"""Pre-bake glyphs into TextMesh Pro SDF atlases.

TMP renders a glyph's signed distance field on the main thread the first time
a character is displayed. A document full of fresh Cyrillic pays for ~70 such
renders in a single frame — the multi-second hitch on opening any file with
Russian text. Baking every glyph the translation uses at patch time removes
the hitch entirely: at runtime there is nothing left to add.

The atlas textures keep their shipped 1024x1024 size. The Bold atlas has
enough free space for the new glyphs; the Regular atlas does not, so it is
repacked completely at a smaller sampling size (72 pt instead of 90) — every
glyph, old and new, re-rendered and re-packed. SDF spread stays at 10 atlas
px (gradient scale 10), so on-screen sharpness is unchanged.

Calibrated against the glyphs the game itself shipped baked:
  - 0.001 * pointSize atlas px per font unit; metrics in 1/64 (FreeType 26.6)
  - padding 9, SDF spread = padding + 1 = 10 px
  - alpha(d) = clamp(127.5 + 12.75 * d), d = signed distance in atlas px
  - m_GlyphRect stores the tight box; m_UsedGlyphRects store it padded
"""
import io
import math

from fontTools.ttLib import TTFont

PAD = 9                    # atlas px of SDF padding around each glyph
SPREAD = PAD + 1           # SDF gradient half-width in atlas px
CELL = 40                  # font-unit grid on which most outline points sit


def q26_6(v):
    return round(v * 64) / 64


def _contours(glyf, name):
    """Absolute point lists per contour.

    getCoordinates resolves composites including their transforms — the
    game's Г and Я are mirrored copies of other letters, so offset-only
    resolution would place their outlines outside the bounding box.
    """
    g = glyf[name]
    if g.numberOfContours == 0 and not g.isComposite():
        return []
    coords, ends, _ = g.getCoordinates(glyf)
    out, start = [], 0
    for e in ends:
        out.append([tuple(p) for p in coords[start:e + 1]])
        start = e + 1
    return out


def _cell_for(contours):
    """Largest sampling cell that keeps the mask exact for this glyph.

    The game's glyphs sit on a 40-unit grid; a few shipped shapes (comma
    tails) use free-form coordinates and get a fine 5-unit grid, which
    bounds the approximation to ~1/16 of a game pixel.
    """
    m = 0
    for c in contours:
        for x, y in c:
            if x != int(x) or y != int(y):  # transformed composite points
                return 5
            m = math.gcd(math.gcd(m, abs(int(x))), abs(int(y)))
    for cell in (CELL, 20, 10):
        if m and m % cell == 0:
            return cell
    return 5


