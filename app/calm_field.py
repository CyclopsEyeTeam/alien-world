"""Radiant solid squares & outward-swirling spirals, reactive infinite colours, and lively flow.

Presentation & visual-shaping layer (owner-requested 10 November 2026:
  1. "make it more attractive and relaxing too watch? its kinda chaotic right now ;d"
  2. "can appreciate it more now, but its all very slow, alot of empty dark spaces
      also, can you put some random stuff in there too"
  3. "can you make it more colourful too with the infinite colours <3 add more recipes in there if you can"
  4. "still very dark and slow, underneath all the draw can you put some solid squares
      that change and vary in size for some light"
  5. "sweet can you make a chance for the square to turn to a spiral and swirl out <3
      can you also make the colours reactive").

When ENABLED is True:
  - underlight_squares places up to 18 glowing, colour-recipe-tinted shapes underneath
    all GL glyph & Cairo drawing — spanning grand lantern squares, medium prism squares,
    and quick gem squares — where squares periodically win a spiral roll, smoothly spin
    and morph from a solid Chebyshev square into a 2-arm or 3-arm logarithmic spiral,
    expand ~2x, shimmer chromatically along their outer arms, and swirl outward;
  - ReactiveChroma + live field signals make both field ribbons and underlight squares/spirals
    react vividly in colour and luminance to canonical ticks, entropy/light-variance surges,
    ripples, thoughts, fragments, math patterns, recalls, and genome generations;
  - flow_vector glides on lively 13-second smooth currents (~1.16..1.80x pace) with ~28 FPS
    renderer cadence and zero solid ▓█ brick walls.

Setting ENABLED = False reproduces native-warm-pulse-v1 frames byte for byte (and turns off
underlight squares/spirals cleanly). No new clock, worker, model call, source, archive key or authority.
"""
import colorsys
import math

ENABLED = True
SQUARES_ENABLED = True
SPIRAL_SWIRL_ENABLED = True
ELECTRIC_GLASS_ENABLED = True
MAX_UNDERLIGHT_SQUARES = 18
UNDERLIGHT_FEATHER = 1.25

FLOW_EPOCH = 13.0
FLOW_EASE = 5.0 / FLOW_EPOCH

# Luminous single-width glyph progressions using the existing font repertoire only:
# airy filigree at the edges rising to bright woven crests, with zero solid ▓█ brick walls.
CALM_CHAR_BANDS = (
    "·.,:;~=+*#%░▒░%#*+=~·",
    "·.:;~=+*◦◊#░#◊◦*+=~·.",
    "·.,:;~=+*^%░▒░%^*+=~·",
    "·.,:;~=+*#%░#%#*+=~:·",
    "·.:;~+*=*#░▒░#*=*+~:·",
    "·.,:;~=+*x◊#░#◊x*+=~·",
)

# Ambient pocket curiosities that softly materialize and fade inside dark coves.
CALM_CURIOSITIES = "·*+◦◊π∞∆≈01379~:"


def _clamp01(v: float) -> float:
    return 0.0 if v <= 0.0 else (1.0 if v >= 1.0 else v)


def _hash_u32(a: int, b: int, c: int) -> float:
    n = (a * 374761393 + b * 668265263 + c * 1442695041) & 0xFFFFFFFF
    n ^= n >> 13
    n = (n * 1274126177) & 0xFFFFFFFF
    return (n & 0xFFFFFF) / float(0xFFFFFF)


def _calm_angle(epoch: int) -> float:
    e = float(epoch)
    base = 0.85 * math.sin(e * 0.61803398875 - 1.5) + 0.52 * math.cos(e * 0.2718281828 - 0.9)
    nudge = (_hash_u32(epoch & 0xFFFFFFFF, 0x9E3779B1, 31) - 0.5) * 0.55
    return base + nudge


