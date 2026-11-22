"""Exact frame parity through zoom, resize, colour and load transitions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'app'))

import aura_hive
import calm_field
import fast_cells
import fast_ripples
import recipe_palette


class RenderingParityTests(unittest.TestCase):
    def renderers(self):
        ns = vars(aura_hive)
        genome = aura_hive.Genome([
            ((index * 17) % 97) / 96 for index in range(len(aura_hive.GENE_NAMES))
        ])
        renderers = [
            cls({}, genome, True) for cls in
            (fast_ripples.renderer_class(ns), fast_cells.renderer_class(ns))
        ]
        for renderer in renderers:
            renderer.rng.seed(4127)
        return renderers

    @unittest.skipIf(fast_cells._fast_cells is None, 'Native extension not built')
    def test_native_frames_match_python_through_live_transitions(self):
        cases = (
            (64, 24, 1.0, 12.345),
            (64, 24, 1.0, 12.678),
            (64, 24, 0.6, 13.999),
            (80, 28, 1.4, 14.001),
            (80, 28, 1.4, 26.125),
            (64, 24, 1.0, 90.25),
        )
        for calm in (True, False):
            for recipes in (True, False):
                with patch.object(calm_field, 'ENABLED', calm), patch.object(recipe_palette, 'ENABLED', recipes):
                    python, native = self.renderers()
                    for index, (cols, rows, scale, t) in enumerate(cases):
                        with self.subTest(calm=calm, recipes=recipes, case=index):
                            for renderer in (python, native):
                                renderer.cols, renderer.rows = cols, rows
                                renderer.scale = scale
                                renderer.scale_target = 1.0
                                renderer.dream = index * 0.08
                                renderer.digit_boost = index * 0.07
                                renderer.noise_boost = index * 0.06
                                renderer._chroma_hue = index * 0.13
                                renderer._chroma_pulse = index * 0.1
                                renderer.load_high = index % 2 == 1
                                renderer.load_level = index % 3
                                renderer.load_thin = index % 3 == 2
                                renderer.genome.genes[0] = (index + 1) / 7
                                renderer.ripples = [
                                    dict(fx=0.3 + n * 0.2, fy=0.4, r=3.5, life=0.8, auth=auth)
                                    for n, auth in enumerate(('authority', 'unauthority', 'residue'))
                                ]
                            self.assertEqual(native._frame(cols, rows, t), python._frame(cols, rows, t))
                            self.assertEqual(native._glyph_sample, python._glyph_sample)

    def test_python_fallback_keeps_prepared_cells(self):
        with patch.object(fast_cells, '_fast_cells', None):
            python, fallback = self.renderers()
            for cols, rows, scale, t in ((64, 24, 1.0, 1.2), (80, 28, 0.6, 14.1), (64, 24, 1.0, 28.2)):
                for renderer in (python, fallback):
                    renderer.scale = scale
                self.assertEqual(fallback._frame(cols, rows, t), python._frame(cols, rows, t))
