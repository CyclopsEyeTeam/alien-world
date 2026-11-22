"""Exact native cell-grid construction via the local C extension.

The extension replicates fast_field.prepare_cell and the native
_build_cells grid loop with the same libm sin, the same expression order
and no FP contraction; benchmark_frame.py asserts exact cells/RGB
equality against the prior release source before any release selection.
There is no silent Python fallback here: a missing or mismatched
extension is a packaging error and fails loudly.
"""
from fast_field import prepare_state
from fast_ripples import renderer_class as ripple_renderer
try:
    import _fast_cells
except ImportError:
    _fast_cells = None

def renderer_class(ns):
    Base = ripple_renderer(ns)
    if _fast_cells is None:
        return Base
    class FastCells(Base):
        def _build_cells(self, cols, rows, t, void):
            s = prepare_state(ns, self.genome, t, cols, rows, getattr(self, '_chroma_hue', 0.0), getattr(self, '_chroma_pulse', 0.0))
            spark_left = -1
            if self.load_high:
                spark_left = 6 if self.load_level >= 2 else 18
            calm_args = (
                s['shimmer_blend'], s['swell_freq'], s['swell_shift'], s['inv_span'],
                s['hue_drift'], s['cur_tick'], s['cur_blend'], s['curiosities'],
            ) if s['calm'] else None
            return _fast_cells.build_cells(
                s['cols'], s['rows'], t, void,
                s['freq'], s['tspeed'], s['tslow'], s['palette'], s['hue0'],
                s['spread'], s['noise'], s['amp'], s['tick'], s['period'],
                s['crest'], s['phase'], s['dark_limit'], s['spark_limit'],
                s['saturation'], s['band'], ns['SPARKS'],
                self.prepared_x, self.prepared_y,
                self.load_thin, self.digit_boost > 0.08,
                self.digit_boost * 0.22, int(t * (1.8 if s['calm'] else 11)),
                self.noise_boost > 0.15, int(t * (2.5 if s['calm'] else 30)), spark_left,
                s['fdx'], s['fdy'], s['recipe_table'], calm_args)

        def _paint_ripples(self, cells, cols, rows, t):
            if ns.get('_rift_center') is None:
                flow_a = float('nan')
            else:
                fv = ns.get('flow_vector')
                flow = getattr(self, '_flow', None)
                flow_a = flow[2] if flow is not None else (fv(t)[2] if fv is not None else 0.0)
            _fast_cells.paint_ripples(
                cells, cols, rows, t, self.ripples,
                float(self.genome.g("hue")), ns['SPARKS'], ns['BLOCKS'], flow_a)

        def _post_pass(self, cells, cols, rows, front, veil, veil_y,
                       veil_tick, dream_mix, lift, trans=0.0, front_lift=36):
            return _fast_cells.post_cells(
                cells, cols, rows, front, veil, veil_y,
                veil_tick, dream_mix, lift, trans, front_lift)
    return FastCells
