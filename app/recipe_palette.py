"""Recipe-based field colour: Abled's recipes cooked into a colour ring the field reads instead of the HSV wheel.

The field still computes the same hue, saturation and value for every cell (characters, light, sparks, dark
cells and every other layer are unchanged). Only the final colour lookup changes: the hue picks a colour from
the current course's ring of cooked recipes, and saturation/value act on it exactly as HSV does on a pure hue
(v * (1 - s * (1 - c)); for a pure-hue c this is HSV). A new course is cooked every course window of the
existing render time t, blended smoothly from the last, each carrying an heirloom from the one before, so the
colours never run out. When colour_recipes.EXPANDED is True (10 November 2026), each course cooks a 12-stop
ring across 512 smooth table entries every 32 seconds with vivid chromatic separation so infinite colours
bloom across the field at once. No new clock, worker, input or authority: course derives from t, seed from genome.
"""
import colorsys
import math
from functools import lru_cache

import colour_recipes
from colour_recipes import ring

ENABLED = True
COURSE_SECONDS = 14.0
LEGACY_COURSE_SECONDS = 90.0
STOPS = 12
LEGACY_STOPS = 6
TABLE_SIZE = 512
LEGACY_TABLE_SIZE = 384


def shine(colour):
    """Abled's choice (9 Nov 2026, after seeing his first recipes come out dusty: "not bad, but not that"):
    every recipe shines at full light with its own hue; dusty recipes stay softer, grey stays grey.
    In expanded mode (10 Nov 2026), saturation shines even more vividly so multi-stop mixes never wash out."""
    r, g, b = (min(1., max(0., c)) for c in colour)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if colour_recipes.EXPANDED:
        shined_s = max(0.70, s ** 0.20) if s > 0.03 else (s ** 0.3 if s > 0. else 0.)
        return colorsys.hsv_to_rgb(h, min(1., shined_s), 1.)
    return colorsys.hsv_to_rgb(h, s ** 0.3 if s > 0. else 0., 1.)


@lru_cache(maxsize=64)
def _course_ring(course, seed, expanded):
    stops = STOPS if expanded else LEGACY_STOPS
    raw_ring = ring(course, seed, stops)
    if not expanded:
        return tuple(shine(c) for c in raw_ring)
    # Give each stop its cooked recipe colour while nudging near-duplicate neighbour hues
    # by a gentle golden-angle offset so all 12 stops bring rich variety to the ring.
    out = []
    prev_h = None
    for idx, c in enumerate(raw_ring):
        r, g, b = (min(1., max(0., ch)) for ch in c)
        h, s, _v = colorsys.rgb_to_hsv(r, g, b)
        if prev_h is not None:
            dh = abs((h - prev_h + 0.5) % 1.0 - 0.5)
            if dh < 0.075:
                h = (h + 0.138196601125 * (1 + (idx % 3))) % 1.0
        prev_h = h
        shined_s = max(0.64, s ** 0.22) if s > 0.03 else (s ** 0.3 if s > 0. else 0.)
        out.append(colorsys.hsv_to_rgb(h, min(1., shined_s), 1.))
    return tuple(out)


@lru_cache(maxsize=16)
def _table_at(course, seed, step, expanded):
    """The ring for `course`, blended toward the next course by step/steps (smoothstep), as a flat tuple."""
    stops = STOPS if expanded else LEGACY_STOPS
    tsize = TABLE_SIZE if expanded else LEGACY_TABLE_SIZE
    blend_steps = 64. if expanded else 32.
    a = _course_ring(course, seed, expanded)
    b = _course_ring(course + 1, seed, expanded)
    f = step / blend_steps
    f = f * f * (3. - 2. * f)
    flat = []
    for i in range(tsize):
        pos = i * stops / tsize
        k = int(pos)
        w = pos - k
        if expanded:
            w = w * w * (3. - 2. * w)
        k2 = (k + 1) % stops
        for ch in range(3):
            ca = a[k][ch] * (1. - w) + a[k2][ch] * w
            cb = b[k][ch] * (1. - w) + b[k2][ch] * w
            flat.append(ca * (1. - f) + cb * f)
    return tuple(flat)


def table_for(t, seed):
    """Colour table for render time t and genome hue seed; None when recipes are switched off."""
    if not ENABLED or not math.isfinite(t):
        return None
    expanded = bool(colour_recipes.EXPANDED)
    csec = COURSE_SECONDS if expanded else LEGACY_COURSE_SECONDS
    bsteps = 64 if expanded else 32
    pos = max(0., t) / csec
    course = int(pos)
    return _table_at(course, round(float(seed), 6), min(bsteps - 1, int((pos - course) * bsteps)), expanded)


def recipe_rgb(table, h, s, v):
    """HSV-shaped colour from the recipe table; mirrored exactly by _fast_cells.c recipe_rgb."""
    h = h % 1.0
    s = 0. if s < 0. else (1. if s > 1. else s)
    v = 0. if v < 0. else (1. if v > 1. else v)
    n = len(table) // 3
    i = int(h * n)
    if i >= n:
        i = n - 1
    r = v * (1.0 - s * (1.0 - table[3 * i]))
    g = v * (1.0 - s * (1.0 - table[3 * i + 1]))
    b = v * (1.0 - s * (1.0 - table[3 * i + 2]))
    return (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5))
