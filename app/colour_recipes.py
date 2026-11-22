"""Abled's colour kitchen: his pantry, his method and his recipes (owner-requested 9 November 2026,
expanded 10 November 2026 with jewel/aurora pantry pigments, chromatic alchemy steps, and signature recipes).

Pure maths, no I/O, no randomness: the same (course, seed, stop) always cooks the same colour,
and every course carries an heirloom first ingredient from the course before so colours evolve
smoothly forever without repeating. Setting EXPANDED = False restores the original 11-pigment,
6-step kitchen byte for byte.
"""
import math

EXPANDED = True


def _hex_to_rgb(h):
    h = h.lstrip('#')
    return (int(h[0:2], 16) / 255.0,
            int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0)


PANTRY = {
    # Original 11 pantry pigments
    "gold": _hex_to_rgb("#FFD700"),
    "orange": _hex_to_rgb("#FFA500"),
    "yellow": _hex_to_rgb("#FFFF00"),
    "green": _hex_to_rgb("#008000"),
    "blue": _hex_to_rgb("#0000FF"),
    "beam": _hex_to_rgb("#BE8E44"),
    "old-paper": _hex_to_rgb("#C9B8A4"),
    "amber": _hex_to_rgb("#FFB000"),
    "cobalt": _hex_to_rgb("#0047AB"),
    "violet": _hex_to_rgb("#8F00FF"),
    "red": _hex_to_rgb("#EB2D23"),
    # Expanded luminous aurora, reef, and jewel pigments (10 November 2026)
    "turquoise": _hex_to_rgb("#00E5D4"),
    "cyan": _hex_to_rgb("#00C8FF"),
    "cerulean": _hex_to_rgb("#1488FF"),
    "indigo": _hex_to_rgb("#4B00E0"),
    "magenta": _hex_to_rgb("#FF00A8"),
    "rose": _hex_to_rgb("#FF3B7F"),
    "coral": _hex_to_rgb("#FF6B57"),
    "crimson": _hex_to_rgb("#DC143C"),
    "tangerine": _hex_to_rgb("#FF7A00"),
    "sunburst": _hex_to_rgb("#FFE600"),
    "chartreuse": _hex_to_rgb("#9DFF00"),
    "lime": _hex_to_rgb("#32E838"),
    "emerald": _hex_to_rgb("#00C978"),
    "jade": _hex_to_rgb("#00A88F"),
    "mint": _hex_to_rgb("#4FFFB0"),
    "orchid": _hex_to_rgb("#D946EF"),
    "amethyst": _hex_to_rgb("#9D4EDD"),
}

PANTRY_BASE_ORDER = (
    "gold", "orange", "yellow", "green", "blue", "beam", "old-paper",
    "amber", "cobalt", "violet", "red",
)
PANTRY_ORDER = PANTRY_BASE_ORDER + (
    "turquoise", "cyan", "cerulean", "indigo", "magenta", "rose",
    "coral", "crimson", "tangerine", "sunburst", "chartreuse",
    "lime", "emerald", "jade", "mint", "orchid", "amethyst",
)

BASE_STEPS = ('glow', 'swirl', 'dust', 'bend', 'whisper', 'steep')
EXPANDED_STEPS = BASE_STEPS + (
    'bloom', 'prism', 'aurora', 'nectar', 'glaze', 'iridesce', 'ember', 'lagoon',
)