def _mask(contours, x0, y0, x1, y1, cell):
    """Even-odd fill sampled at cell centres -> grid of filled cells."""
    cols = max(1, -((x0 - x1) // cell))
    rows = max(1, -((y0 - y1) // cell))
    filled = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        py = y0 + (r + 0.5) * cell
        xs = []
        for c in contours:
            n = len(c)
            for i in range(n):
                ax, ay = c[i]
                bx, by = c[(i + 1) % n]
                if (ay > py) != (by > py):
                    xs.append(ax + (py - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            ca = max(0, int(math.ceil((xs[i] - x0) / cell - 0.5)))
            cb = min(cols - 1, int(math.floor((xs[i + 1] - x0) / cell - 0.5)))
            for c_ in range(ca, cb + 1):
                filled[r][c_] = True
    return filled


def _runs(filled, value, x0, y0, cell):
    """Horizontal runs of cells equal to `value`, as unit-coord rects."""
    rects = []
    for r, row in enumerate(filled):
        c = 0
        while c < len(row):
            if row[c] == value:
                s = c
                while c < len(row) and row[c] == value:
                    c += 1
                rects.append((x0 + s * cell, y0 + r * cell,
                              x0 + c * cell, y0 + (r + 1) * cell))
            else:
                c += 1
    return rects


def _dist(px, py, rects):
    best = 1e9
    for (rx0, ry0, rx1, ry1) in rects:
        dx = rx0 - px if px < rx0 else (px - rx1 if px > rx1 else 0.0)
        dy = ry0 - py if py < ry0 else (py - ry1 if py > ry1 else 0.0)
        d = math.hypot(dx, dy)
        if d < best:
            best = d
            if best == 0.0:
                return 0.0
    return best


class Baker:
    """Renders TTF glyphs the way Unity's FontEngine does."""

    def __init__(self, ttf_bytes, point_size):
        self.font = TTFont(io.BytesIO(ttf_bytes), fontNumber=0)
        self.glyf = self.font["glyf"]
        self.hmtx = self.font["hmtx"]
        self.cmap = self.font.getBestCmap()
        self.order = self.font.getGlyphOrder()
        self.scale = point_size / self.font["head"].unitsPerEm

    def glyph_id(self, ch):
        name = self.cmap.get(ord(ch))
        return (self.order.index(name), name) if name else (None, None)

    def metrics(self, name):
        g = self.glyf[name]
        adv, _ = self.hmtx[name]
        s = self.scale
        if g.numberOfContours == 0:
            return ({"m_Width": 0.0, "m_Height": 0.0,
                     "m_HorizontalBearingX": 0.0, "m_HorizontalBearingY": 0.0,
                     "m_HorizontalAdvance": q26_6(adv * s)}, 0, 0)
        w = int(math.ceil((g.xMax - g.xMin) * s))
        h = int(math.ceil((g.yMax - g.yMin) * s))
        return ({"m_Width": q26_6((g.xMax - g.xMin) * s),
                 "m_Height": q26_6((g.yMax - g.yMin) * s),
                 "m_HorizontalBearingX": q26_6(g.xMin * s),
                 "m_HorizontalBearingY": q26_6(g.yMax * s),
                 "m_HorizontalAdvance": q26_6(adv * s)}, w, h)

    def render(self, name, w, h):
        """Alpha rows (bottom-up) over the padded (w+2P)x(h+2P) box."""
        g = self.glyf[name]
        x0, y0, x1, y1 = g.xMin, g.yMin, g.xMax, g.yMax
        contours = _contours(self.glyf, name)
        cell = _cell_for(contours)
        filled = _mask(contours, x0, y0, x1, y1, cell)
        ink = _runs(filled, True, x0, y0, cell)
        holes = _runs(filled, False, x0, y0, cell)
        M = 10000
        holes += [(x0 - M, y0 - M, x1 + M, y0), (x0 - M, y1, x1 + M, y1 + M),
                  (x0 - M, y0, x0, y1), (x1, y0, x1 + M, y1)]
        upx = 1 / self.scale  # font units per atlas px
        cols_n, rows_n = len(filled[0]) if filled else 0, len(filled)
        rows = []
        for py in range(-PAD, h + PAD):
            row = bytearray()
            gy = y0 + (py + 0.5) * upx
            for px in range(-PAD, w + PAD):
                gx = x0 + (px + 0.5) * upx
                c_i = int((gx - x0) // cell)
                r_i = int((gy - y0) // cell)
                inside = (0 <= c_i < cols_n and 0 <= r_i < rows_n
                          and filled[r_i][c_i])
                if inside:
                    d = _dist(gx, gy, holes) * self.scale
                else:
                    d = -_dist(gx, gy, ink) * self.scale
                a = 127.5 + d * (255 / (2 * SPREAD))
                row.append(0 if a < 0 else (255 if a > 255 else int(a + 0.5)))
            rows.append(bytes(row))
        return rows


def _blit(img, aw, rows, x, y):
    bw = len(rows[0])
    for r_i, row in enumerate(rows):
        off = (y + r_i) * aw + x
        img[off:off + bw] = row


def repack(asset, tex, ttf_bytes, want, point_size, log=print):
    """Re-render and re-pack the whole atlas at `point_size` (size unchanged).

    Used when the shipped atlas has no room left: a smaller sampling size
    shrinks every glyph's footprint so old and new fit together in 1024x1024.
    """
    aw, ah = asset["m_AtlasWidth"], asset["m_AtlasHeight"]
    old_size = asset["m_FaceInfo"]["m_PointSize"]
    baker = Baker(ttf_bytes, point_size)

    # every character the asset already maps, plus the new ones
    charmap = {c["m_Unicode"]: c["m_GlyphIndex"]
               for c in asset["m_CharacterTable"]}
    for ch in sorted(want):
        if ord(ch) in charmap:
            continue
        gid, _ = baker.glyph_id(ch)
        if gid is not None:
            charmap[ord(ch)] = gid

    img = bytearray(aw * ah)
    glyph_table, used = [], []
    x = y = shelf = 0
    # tallest first: homogeneous shelves waste far less vertical space
    measured = []
    for gid in sorted(set(charmap.values())):
        name = baker.order[gid]
        measured.append((gid, name, baker.metrics(name)))
    measured.sort(key=lambda t: -t[2][2])
    for gid, name, (metrics, w, h) in measured:
        if w == 0:  # space and friends: metrics only, no rect
            glyph_table.append(
                {"m_Index": gid, "m_Metrics": metrics,
                 "m_GlyphRect": {"m_X": 0, "m_Y": 0, "m_Width": 0, "m_Height": 0},
                 "m_Scale": 1.0, "m_AtlasIndex": 0, "m_ClassDefinitionType": 0})
            continue
        bw, bh = w + 2 * PAD, h + 2 * PAD
        if x + bw > aw:
            x, y = 0, y + shelf
            shelf = 0
        if y + bh > ah:
            raise RuntimeError(f"atlas overflow at glyph {name}")
        _blit(img, aw, baker.render(name, w, h), x, y)
        glyph_table.append(
            {"m_Index": gid, "m_Metrics": metrics,
             "m_GlyphRect": {"m_X": x + PAD, "m_Y": y + PAD,
                             "m_Width": w, "m_Height": h},
             "m_Scale": 1.0, "m_AtlasIndex": 0, "m_ClassDefinitionType": 0})
        used.append({"m_X": x, "m_Y": y, "m_Width": bw, "m_Height": bh})
        x += bw
        shelf = max(shelf, bh)

    free = []
    if x < aw and shelf:
        free.append({"m_X": x, "m_Y": y, "m_Width": aw - x, "m_Height": shelf})
    if y + shelf < ah:
        free.append({"m_X": 0, "m_Y": y + shelf, "m_Width": aw,
                     "m_Height": ah - (y + shelf)})

    asset["m_GlyphTable"] = glyph_table
    asset["m_CharacterTable"] = [
        {"m_ElementType": 1, "m_Unicode": u, "m_GlyphIndex": gi, "m_Scale": 1.0}
        for u, gi in sorted(charmap.items())]
    asset["m_UsedGlyphRects"] = used
    asset["m_FreeGlyphRects"] = free

    # the whole face scales with the sampling size
    fi = asset["m_FaceInfo"]
    k = point_size / old_size
    for key, v in fi.items():
        if key in ("m_PointSize", "m_FamilyName", "m_StyleName", "m_Scale",
                   "m_UnitsPerEM", "m_FaceIndex",
                   "m_SuperscriptSize", "m_SubscriptSize"):  # ratios, not px
            continue
        if isinstance(v, (int, float)) and key.startswith("m_"):
            fi[key] = v * k
    fi["m_PointSize"] = point_size
    if "m_CreationSettings" in asset:
        asset["m_CreationSettings"]["pointSize"] = point_size

    tex["image data"] = bytes(img)
    tex["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
    log(f"  repacked {len(glyph_table)} glyphs at {point_size}pt "
        f"({len(asset['m_CharacterTable'])} characters)")
    return len(glyph_table)
