"""Exact native ripple painting with per-frame invariants and conservative culling.

Raster/ripple order and both post-passes are preserved from the frozen source.
No sqrt bounding spans, squared-distance substitution or collision-rule changes.
"""
import math
from fast_field import renderer_class as field_renderer

def renderer_class(ns):
    Base=field_renderer(ns)
    hashmix=ns['hashmix'];SPARKS=ns['SPARKS'];hsv_to_rgb=ns['hsv_to_rgb'];BLOCKS=ns['BLOCKS'];clamp01=ns['clamp01'];mix_rgb=ns['mix_rgb']
    def _paint_ripples(
        self,
        cells: list[list[tuple[str, tuple[int, int, int]]]],
        cols: int,
        rows: int,
        t: float,
    ) -> None:
        """Authority blocks, unauthority sparks, and residue marks share the field.

        A spark or a residue mark that would erase a block is stepped one cell
        aside. Residue is a dim dot or spark, slower than a keystroke block.
        Nothing is chosen as the real mark.
        """

        genome = self.genome
        rift = ns.get('_rift_center')
        fv = ns.get('flow_vector')
        flow = getattr(self, '_flow', None)
        flow_a = flow[2] if flow is not None else (fv(t)[2] if fv is not None else 0.0)
        ghosts: list[tuple[int, int, str, tuple[int, int, int]]] = []
        residue_marks: list[tuple[int, int, str, tuple[int, int, int]]] = []
        prepared = []
        for rip in self.ripples:
            radius = float(rip.get("r", 0.0))
            if radius < 0.0:
                continue
            kind = rip.get("auth")
            band = 1.7 if kind == "unauthority" else 1.25 if kind == "residue" else 0.48 if rip.get("amp") else 0.68
            fx = float(rip["fx"])
            fy = float(rip["fy"])
            cx, cy = rift(fx, fy, radius, flow_a, cols, rows) if rift is not None else (fx * cols, fy * rows)
            prepared.append((rip, cx, cy, radius, kind, band, math.nextafter(radius + band, math.inf)))
        if not prepared:
            return
        for y in range(rows):
            candidates = []
            for rip, cx, cy, radius, kind, band, outer in prepared:
                dy = (y - cy) * 2.0
                if not math.isfinite(dy) or not math.isfinite(outer) or abs(dy) <= outer:
                    candidates.append((rip, cx, dy, radius, kind, band, outer))
            for x in range(cols):
                auth_rip = None
                ghost_rip = None
                residue_rip = None
                crest_lift = 0
                crest_hot = 0.0
                for rip, cx, dy, radius, kind, band, outer in candidates:
                    dx = x - cx
                    if math.isfinite(dx) and math.isfinite(outer) and abs(dx) > outer:
                        continue
                    dist = math.hypot(dx, dy)
                    if dist < radius <= 2.6 and kind != "residue":
                        life = float(rip.get("life") or 0.0)
                        if kind == "unauthority":
                            glow = int(42.0 * clamp01((life - 0.5) / 0.5))
                            hot = (genome.g("hue") + 0.62) % 1.0
                        else:
                            glow = int(85.0 * clamp01((life - 0.55) / 0.45))
                            hot = (genome.g("hue") + 0.10) % 1.0
                        if glow > crest_lift:
                            crest_lift = glow
                            crest_hot = hot
                    if abs(dist - radius) < band:
                        if kind == "unauthority":
                            ghost_rip = rip
                        elif kind == "residue":
                            residue_rip = rip
                        else:
                            auth_rip = rip
                char, fg = cells[y][x]
                sparked = False
                if ghost_rip is not None:
                    flick = hashmix(x, y, int(t * 17) + int(float(ghost_rip["r"]) * 10))
                    if flick > 0.3:
                        spark = SPARKS[int(flick * 997) % len(SPARKS)]
                        ghost_fg = hsv_to_rgb((genome.g("hue") + 0.62) % 1.0, 0.14, 0.46)
                        if auth_rip is not None:
                            gx = x + 1 if x + 1 < cols else x - 1
                            if gx != x:
                                ghosts.append((gx, y, spark, ghost_fg))
                        else:
                            char = spark
                            fg = ghost_fg
                            sparked = True
                            if flick > 0.8:
                                gx = x + 1 if x + 1 < cols else x - 1
                                if gx != x:
                                    ghosts.append((gx, y, SPARKS[int(flick * 13) % len(SPARKS)], ghost_fg))
                if residue_rip is not None:
                    flick = hashmix(x, y, int(t * 9) + int(float(residue_rip["r"]) * 6))
                    mark = "·" if flick < 0.58 else SPARKS[int(flick * 997) % len(SPARKS)]
                    residue_fg = hsv_to_rgb((genome.g("hue") + 0.48) % 1.0, 0.16, 0.36)
                    if auth_rip is not None or sparked:
                        rx = x + 1 if x + 1 < cols else x - 1
                        if rx != x:
                            residue_marks.append((rx, y, mark, residue_fg))
                    else:
                        char = mark
                        fg = residue_fg
                if auth_rip is not None:
                    level = 3 if auth_rip.get("amp") else int(clamp01(float(auth_rip["life"])) * 3.99)
                    char = BLOCKS[max(0, min(3, level))]
                    sat = 0.95 if auth_rip.get("amp") else 0.8
                    fg = hsv_to_rgb((genome.g("hue") + 0.04) % 1.0, sat, 1.0)
                if crest_lift:
                    lum = max(fg)
                    if lum <= 168:
                        fg = (
                            min(255, fg[0] + crest_lift),
                            min(255, fg[1] + crest_lift),
                            min(255, fg[2] + crest_lift),
                        )
                    else:
                        w = clamp01((lum - 168) / 87.0) * (crest_lift / 85.0)
                        fg = mix_rgb(fg, hsv_to_rgb(crest_hot % 1.0, 0.95, 1.0), w)
                cells[y][x] = (char, fg)
        for gx, gy, gch, gfg in ghosts:
            if not (0 <= gx < cols and 0 <= gy < rows):
                continue
            if cells[gy][gx][0] in BLOCKS:
                nxt = gx + 1 if gx + 1 < cols else gx - 1
                if nxt != gx and cells[gy][nxt][0] not in BLOCKS:
                    gx = nxt
            cells[gy][gx] = (gch, gfg)
        for rx, ry, mch, mfg in residue_marks:
            if not (0 <= rx < cols and 0 <= ry < rows):
                continue
            if cells[ry][rx][0] in BLOCKS:
                nxt = rx + 1 if rx + 1 < cols else rx - 1
                if nxt != rx and cells[ry][nxt][0] not in BLOCKS:
                    rx = nxt
                else:
                    continue
            if cells[ry][rx][0] in BLOCKS:
                continue
            cells[ry][rx] = (mch, mfg)

    class RippleRenderer(Base):
        pass
    RippleRenderer._paint_ripples=_paint_ripples
    return RippleRenderer