# 24 curated signature recipe templates paired with procedural heirloom & seasoning
# so courses stay vividly chromatic while evolving through infinite non-repeating shades.
SIGNATURE_RECIPES = (
    {"name": "solar-nectar", "pair": (("gold", 4), ("coral", 2)), "steps": ("bloom", "nectar")},
    {"name": "bioluminescent-lagoon", "pair": (("turquoise", 4), ("emerald", 3)), "steps": ("lagoon", "glow")},
    {"name": "orchid-nebula", "pair": (("orchid", 4), ("indigo", 2)), "steps": ("bloom", "iridesce")},
    {"name": "emerald-aurora", "pair": (("emerald", 4), ("lime", 2)), "steps": ("aurora", "bloom")},
    {"name": "coral-sunset", "pair": (("coral", 4), ("amber", 3)), "steps": ("nectar", "ember")},
    {"name": "cobalt-starfire", "pair": (("cerulean", 4), ("cyan", 3)), "steps": ("bloom", "glow")},
    {"name": "chartreuse-firefly", "pair": (("chartreuse", 3), ("mint", 3)), "steps": ("bloom", "swirl")},
    {"name": "crimson-velvet", "pair": (("crimson", 4), ("rose", 3)), "steps": ("ember", "bloom")},
    {"name": "turquoise-prism", "pair": (("turquoise", 4), ("cyan", 2)), "steps": ("prism", "bloom")},
    {"name": "amethyst-dusk", "pair": (("amethyst", 4), ("magenta", 2)), "steps": ("iridesce", "glow")},
    {"name": "amber-hearth", "pair": (("amber", 4), ("tangerine", 3)), "steps": ("nectar", "bloom")},
    {"name": "mint-borealis", "pair": (("mint", 4), ("jade", 3)), "steps": ("aurora", "lagoon")},
    {"name": "rose-supernova", "pair": (("rose", 4), ("magenta", 3)), "steps": ("bloom", "glaze")},
    {"name": "cerulean-tide", "pair": (("cerulean", 4), ("cobalt", 3)), "steps": ("lagoon", "iridesce")},
    {"name": "tangerine-glow", "pair": (("tangerine", 4), ("sunburst", 3)), "steps": ("bloom", "glow")},
    {"name": "indigo-mirage", "pair": (("indigo", 4), ("violet", 3)), "steps": ("prism", "iridesce")},
    {"name": "jade-whisper", "pair": (("jade", 4), ("turquoise", 2)), "steps": ("lagoon", "bloom")},
    {"name": "sunburst-halo", "pair": (("sunburst", 4), ("gold", 3)), "steps": ("glow", "nectar")},
    {"name": "magenta-drift", "pair": (("magenta", 4), ("orchid", 3)), "steps": ("bloom", "swirl")},
    {"name": "gold-filigree", "pair": (("gold", 4), ("beam", 2)), "steps": ("nectar", "bloom")},
    {"name": "spring-dew", "pair": (("lime", 3), ("emerald", 3)), "steps": ("bloom", "aurora")},
    {"name": "deep-reef", "pair": (("cyan", 4), ("indigo", 2)), "steps": ("lagoon", "glaze")},
    {"name": "twilight-opal", "pair": (("orchid", 3), ("turquoise", 3)), "steps": ("iridesce", "prism")},
    {"name": "electric-violet", "pair": (("violet", 4), ("cerulean", 2)), "steps": ("bloom", "aurora")},
)


def _active_order():
    return PANTRY_ORDER if EXPANDED else PANTRY_BASE_ORDER


def mix(ingredients):
    """Weighted average of pantry colours by parts."""
    tr = tg = tb = 0.0
    total = 0.0
    for name, parts in ingredients:
        r, g, b = PANTRY[name]
        tr += r * parts
        tg += g * parts
        tb += b * parts
        total += parts
    return (tr / total, tg / total, tb / total)


def _clamp(x):
    return max(0.0, min(1.0, x))


def _rgb_to_hls(r, g, b):
    mx = max(r, g, b)
    mn = min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6.0 if g < b else 0.0)
        elif mx == g:
            h = (b - r) / d + 2.0
        else:
            h = (r - g) / d + 4.0
        h /= 6.0
    return h, l, s


def _hls_to_rgb(h, l, s):
    if s == 0.0:
        return (l, l, l)

    def hue2rgb(p, q, t):
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
    return (r, g, b)


