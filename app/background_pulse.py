"""A warm, light pulse in the dark background (owner-requested 10 November 2026, for Abled): "make the dark
background pulse infinite colours ❤️ only lightly though make it warming".

Presentation only. The window paints Alien's native void (unchanged in every frame) with a small tint:
  - it breathes: a soft rise and fall about every 96 native ticks;
  - its hue drifts through every colour, about once per HUE_TICKS ticks, nudged by an irrational wobble so the
    drift never settles into an exact repeat;
  - it is warmed: the tint is mostly amber, with the drifting hue mixed in;
  - it is light: at most MAX_LIFT above the native void per channel, never below it.
The phase comes from the frame's own native tick, so no new clock is added; while the world sleeps its ticks rest
and so does the pulse. ENABLED = False paints exactly the native void, as the prior release did.
"""
import math

ENABLED = True
BREATH_TICKS = 96            # one breath: about 14 seconds at the world's usual pace
HUE_TICKS = 2600             # one drift through every colour: about six minutes
WARM = (1.0, 0.58, 0.28)     # amber hearth
WARM_SHARE = 0.68            # how much of the tint is the hearth; the rest is the drifting hue
BASE_LIFT, BREATH_LIFT = 0.025, 0.030
MAX_LIFT = BASE_LIFT + BREATH_LIFT
_WOBBLE = (math.sqrt(5) - 1) / 2  # golden ratio conjugate: the drift's nudge never lines up with its own cycle


def hue_at(tick):
    t = int(tick)
    return (t / HUE_TICKS + 0.08 * math.sin(2 * math.pi * _WOBBLE * t / 300)) % 1.0


def _hue_rgb(h):
    """Pure hue at saturation 0.6, value 1."""
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    s = 0.6
    p, q, u = 1 - s, 1 - s * f, 1 - s * (1 - f)
    return ((1, u, p), (q, 1, p), (p, 1, u), (p, q, 1), (u, p, 1), (1, p, q))[i]


def pulse(void, tick):
    """The background to paint for a frame whose native void is `void` (0..1 per channel) at native `tick`."""
    void = tuple(void)
    if not ENABLED or tick is None:
        return void
    t = int(tick)
    breath = 0.5 - 0.5 * math.cos(2 * math.pi * t / BREATH_TICKS)
    hue = _hue_rgb(hue_at(t))
    tint = tuple(WARM_SHARE * w + (1 - WARM_SHARE) * c for w, c in zip(WARM, hue))
    lift = BASE_LIFT + BREATH_LIFT * breath
    return tuple(min(1.0, v + lift * c) for v, c in zip(void, tint))