def flow_vector(t: float) -> tuple[float, float, float, float]:
    """Smooth, energetic current direction and ~1.16..1.80x breathing pace."""
    if not math.isfinite(t):
        return 1.0, 0.0, 0.0, t
    epoch = t / FLOW_EPOCH
    e0 = math.floor(epoch)
    raw_u = (epoch - e0) / FLOW_EASE
    u = 0.0 if raw_u < 0.0 else (1.0 if raw_u > 1.0 else raw_u)
    u = u * u * (3.0 - 2.0 * u)
    a0 = _calm_angle(e0)
    da = _calm_angle(e0 + 1) - a0
    while da > math.pi:
        da -= math.tau
    while da < -math.pi:
        da += math.tau
    angle = a0 + da * u
    # Instantaneous pace d(phi)/dt stays in ~1.16..1.80: lively, smooth, never static.
    phi = (
        1.48 * t
        - (0.22 / 0.28) * (math.cos(t * 0.28 + 0.9) - math.cos(0.9))
        - (0.10 / 0.11) * (math.cos(t * 0.11 + 0.3) - math.cos(0.3))
    )
    return math.cos(angle), math.sin(angle), angle, phi


class ReactiveChroma:
    """Presentation-only colour reactivity tracker updated once per uploaded Message.

    Re-observing the same Message returns the cached (hue_offset, energy) pair
    unchanged so frozen-frame visibility proofs render identically before/after.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._last_msg = None
        self._last_seq = -1
        self._last_ts = 0.0
        self._last_tick = 0
        self._last_gen = 0
        self._ent_ema = 0.5
        self._col_ema = 0.5
        self.hue = 0.0
        self.target_hue = 0.0
        self.energy = 0.0
        self.current: tuple[float, float] = (0.0, 0.0)

    def observe(self, message) -> tuple[float, float]:
        if message is None:
            return self.current
        seq = getattr(message, "sequence", None)
        if message is self._last_msg or (isinstance(seq, int) and seq > 0 and seq == self._last_seq):
            return self.current

        raw_ts = getattr(message, "timestamp", None)
        ts = float(raw_ts) if isinstance(raw_ts, (int, float)) and math.isfinite(raw_ts) else 0.0
        raw_ent = getattr(message, "entropy", 0.5)
        ent = _clamp01(float(raw_ent) if isinstance(raw_ent, (int, float)) and math.isfinite(raw_ent) else 0.5)
        raw_col = getattr(message, "colour", 0.5)
        col = max(0.0, min(1.5, float(raw_col) if isinstance(raw_col, (int, float)) and math.isfinite(raw_col) else 0.5))
        raw_tick = getattr(message, "tick", 0)
        tick = int(raw_tick) if isinstance(raw_tick, int) else 0
        raw_gen = getattr(message, "generation", 0)
        gen = int(raw_gen) if isinstance(raw_gen, int) else 0

        if not self._initialized:
            self._initialized = True
            self._last_msg = message
            self._last_seq = seq if isinstance(seq, int) else -1
            self._last_ts = ts
            self._last_tick = tick
            self._last_gen = gen
            self._ent_ema = ent
            self._col_ema = col
            self.current = (0.0, 0.0)
            return self.current

        dt = max(0.005, min(0.25, ts - self._last_ts)) if ts > self._last_ts else 0.032
        self._last_ts = ts
        self._last_msg = message
        self._last_seq = seq if isinstance(seq, int) else -1

        d_ent = abs(ent - self._ent_ema)
        d_col = abs(col - self._col_ema)
        self._ent_ema += (ent - self._ent_ema) * 0.14
        self._col_ema += (col - self._col_ema) * 0.14

        surge = min(1.0, d_ent * 22.0 + d_col * 5.2)
        if tick != self._last_tick:
            self._last_tick = tick
            surge = max(surge, 0.56)
            self.target_hue = (self.target_hue + 0.11803398875) % 1.0
        if gen != self._last_gen:
            self._last_gen = gen
            surge = 1.0
            self.target_hue = (self.target_hue + 0.38196601125) % 1.0
        if surge > 0.06:
            self.energy = min(1.0, max(self.energy, surge))
            self.target_hue = (self.target_hue + surge * 0.22) % 1.0
        else:
            self.energy = max(0.0, self.energy - dt * 0.62)

        dh = ((self.target_hue - self.hue + 0.5) % 1.0) - 0.5
        self.hue = (self.hue + dh * min(1.0, dt * 4.5)) % 1.0
        self.current = (self.hue, self.energy)
        return self.current


def _encode_swirl(progress: float, spin_sign: float, three_arms: bool, inward: bool = False) -> float:
    """Magnitudes above two select the inward coil without changing outward encodings."""
    p = max(0.001, min(1.0, progress))
    mag = (2.0 + p) if inward else ((1.0 + p) if three_arms else p)
    return mag if spin_sign >= 0.0 else -mag


def _decode_swirl(swirl: float) -> tuple[float, float, float]:
    """Return (progress_0_to_1, spin_dir, arms) for a packed swirl parameter."""
    sdir = 1.0 if swirl >= 0.0 else -1.0
    mag = abs(swirl)
    if mag > 2.0:
        return min(1.0, mag - 2.0), sdir, 1.0
    if mag > 1.0:
        return min(1.0, mag - 1.0), sdir, 3.0
    return min(1.0, mag), sdir, 2.0


def underlight_squares(
    message,
    width: float,
    height: float,
    t0: float | None = None,
    reactive: tuple[float, float] = (0.0, 0.0),
) -> tuple[tuple[float, float, float, float, float, float, float, float], ...]:
    """Deterministic solid squares & outward-swirling spirals underneath all GL & Cairo drawing.

    Derived strictly from the presented `message` (and optional per-message `reactive`
    pair `(reactive_hue, reactive_energy)`) so frozen-frame visibility probes render
    identically before and after neural overlays.

    Returns up to MAX_UNDERLIGHT_SQUARES tuples:
        (cx_px, cy_px, half_side_px, swirl_param, r, g, b, alpha)
    where `swirl_param == 0.0` is a crisp solid square and `abs(swirl_param) > 0.0`
    smoothly morphs the square into a 2-arm or 3-arm logarithmic spiral swirling outward.
    """
    if not ENABLED or not SQUARES_ENABLED or message is None or width < 1 or height < 1:
        return ()
    ts = getattr(message, "timestamp", None)
    if isinstance(ts, (int, float)) and math.isfinite(ts):
        base = float(ts) if (t0 is None or not math.isfinite(t0)) else float(t0)
        t = max(0.0, float(ts) - base)
    else:
        tick_t = getattr(message, "tick", 0)
        t = float(int(tick_t) if isinstance(tick_t, int) else 0) * 0.14

    raw_col = getattr(message, "colour", 0.5)
    col_var = max(0.0, min(1.5, float(raw_col) if isinstance(raw_col, (int, float)) and math.isfinite(raw_col) else 0.5))
    raw_ent = getattr(message, "entropy", 0.5)
    ent = _clamp01(float(raw_ent) if isinstance(raw_ent, (int, float)) and math.isfinite(raw_ent) else 0.5)
    raw_tick = getattr(message, "tick", 0)
    tick = int(raw_tick) if isinstance(raw_tick, int) else 0
    raw_gen = getattr(message, "generation", 0)
    gen = (int(raw_gen) if isinstance(raw_gen, int) else 0) & 0xFFFF

    r_hue, r_energy = reactive
    seed = (col_var * 0.41 + gen * 0.138196601125) % 1.0
    # Instantaneous + stateful colour reactivity: field entropy, luminance variance,
    # canonical ticks, and ReactiveChroma surges sweep hues & boost luminous bloom.
    live_hue = (
        r_hue
        + (ent - 0.5) * 0.48
        + (col_var - 0.5) * 0.34
        + (tick % 23) * 0.031
    ) % 1.0
    live_energy = min(
        1.0,
        max(
            float(r_energy),
            abs(ent - 0.5) * 1.15 + max(0.0, col_var - 0.55) * 0.85,
        ),
    )

    from recipe_palette import recipe_rgb, table_for
    rtable = table_for(t + live_hue * 6.5, seed)

    def _sq_rgb(h: float, sat: float) -> tuple[float, float, float]:
        if rtable is not None:
            ri, gi, bi = recipe_rgb(rtable, h, sat, 1.0)
            r, g, b = ri / 255.0, gi / 255.0, bi / 255.0
        else:
            r, g, b = colorsys.hsv_to_rgb(h % 1.0, sat, 1.0)
        peak = max(r, g, b, 0.25)
        return r / peak, g / peak, b / peak

    w_f = float(width)
    h_f = float(height)
    min_d = min(w_f, h_f)
    swirl_on = bool(SPIRAL_SWIRL_ENABLED)
    energy_lift = 1.0 + 0.28 * live_energy
    spread_boost = 1.0 + 0.35 * live_energy
    out: list[tuple[float, float, float, float, float, float, float, float]] = []

    # Tier 1 (slots 0..5): 6 broad glowing lantern squares that glide & breathe in size,
    # with a ~42..64% phrase chance to unwind into a grand logarithmic spiral and swirl out.
    for i in range(6):
        phrase_len = 8.4 + 1.15 * i
        p_pos = t / phrase_len + i * 0.371
        phr = int(math.floor(p_pos))
        pu = p_pos - phr
        ux = 0.11 + 0.78 * (0.5 + 0.46 * math.sin(t * (0.28 + 0.055 * i) + i * 1.91))
        uy = 0.13 + 0.74 * (0.5 + 0.46 * math.cos(t * (0.22 + 0.045 * i) + i * 2.53))
        size_wave = 0.5 + 0.5 * math.sin(t * (0.68 + 0.14 * i) + i * 1.17)
        half_s = max(10.0, min_d * (0.072 + 0.118 * size_wave + 0.014 * (i % 3)))
        swirl = 0.0
        alpha_env = 1.0
        if swirl_on and _hash_u32(i, 887, phr + gen) < (0.42 + 0.22 * live_energy):
            if 0.36 < pu <= 0.92:
                sp = (pu - 0.36) / 0.56
                sdir = 1.0 if _hash_u32(i, 889, phr + gen) >= 0.5 else -1.0
                arms3 = _hash_u32(i, 893, phr + gen) < 0.42
                inward = i % 3 == 0 and _hash_u32(i, 1031, phr + gen) < 0.65
                swirl = _encode_swirl(sp, sdir, arms3, inward)
                half_s *= (1.0 - 0.36 * sp) if inward else (1.0 + 0.88 * sp)
                alpha_env = math.sin(math.pi * min(1.0, (pu - 0.12) / 0.80)) ** 0.55
            elif pu > 0.92:
                re_u = (pu - 0.92) / 0.08
                alpha_env = re_u * re_u * (3.0 - 2.0 * re_u)
                half_s *= 0.65 + 0.35 * alpha_env
        hue = (live_hue + seed * 0.61 + i * 0.161803398875 * spread_boost + t * (0.058 + 0.009 * i)) % 1.0
        r, g, b = _sq_rgb(hue, 0.95)
        alpha = min(0.56, (0.26 + 0.14 * (0.5 + 0.5 * math.cos(t * (0.52 + 0.09 * i) - i * 0.8))) * energy_lift * alpha_env)
        if alpha > 0.01:
            out.append((ux * w_f, uy * h_f, half_s, swirl, r, g, b, alpha))

    # Tier 2 (slots 6..12): 7 medium prism squares that pop into fresh places, vary in size,
    # and have a ~48..72% chance to turn into a glowing 2/3-arm spiral and swirl outward.
    for i in range(6, 13):
        j = i - 6
        rate = 0.40 + 0.072 * (j % 4)
        pos = t * rate + j * 0.61803398875
        cyc = int(math.floor(pos))
        u = pos - cyc
        env = math.sin(math.pi * u)
        if env <= 0.02:
            continue
        ux = 0.08 + 0.84 * _hash_u32(i, 107, cyc + gen) + (u - 0.5) * 0.06 * math.cos(cyc * 1.7 + j)
        uy = 0.10 + 0.80 * _hash_u32(i, 211, cyc + gen) + (u - 0.5) * 0.06 * math.sin(cyc * 1.7 + j)
        base_frac = 0.042 + 0.096 * _hash_u32(i, 313, cyc + gen)
        grow = (0.36 + 0.80 * u) if ((cyc + j) & 1) else (0.34 + 0.84 * (env ** 0.62))
        half_s = max(7.0, min_d * base_frac * grow)
        swirl = 0.0
        if swirl_on and _hash_u32(i, 773, cyc + gen) < (0.48 + 0.24 * live_energy) and u > 0.28:
            sp = (u - 0.28) / 0.72
            sdir = 1.0 if _hash_u32(i, 787, cyc + gen) >= 0.5 else -1.0
            arms3 = _hash_u32(i, 797, cyc + gen) < 0.45
            inward = i % 3 == 0 and _hash_u32(i, 1031, cyc + gen) < 0.65
            swirl = _encode_swirl(sp, sdir, arms3, inward)
            half_s *= (1.0 - 0.36 * sp) if inward else (1.0 + 0.96 * sp)
        hue = (live_hue + seed * 0.47 + _hash_u32(i, 419, cyc) * spread_boost + t * 0.048) % 1.0
        r, g, b = _sq_rgb(hue, 0.96)
        alpha = min(0.60, (0.32 + 0.15 * _hash_u32(i, 521, cyc)) * (env ** 0.66) * energy_lift)
        out.append((ux * w_f, uy * h_f, half_s, swirl, r, g, b, alpha))

    # Tier 3 (slots 13..17): 5 crisp smaller gem squares gleaming & whirling out into fast spirals.
    for i in range(13, MAX_UNDERLIGHT_SQUARES):
        k = i - 13
        rate = 0.58 + 0.11 * (k % 3)
        pos = t * rate + k * 0.38196601125
        cyc = int(math.floor(pos))
        u = pos - cyc
        env = math.sin(math.pi * u)
        if env <= 0.02:
            continue
        ux = 0.07 + 0.86 * _hash_u32(i, 613, cyc + gen)
        uy = 0.09 + 0.82 * _hash_u32(i, 719, cyc + gen)
        base_frac = 0.018 + 0.046 * _hash_u32(i, 823, cyc + gen)
        grow = 0.40 + 0.78 * (env ** 0.55)
        half_s = max(5.0, min_d * base_frac * grow)
        swirl = 0.0
        if swirl_on and _hash_u32(i, 953, cyc + gen) < (0.46 + 0.24 * live_energy) and u > 0.26:
            sp = (u - 0.26) / 0.74
            sdir = 1.0 if _hash_u32(i, 967, cyc + gen) >= 0.5 else -1.0
            arms3 = _hash_u32(i, 971, cyc + gen) < 0.38
            inward = i % 3 == 0 and _hash_u32(i, 1031, cyc + gen) < 0.65
            swirl = _encode_swirl(sp, sdir, arms3, inward)
            half_s *= (1.0 - 0.36 * sp) if inward else (1.0 + 1.05 * sp)
        hue = (live_hue + seed * 0.33 + _hash_u32(i, 929, cyc) * spread_boost + 0.5 + t * 0.068) % 1.0
        r, g, b = _sq_rgb(hue, 0.98)
        alpha = min(0.62, (0.36 + 0.18 * _hash_u32(i, 997, cyc)) * (env ** 0.62) * energy_lift)
        out.append((ux * w_f, uy * h_f, half_s, swirl, r, g, b, alpha))

    return tuple(out)


def _smoothstep(e0: float, e1: float, x: float) -> float:
    if e1 <= e0:
        return 1.0 if x >= e1 else 0.0
    u = (x - e0) / (e1 - e0)
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    return u * u * (3.0 - 2.0 * u)


def underlight_pixel(
    bg: tuple[float, float, float],
    px: float,
    py: float,
    squares: tuple[tuple[float, float, float, float, float, float, float, float], ...],
    *, phase: float = 0.0, energy: float = 0.0, viewport: tuple[float, float] = (1120.0, 634.0),
) -> tuple[float, float, float]:
    """CPU reference for the underlight shader; phase is native presentation time.

    Electric glass changes only display lighting. Disable ELECTRIC_GLASS_ENABLED
    to evaluate the exact previously installed composition.
    """
    if not squares:
        return bg
    fw = UNDERLIGHT_FEATHER
    sr = sg = sb = 0.0
    glass = ENABLED and ELECTRIC_GLASS_ENABLED
    glass_time = phase
    energy = _clamp01(energy)
    for index, (cx, cy, hs, sw, cr_c, cg_c, cb_c, alpha) in enumerate(squares):
        depth = _clamp01(4.0 * hs / max(1.0, min(viewport)))
        rx = px - cx
        ry = py - cy
        if abs(sw) < 0.0005:
            cheb = max(abs(rx), abs(ry))
            if cheb < hs + fw:
                edge = 1.0 - _smoothstep(hs - fw, hs + fw, cheb)
                rim_w = max(2.5, hs * 0.14)
                rim = 1.0 + 0.18 * (1.0 - _smoothstep(0.0, rim_w, abs(cheb - hs * 0.88)))
                w = alpha * edge * rim
                if glass:
                    border = max(0.0, 1.0 - abs(cheb - hs * 0.94) / max(fw, hs * 0.055)) ** 2
                    travel = (0.5 + 0.5 * math.cos((rx + ry) / max(hs, 1.0) * 3.0 - glass_time * 2.0 + index)) ** 8
                    w = alpha * edge * ((0.70 + 0.18 * depth) + border * (1.8 + depth + 1.6 * energy * travel))
                sr += cr_c * w
                sg += cg_c * w
                sb += cb_c * w
        else:
            p, sdir, arms = _decode_swirl(sw)
            rad = math.hypot(rx, ry)
            soft = fw * (1.0 + 2.4 * p)
            if rad < hs * 1.42 + soft:
                inward = arms == 1.0
                rot = 0.0 if inward else sdir * p * (1.8 + 2.4 * p)
                cs = math.cos(rot)
                sn = math.sin(rot)
                rcx = rx * cs + ry * sn
                rcy = -rx * sn + ry * cs
                rcheb = max(abs(rcx), abs(rcy))
                rmix = _smoothstep(0.0, 0.38, p)
                rounded = (abs(rcx) ** 6 + abs(rcy) ** 6) ** (1.0 / 6.0) if inward else rad
                shape_d = rcheb + (rounded - rcheb) * rmix
                if shape_d < hs + soft:
                    edge = 1.0 - _smoothstep(hs - soft, hs + soft, shape_d)
                    rn = rad / max(hs, 1.0)
                    ang = math.atan2(ry, rx) if rad > 0.0001 else 0.0
                    wind = 5.2 * math.log(1.0 + rn * (2.4 + 2.2 * p))
                    phase = arms * (sdir * ang) + wind - p * 10.5
                    if inward:
                        phase = sdir * ang + 22.619467 * (shape_d / max(hs, 1.0)) + p * 10.053096
                    ribbon = _smoothstep(0.55 if inward else 0.24, 0.93 if inward else 0.86, 0.5 + 0.5 * math.cos(phase))
                    eye_inner = _smoothstep(0.008, 0.055, rn) if inward else _smoothstep(0.03 * p, 0.32 * p, rn)
                    eye_mix = _smoothstep(0.24, 0.74, p)
                    eye = 1.0 + (eye_inner - 1.0) * eye_mix
                    carve = _smoothstep(0.03, 0.32, p)
                    sq_rim = 1.0 + 0.18 * (1.0 - _smoothstep(0.0, max(2.5, hs * 0.14), abs(rcheb - hs * 0.88)))
                    rim = sq_rim + (1.18 - sq_rim) * carve
                    mask = 1.0 + (ribbon * eye - 1.0) * carve
                    shift = 0.40 * carve * _clamp01(rn)
                    ar = cr_c + (cg_c - cr_c) * shift
                    ag = cg_c + (cb_c - cg_c) * shift
                    ab = cb_c + (cr_c - cb_c) * shift
                    w = alpha * edge * rim * mask
                    if glass:
                        crest = (0.5 + 0.5 * math.cos(phase)) ** 12
                        # phase above is the coil's geometry; presentation time is kept separately.
                        travel = (0.5 + 0.5 * math.cos(rn * 10.0 - glass_time * 2.0 + ang)) ** 8
                        filament_width = max(0.045, fw / max(hs, 1.0) * 2.4)
                        filament = 1.0 - _smoothstep(filament_width * 0.35, filament_width, abs(math.sin(phase * 0.5 + 0.55)))
                        head = max(0.0, math.cos(ang - glass_time * 0.7 - index * 1.7)) ** 8
                        tail = _smoothstep(0.12, 0.3, rn) * (1.0 - _smoothstep(0.85, 1.08, rn))
                        w = alpha * edge * eye * ((0.72 * mask + (2.6 + 1.8 * depth) * crest * carve) * (0.84 + 0.16 * depth)
                            + 1.6 * energy * travel * mask + 0.85 * carve * filament * head * tail)
                    sr += ar * w
                    sg += ag * w
                    sb += ab * w
    if glass:
        peak = max(sr, sg, sb)
        if peak <= 0.0:
            return bg
        # One luminance shoulder keeps the summed chroma instead of clipping channels to white.
        tone = min(max(0.0, 0.66 - max(bg)), 0.70 * peak / (0.38 + peak))
        return tuple(bg[k] + value / peak * tone for k, value in enumerate((sr, sg, sb)))
    return (
        min(0.66, max(0.0, bg[0] + sr / (1.0 + sr * 0.55))),
        min(0.66, max(0.0, bg[1] + sg / (1.0 + sg * 0.55))),
        min(0.66, max(0.0, bg[2] + sb / (1.0 + sb * 0.55))),
    )