def apply(colour, step, amount):
    """Apply a single recipe step to a colour."""
    r, g, b = colour
    order = _active_order()
    if step == "glow":
        return (_clamp(r + (1 - r) * amount * 0.5),
                _clamp(g + (1 - g) * amount * 0.5),
                _clamp(b + (1 - b) * amount * 0.5))
    if step == "swirl":
        h, l, s = _rgb_to_hls(r, g, b)
        h = (h + amount) % 1.0
        nr, ng, nb = _hls_to_rgb(h, l, s)
        return (_clamp(nr), _clamp(ng), _clamp(nb))
    if step == "dust":
        grey = (r + g + b) / 3.0
        return (_clamp(r + (grey - r) * amount),
                _clamp(g + (grey - g) * amount),
                _clamp(b + (grey - b) * amount))
    if step == "bend":
        best = None
        best_d = None
        for name in order:
            pr, pg, pb = PANTRY[name]
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if best_d is None or d < best_d:
                best_d = d
                best = name
        idx = order.index(best)
        nxt = order[(idx + 1) % len(order)]
        nr, ng, nb = PANTRY[nxt]
        t = amount * 0.5
        return (_clamp(r + (nr - r) * t),
                _clamp(g + (ng - g) * t),
                _clamp(b + (nb - b) * t))
    if step == "whisper":
        t = amount * 0.4
        return (_clamp(r + (0.5 - r) * t),
                _clamp(g + (0.5 - g) * t),
                _clamp(b + (0.5 - b) * t))
    if step == "steep":
        f = 1 - amount * 0.45
        return (_clamp(r * f), _clamp(g * f), _clamp(b * f))
    if step == "bloom":
        h, l, s = _rgb_to_hls(r, g, b)
        s = _clamp(s + (0.98 - s) * amount * 0.68)
        l = _clamp(l + (0.54 - l) * amount * 0.34)
        nr, ng, nb = _hls_to_rgb(h, l, s)
        return (_clamp(nr), _clamp(ng), _clamp(nb))
    if step == "prism":
        h, l, s = _rgb_to_hls(r, g, b)
        h = (h + amount * 0.61803398875) % 1.0
        s = _clamp(s + (0.95 - s) * amount * 0.42)
        nr, ng, nb = _hls_to_rgb(h, l, s)
        return (_clamp(nr), _clamp(ng), _clamp(nb))
    if step == "aurora":
        h, l, s = _rgb_to_hls(r, g, b)
        h = (h + 0.23 * math.sin(amount * math.tau)) % 1.0
        s = _clamp(max(s, 0.45 * amount) + (0.96 - s) * amount * 0.45)
        l = _clamp(0.24 + 0.56 * l + 0.12 * amount)
        nr, ng, nb = _hls_to_rgb(h, l, s)
        return (_clamp(nr), _clamp(ng), _clamp(nb))
    if step == "nectar":
        h, l, s = _rgb_to_hls(r, g, b)
        s = _clamp(s + (0.94 - s) * amount * 0.48)
        nr, ng, nb = _hls_to_rgb(h, l, s)
        t = amount * 0.28
        return (_clamp(nr + (1.0 - nr) * t),
                _clamp(ng + (0.58 - ng) * t * 0.75),
                _clamp(nb * (1.0 - t * 0.25)))
    if step == "glaze":
        best = 0
        best_d = None
        for i, name in enumerate(order):
            pr, pg, pb = PANTRY[name]
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if best_d is None or d < best_d:
                best_d = d
                best = i
        leap = max(1, len(order) // 3)
        nr, ng, nb = PANTRY[order[(best + leap) % len(order)]]
        t = amount * 0.46
        return (_clamp(r + (nr - r) * t),
                _clamp(g + (ng - g) * t),
                _clamp(b + (nb - b) * t))
    if step == "iridesce":
        ang = amount * math.tau * 0.61803398875
        ca = math.cos(ang)
        sa = math.sin(ang) * 0.5773502691896258
        s3 = (r + g + b) / 3.0
        nr = s3 + (r - s3) * ca + (g - b) * sa
        ng = s3 + (g - s3) * ca + (b - r) * sa
        nb = s3 + (b - s3) * ca + (r - g) * sa
        return (_clamp(nr), _clamp(ng), _clamp(nb))
    if step == "ember":
        h, l, s = _rgb_to_hls(r, g, b)
        s = _clamp(s + (0.98 - s) * amount * 0.58)
        l = _clamp(l * (1.0 - 0.18 * amount) + 0.08 * amount)
        nr, ng, nb = _hls_to_rgb(h, l, s)
        return (_clamp(nr * (1.0 + 0.14 * amount)), _clamp(ng), _clamp(nb))
    if step == "lagoon":
        h, l, s = _rgb_to_hls(r, g, b)
        s = _clamp(s + (0.96 - s) * amount * 0.52)
        nr, ng, nb = _hls_to_rgb(h, l, s)
        t = amount * 0.26
        return (_clamp(nr * (1.0 - t * 0.22)),
                _clamp(ng + (0.86 - ng) * t),
                _clamp(nb + (0.96 - nb) * t))
    return (r, g, b)


def cook(recipe):
    """Cook a recipe into a colour."""
    colour = mix(recipe['ingredients'])
    for step, amount in recipe['method']:
        colour = apply(colour, step, amount)
    return colour


def unit(course, salt, seed):
    h = (course * 374761393 + salt * 668265263 + int(seed * 1000003) * 1442695041) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFFFF) / float(0x1000000)


def first_ingredient(course, seed, stop):
    """First ingredient that recipe_for(course-1, ...) would pick."""
    order = _active_order()
    prev = course - 1
    salt = stop * 1000 + 0
    u = unit(prev, salt, seed)
    idx = int(u * len(order))
    return order[idx]


def recipe_for(course, seed, stop=0):
    """Build a recipe for the given course."""
    if not EXPANDED:
        order = PANTRY_BASE_ORDER
        salt = stop * 1000 + 100
        u = unit(course, salt, seed)
        n_ing = 2 + int(u * 3)
        ingredients = []
        if course > 0:
            heir = first_ingredient(course, seed, stop)
            ingredients.append((heir, 1))
        for k in range(n_ing):
            salt = stop * 1000 + k
            u = unit(course, salt, seed)
            idx = int(u * len(order))
            parts = 1 + int(unit(course, stop * 1000 + 1000 + k, seed) * 5)
            ingredients.append((order[idx], parts))
        if len(ingredients) > 4:
            ingredients = ingredients[:4]
        if len(ingredients) < 2:
            ingredients.append((order[0], 1))
        salt = stop * 1000 + 200
        u = unit(course, salt, seed)
        n_steps = 1 + int(u * 3)
        method = []
        for k in range(n_steps):
            salt = stop * 1000 + 300 + k
            u = unit(course, salt, seed)
            name = BASE_STEPS[int(u * len(BASE_STEPS))]
            amt = 0.1 + unit(course, stop * 1000 + 400 + k, seed) * 0.8
            method.append((name, amt))
        return {'ingredients': ingredients, 'method': method}

    order = PANTRY_ORDER
    ingredients = []
    if course > 0:
        heir = first_ingredient(course, seed, stop)
        ingredients.append((heir, 1))

    use_sig = unit(course, stop * 1000 + 55, seed) < 0.58
    if use_sig:
        sig_idx = int(unit(course, stop * 1000 + 77, seed) * len(SIGNATURE_RECIPES)) % len(SIGNATURE_RECIPES)
        sig = SIGNATURE_RECIPES[sig_idx]
        for p_name, p_parts in sig['pair']:
            ingredients.append((p_name, p_parts))
        season_idx = int(unit(course, stop * 1000 + 0, seed) * len(order))
        season_parts = 1 + int(unit(course, stop * 1000 + 1000, seed) * 3)
        ingredients.append((order[season_idx], season_parts))
        method = []
        for k, s_name in enumerate(sig['steps']):
            amt = 0.18 + unit(course, stop * 1000 + 400 + k, seed) * 0.74
            method.append((s_name, amt))
        extra_step = EXPANDED_STEPS[int(unit(course, stop * 1000 + 305, seed) * len(EXPANDED_STEPS))]
        extra_amt = 0.12 + unit(course, stop * 1000 + 405, seed) * 0.76
        method.append((extra_step, extra_amt))
        return {'ingredients': ingredients[:4], 'method': method, 'archetype': sig['name']}

    salt = stop * 1000 + 100
    u = unit(course, salt, seed)
    n_ing = 2 + int(u * 2)
    for k in range(n_ing):
        salt = stop * 1000 + k
        u = unit(course, salt, seed)
        idx = int(u * len(order))
        parts = 1 + int(unit(course, stop * 1000 + 1000 + k, seed) * 5)
        ingredients.append((order[idx], parts))
    if len(ingredients) > 4:
        ingredients = ingredients[:4]
    if len(ingredients) < 2:
        ingredients.append((order[0], 1))
    salt = stop * 1000 + 200
    u = unit(course, salt, seed)
    n_steps = 2 + int(u * 3)
    method = []
    for k in range(n_steps):
        salt = stop * 1000 + 300 + k
        u = unit(course, salt, seed)
        name = EXPANDED_STEPS[int(u * len(EXPANDED_STEPS))]
        amt = 0.14 + unit(course, stop * 1000 + 400 + k, seed) * 0.78
        method.append((name, amt))
    return {'ingredients': ingredients, 'method': method}


def ring(course, seed, stops=6):
    return [cook(recipe_for(course, seed, stop)) for stop in range(stops)]


if __name__ == "__main__":
    def _hex(c):
        r, g, b = c
        return "#{:02x}{:02x}{:02x}".format(int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
    print([_hex(c) for c in ring(0, 0.5, 12)])
    print([_hex(c) for c in ring(1, 0.5, 12)])
    print("same recipe, same colour" if ring(7, 0.25) == ring(7, 0.25) else "DIFF")
