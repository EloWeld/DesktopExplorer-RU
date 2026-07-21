"""Russian localisation patcher for Desktop Explorer — the patching itself.

Patches YOUR OWN copy of the game in place. No game assets are shipped with
this tool: the fonts and string tables are read out of the installation,
modified, and written back. Originals are backed up first.

Nothing here writes to the screen. Progress goes to a Reporter, so the same
code drives the plain command line, the wizard, and the tests.
"""
import copy
import json
import os
import shutil
import struct

import UnityPy
from PIL import Image

from errors import GameLayoutError, NoBackup, NotWritable
from glyphs import G
from resources import res
from unityfs import Bundle, SerializedFile
from version import VERSION
from writer import rebuild_bundle, rebuild_serialized

CELL, XOFF = 80, 40

STRINGS = "localization-string-tables-spanish(mexico)(es-mx)_assets_all.bundle"
STRINGS_EN = "localization-string-tables-english(unitedstates)(en-us)_assets_all.bundle"
SHARED = "localization-assets-shared_assets_all.bundle"
LOCALES = "localization-locales_assets_all.bundle"
ASSET_TABLES = "localization-asset-tables-spanish(mexico)(es-mx)_assets_all.bundle"
ASSET_TABLES_EN = "localization-asset-tables-english(unitedstates)(en-us)_assets_all.bundle"
ART = os.path.join("art", "reference", "ru")
DLL = "Assembly-CSharp.dll"

# translated strings live in data/payload.json; PAYLOAD_EXTRA holds the ones
# still awaiting a translation (value = the English original), kept apart so a
# hand-edit shows up as a readable diff instead of drowning in the big payload.
# It is merged on top of the main payload and may be absent entirely.
PAYLOAD = os.path.join("data", "payload.json")
PAYLOAD_EXTRA = os.path.join("data", "payload_additional.json")

# marker written into the backup folder: what patched this game, and when
STAMP = ".deru.json"

# The game formats dates with the CultureInfo of the selected locale's code, so
# a locale that still says es-MX shows Spanish weekday names ("jueves"). The
# code is renamed to ru-RU everywhere it acts as an identifier. ru-RU and es-MX
# are the same length, which keeps every offset-indexed structure valid.
ES_CODE, RU_CODE = b"es-MX", b"ru-RU"

# The terminal renders with bpdots.squares-bold SDF, whose typeface has no
# Cyrillic at all; those characters spill into TMP's global LiberationSans
# fallback — wrong (non-pixel) look, and its small dynamic atlas silently
# overflows, so late-arriving letters show as □. The Chinese locales solve
# this by localizing the console slot of the FontAssets table to their own
# pixel font; the Russian locale does the same with FSEX302, which is pixel,
# ships full Cyrillic and is pre-baked by this patcher anyway.
BPDOTS_GUID = "6fa24e3296f79437590fcbc512e87b4b"   # bpdots.squares-bold SDF
FSEX_GUID = "57886462b9e08456f9b6f3b12bf04d27"     # FSEX302 SDF

# The files the patch replaces, and therefore the files it must back up. The
# artwork bundle carries a content hash in its name, so it is added per install.
PATCHED_BUNDLES = (SHARED, STRINGS, LOCALES, ASSET_TABLES)

# Steps the install goes through, in order. The wizard renders one line per
# entry before any work starts, so the player sees the whole road up front.
STEPS = [
    ("backup", "резервная копия"),
    ("fonts", "шрифты"),
    ("strings", "строки"),
    ("locales", "коды локали"),
    ("tables", "таблицы ресурсов"),
    ("images", "картинки"),
    ("menu", "меню выбора языка"),
    ("catalog", "каталог ресурсов"),
    ("settings", "сохранённый язык"),
]


class Reporter:
    """Sink for progress. Subclasses print, draw, or collect."""

    def step(self, key, title):
        """A step is starting."""

    def ok(self, detail=""):
        """The current step finished, with an optional one-line result."""

    def note(self, text):
        """Secondary detail inside the current step."""

    def warn(self, text):
        """Something worth reading, but not fatal."""


# ------------------------------------------------------------------- fonts
def dilate(rows):
    out = []
    for line in rows:
        new = list(line) + ["."]
        for i, c in enumerate(line):
            if c == "#":
                new[i + 1] = "#"
        out.append("".join(new))
    return out


def build_glyph(top, rows):
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    pen = TTGlyphPen(None)
    for i, line in enumerate(rows):
        r, c = top - i, 0
        while c < len(line):
            if line[c] == "#":
                start = c
                while c < len(line) and line[c] == "#":
                    c += 1
                x0, x1 = XOFF + start * CELL, XOFF + c * CELL
                y0, y1 = r * CELL, (r + 1) * CELL
                pen.moveTo((x0, y0)); pen.lineTo((x0, y1))
                pen.lineTo((x1, y1)); pen.lineTo((x1, y0))
                pen.closePath()
            else:
                c += 1
    return pen.glyph()


def patch_ttf(data, bold):
    """Add the Cyrillic glyphs to a font extracted from the player's own game."""
    import io
    from fontTools.ttLib import TTFont
    font = TTFont(io.BytesIO(data), fontNumber=0)
    glyf, hmtx = font["glyf"], font["hmtx"]
    order = font.getGlyphOrder()
    cmaps = [t for t in font["cmap"].tables if t.isUnicode()]
    for ch, (top, adv, rows) in G.items():
        r, a = (dilate(rows), adv + 1) if bold else (rows, adv)
        name = "uni%04X" % ord(ch)
        glyf.glyphs[name] = build_glyph(top, r)
        if name not in order:
            order.append(name)
        hmtx.metrics[name] = (a * CELL, XOFF)
        for t in cmaps:
            t.cmap[ord(ch)] = name
    font.setGlyphOrder(order)
    font["maxp"].numGlyphs = len(order)
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def patch_shared(src, dst, bake_chars, rep):
    from prebake import repack
    env = UnityPy.load(src)
    b = Bundle(src)
    # the streamed-texture payload lives in the bundle's .resS node
    resS = b""
    for i, (_, _, _, name) in enumerate(b.nodes):
        if name.endswith(".resS"):
            resS = b.node_bytes(i)

    fonts, assets, textures = {}, {}, {}   # name/pid -> (obj, typetree dict)
    for obj in env.objects:
        if obj.type.name == "Font":
            d = obj.read_typetree()
            fonts[d.get("m_Name")] = (obj, d)
        elif obj.type.name == "Texture2D":
            textures[obj.path_id] = (obj, None)  # read lazily, they are big
        elif obj.type.name == "MonoBehaviour":
            try:
                d = obj.read_typetree()
            except Exception:
                continue
            if "m_CharacterTable" in d and "m_AtlasPopulationMode" in d:
                assets[d.get("m_Name")] = (obj, d)

    if "Windows Regular" not in fonts or "Windows Bold" not in fonts:
        raise GameLayoutError(
            "В шрифтах игры нет ожидаемых начертаний Windows Regular/Bold.",
            hint="Скорее всего, вышло обновление игры — нужна новая версия русификатора.")

    dirty = set()

    # 1. TTFs gain the Cyrillic glyphs
    ttf = {}
    for name in ("Windows Regular", "Windows Bold"):
        obj, d = fonts[name]
        raw = d["m_FontData"]
        raw = bytes(raw) if not isinstance(raw, (bytes, bytearray)) else raw
        ttf[name] = patch_ttf(raw, bold=(name == "Windows Bold"))
        d["m_FontData"] = list(ttf[name])
        dirty.add(name)

    def texture_dict(pid):
        obj, d = textures[pid]
        if d is None:
            d = obj.read_typetree()
            sd = d.get("m_StreamData") or {}
            if sd.get("size"):
                # non-readable textures stream their pixels from .resS and
                # keep no CPU copy; writing glyphs there crashes the player,
                # so pull the pixels inline before making anything readable
                d["image data"] = bytes(resS[sd["offset"]:sd["offset"] + sd["size"]])
                d["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
            textures[pid] = (obj, d)
        return d

    # 2. every font asset goes dynamic multi-atlas with a readable atlas
    for name, (obj, d) in assets.items():
        if d.get("m_AtlasPopulationMode") == 0:
            # only "Windows Regular SDF" ships static
            d["m_AtlasPopulationMode"] = 1
            d["m_SourceFontFile"] = {"m_FileID": 0,
                                     "m_PathID": fonts["Windows Regular"][0].path_id}
        if not d.get("m_IsMultiAtlasTexturesEnabled"):
            # baked atlases are near full; without this, adding a glyph to a
            # full atlas silently fails and the character shows as □
            d["m_IsMultiAtlasTexturesEnabled"] = 1
        if name == "Windows Monoline SDF":
            # the Monoline typeface itself is left without Cyrillic (used in
            # a handful of places) — fall back to Regular so text stays legible
            fb = d.setdefault("m_FallbackFontAssetTable", [])
            reg = assets["Windows Regular SDF"][0].path_id
            if all(f.get("m_PathID") != reg for f in fb):
                fb.append({"m_FileID": 0, "m_PathID": reg})
        for a in d.get("m_AtlasTextures") or []:
            if a.get("m_PathID"):
                td = texture_dict(a["m_PathID"])
                if not td.get("m_IsReadable"):
                    td["m_IsReadable"] = 1
        dirty.add(name)

    # 3. pre-bake the translation's characters so TMP never renders SDFs at
    #    runtime — that main-thread work is the freeze on opening documents.
    #    The shipped atlases have no room for ~70 more glyphs, so each asset
    #    is repacked wholesale at a smaller sampling size; the textures keep
    #    their original 1024x1024 dimensions. Skipped: Monoline (round-dot
    #    curves this rasteriser can't honour — it falls back to Regular) and
    #    bpdots (its typeface has no Cyrillic at all).
    font_by_pid = {o.path_id: n for n, (o, _) in fonts.items()}
    for name in ("Windows Regular SDF", "Windows Regular SDF_GLITCH",
                 "Windows Bold SDF", "Windows Bold Glitch VFX",
                 "Windows Bold SDF_Colorlens", "Windows Bold SDF_Tower",
                 "FSEX302 SDF"):
        obj, d = assets[name]
        src_font = font_by_pid[d["m_SourceFontFile"]["m_PathID"]]
        data = ttf.get(src_font)
        if data is None:
            raw = fonts[src_font][1]["m_FontData"]
            data = bytes(raw) if isinstance(raw, (bytes, bytearray)) else bytes(bytearray(raw))
        repack(d, texture_dict(d["m_AtlasTextures"][0]["m_PathID"]),
               data, bake_chars, point_size=72,
               log=lambda line, _n=name: rep.note(f"{_n}: {line.strip()}"))

    new_objects = {}
    for name in dirty:
        obj, d = (fonts | assets)[name]
        new_objects[obj.path_id] = obj.save_typetree(d)
    for pid, (obj, d) in textures.items():
        if d is not None:
            new_objects[pid] = obj.save_typetree(d)

    sf = SerializedFile(b.node_bytes(0))
    rebuild_bundle(b, 0, rebuild_serialized(sf, new_objects), dst)
    return len(new_objects)


# ------------------------------------------------------------------ images
def encode_texture(img, fmt, width, height, mips):
    """Compress a PIL image into a texture's own format and full mip chain.

    Same format, same dimensions and same number of mip levels means the encoded
    payload is exactly as long as the one it replaces, which is what lets the
    pixels be written straight into the bundle's .resS node.
    """
    from UnityPy.export.Texture2DConverter import image_to_texture2d
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    out = b""
    for lvl in range(max(1, mips)):
        w, h = max(1, width >> lvl), max(1, height >> lvl)
        out += image_to_texture2d(img if lvl == 0 else img.resize((w, h), Image.LANCZOS), fmt)[0]
    return out


def patch_images(src, dst, art_dir):
    """Bake the translated artwork over the English textures.

    The localized asset tables already point every image at the English asset,
    so replacing the pixels in that bundle is enough — no table, catalog or
    object layout changes. Textures with no Russian counterpart stay English.
    """
    art = {os.path.splitext(f)[0]: os.path.join(art_dir, f)
           for f in os.listdir(art_dir) if f.lower().endswith(".png")}
    b = Bundle(src)
    res_i = next((i for i, n in enumerate(b.nodes) if n[3].endswith(".resS")), None)
    if res_i is None:
        raise GameLayoutError(
            "В бандле с графикой нет узла .resS — файлы игры изменились.",
            hint="Скорее всего, вышло обновление игры — нужна новая версия русификатора.")
    resS = bytearray(b.node_bytes(res_i))

    env = UnityPy.load(src)
    done, skipped = [], []
    for obj in env.objects:
        if obj.type.name != "Texture2D":
            continue
        d = obj.read_typetree()
        name = d.get("m_Name")
        png = art.get(name)
        if not png:
            continue
        sd = d.get("m_StreamData") or {}
        if not sd.get("size"):
            skipped.append((name, "texture is not streamed"))
            continue
        data = encode_texture(Image.open(png), d["m_TextureFormat"],
                              d["m_Width"], d["m_Height"], d.get("m_MipCount", 1))
        if len(data) != sd["size"]:
            skipped.append((name, f"encoded {len(data)} B, slot is {sd['size']} B"))
            continue
        resS[sd["offset"]:sd["offset"] + sd["size"]] = data
        done.append(name)

    unused = sorted(set(art) - set(done) - {n for n, _ in skipped})
    rebuild_bundle(b, res_i, bytes(resS), dst)
    return done, skipped, unused


# ----------------------------------------------------------------- strings
def load_tables(path):
    """{table name: {int id: text}} from a string-tables bundle."""
    env = UnityPy.load(path)
    out = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        d = obj.read_typetree()
        if "m_TableData" not in d or not d.get("m_Name"):
            continue
        out[d["m_Name"].rsplit("_", 1)[0]] = {
            e["m_Id"]: e["m_Localized"] for e in d["m_TableData"]}
    return out


def patch_strings(src, dst, payload, english):
    """Rebuild the es-MX tables as English base + Russian overlay.

    payload:  {table name: {id: text}} — the Russian translation.
    english:  {table name: {int id: text}} — the player's own en-US tables.
    Everything not translated (file names, passwords, terminal commands) must
    read exactly as in English, or the puzzles stop matching player input —
    leaving the original Spanish text there would break them the same way.
    """
    env = UnityPy.load(src)
    new_objects, changed, rebased, added = {}, 0, 0, 0
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        d = obj.read_typetree()
        if "m_TableData" not in d or not d.get("m_Name"):
            continue
        name = d["m_Name"].rsplit("_", 1)[0]
        table = payload.get(name, {})
        en = english.get(name, {})
        if not table and not en:
            continue

        # the tables become the ru-RU locale's tables (see ES_CODE/RU_CODE note)
        renamed = False
        lid = d.get("m_LocaleId")
        if isinstance(lid, dict) and lid.get("m_Code") == "es-MX":
            lid["m_Code"] = "ru-RU"
            d["m_Name"] = d["m_Name"].replace("es-MX", "ru-RU")
            renamed = True

        rows = d["m_TableData"]
        template = copy.deepcopy(rows[0]) if rows else None
        seen, local = set(), 0
        for e in rows:
            seen.add(e["m_Id"])
            new = table.get(str(e["m_Id"]))
            if new is None:
                new = en.get(e["m_Id"])  # untranslated -> English, never Spanish
                if new is not None and new != e.get("m_Localized"):
                    rebased += 1
            elif new != e.get("m_Localized"):
                local += 1
            if new is not None and new != e.get("m_Localized"):
                e["m_Localized"] = new
        # entries the Spanish table lacks: first the translated ones...
        for sid, text in table.items():
            if int(sid) not in seen and template is not None:
                n = copy.deepcopy(template)
                n["m_Id"], n["m_Localized"] = int(sid), text
                rows.append(n)
                seen.add(int(sid))
                added += 1
        # ...then everything else the English table has
        for iid, text in en.items():
            if iid not in seen and template is not None:
                n = copy.deepcopy(template)
                n["m_Id"], n["m_Localized"] = iid, text
                rows.append(n)
                added += 1
        if local or rebased or added or renamed:
            new_objects[obj.path_id] = obj.save_typetree(d)
            changed += local

    b = Bundle(src)
    sf = SerializedFile(b.node_bytes(0))
    rebuild_bundle(b, 0, rebuild_serialized(sf, new_objects), dst)
    return changed, rebased, added


# ------------------------------------------------------------- locale codes
def patch_locale_codes(src, dst):
    """Rename es-MX -> ru-RU inside Locale/table objects of a bundle.

    Same-length in-place byte patch, so no object relayout is needed. The
    AssetBundle container object is skipped: its "Assets/..." paths must keep
    matching the untouched catalog internal ids and on-disk file names.
    """
    b = Bundle(src)
    node = bytearray(b.node_bytes(0))
    sf = SerializedFile(bytes(node))
    n = 0
    for o in sf.objects:
        start = sf.data_offset + o["byte_start"]
        chunk = bytes(node[start:start + o["byte_size"]])
        if ES_CODE not in chunk or b"Assets/" in chunk:
            continue
        n += chunk.count(ES_CODE)
        node[start:start + o["byte_size"]] = chunk.replace(ES_CODE, RU_CODE)
    rebuild_bundle(b, 0, bytes(node), dst)
    return n


def _table_parts(obj):
    """Split a localized-table object into (name, head, entries, tail).

    entries are (id, value, raw_metadata) triples; head covers everything up to
    and including the entry count, so rebuilding is head + entries + tail.
    """
    def rstr(p):
        n = struct.unpack_from("<I", obj, p)[0]
        e = p + 4 + n
        return obj[p + 4:e].decode("utf-8"), (e + 3) & ~3

    p = 28                                      # two PPtrs + m_Enabled
    name, p = rstr(p)
    _code, p = rstr(p)
    p += 12                                     # m_SharedData PPtr
    mcount = struct.unpack_from("<I", obj, p)[0]
    p += 4 + mcount * 8
    cnt = struct.unpack_from("<I", obj, p)[0]
    head = obj[:p + 4]
    p += 4
    entries = []
    for _ in range(cnt):
        sid = struct.unpack_from("<q", obj, p)[0]
        val, q = rstr(p + 8)
        emc = struct.unpack_from("<I", obj, q)[0]
        entries.append((sid, val, obj[q:q + 4 + emc * 8]))
        p = q + 4 + emc * 8
    return name, head, entries, obj[p:]


def _build_table(head, entries, tail):
    out = bytearray(head)
    for sid, val, meta in entries:
        out += struct.pack("<q", sid)
        vb = val.encode("utf-8")
        out += struct.pack("<I", len(vb)) + vb
        out += b"\0" * (-len(out) % 4)
        out += meta
    out += tail
    return bytes(out)


def patch_asset_tables(src, english, dst):
    """Rebuild the localized asset tables for the ru-RU locale.

    ImageFiles entries are re-pointed at the English textures — the Spanish
    ones have Spanish text baked into the pixels and there is no Russian art.
    FontAssets entries are kept (they carry the fonts the Cyrillic glyphs are
    baked into) except the console slot, which moves from bpdots to FSEX302
    (see BPDOTS_GUID). Table ids are renamed to ru-RU like everywhere else.
    """
    ben = Bundle(english)
    sfe = SerializedFile(ben.node_bytes(0))
    en_images = {}
    for o in sfe.objects:
        chunk = sfe.raw[sfe.data_offset + o["byte_start"]:
                        sfe.data_offset + o["byte_start"] + o["byte_size"]]
        if b"Assets/" in chunk:
            continue
        try:
            name, _, entries, _ = _table_parts(chunk)
        except (struct.error, UnicodeDecodeError, IndexError):
            continue
        if name.startswith("ImageFiles"):
            en_images = {sid: val for sid, val, _ in entries}
    if not en_images:
        raise GameLayoutError(
            "Не найдена английская таблица ImageFiles — файлы игры изменились.",
            hint="Скорее всего, вышло обновление игры — нужна новая версия русификатора.")

    b = Bundle(src)
    sf = SerializedFile(b.node_bytes(0))
    new_objects, renamed, swapped, refonted = {}, 0, 0, 0
    for o in sf.objects:
        chunk = sf.raw[sf.data_offset + o["byte_start"]:
                       sf.data_offset + o["byte_start"] + o["byte_size"]]
        if ES_CODE not in chunk or b"Assets/" in chunk:
            continue
        name, head, entries, tail = _table_parts(chunk)
        head = head.replace(ES_CODE, RU_CODE)
        renamed += 1
        if name.startswith("ImageFiles"):
            fixed = []
            for sid, val, meta in entries:
                tgt = en_images.get(sid, val)
                if tgt != val:
                    swapped += 1
                fixed.append((sid, tgt, meta))
            entries = fixed
        elif name.startswith("FontAssets"):
            fixed = []
            for sid, val, meta in entries:
                if val == BPDOTS_GUID:
                    val = FSEX_GUID
                    refonted += 1
                fixed.append((sid, val, meta))
            entries = fixed
        new_objects[o["path_id"]] = _build_table(head, entries, tail)
    rebuild_bundle(b, 0, rebuild_serialized(sf, new_objects), dst)
    return renamed, swapped, refonted


# ---------------------------------------------------------- saved settings
def settings_roots():
    home = os.path.expanduser("~")
    return [
        os.path.join(home, "Library/Application Support/Recurring Dream/DesktopExplorer"),
        os.path.join(home, "AppData/LocalLow/Recurring Dream/DesktopExplorer"),
        os.path.join(home, ".config/unity3d/Recurring Dream/DesktopExplorer"),
    ]


def fix_saved_language(to_code):
    """Rewrite the saved language choice in the game's own settings file.

    The game boots with SetLanguageFromLocaleCode(saved code) and crashes with
    an unhandled IndexOutOfRange (black screen) when the saved code is missing
    from its hardcoded list, so the stored value must follow the rename in both
    directions: es-MX -> ru-RU on patch, back again on --restore.
    """
    from_code = b"es-MX" if to_code == b"ru-RU" else b"ru-RU"
    n = 0
    for root in settings_roots():
        if not os.path.isdir(root):
            continue
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f != "generalSettings.json":
                    continue
                p = os.path.join(r, f)
                raw = open(p, "rb").read()
                if from_code in raw:
                    open(p, "wb").write(raw.replace(from_code, to_code))
                    n += 1
    return n


# --------------------------------------------------------------------- dll
def patch_dll(src, dst):
    """Point the hardcoded language menu at the renamed ru-RU locale.

    Both replacements are UTF-16 and byte-length-identical, so the #US heap
    offsets in the assembly stay valid.
    """
    data = open(src, "rb").read()
    n = 0
    for old, new in (("es-MX", "ru-RU"), ("Español Latam", "Русский язык ")):
        ob, nb = old.encode("utf-16-le"), new.encode("utf-16-le")
        assert len(ob) == len(nb)
        count = data.count(ob)
        if count != 1:
            raise GameLayoutError(
                f"В Assembly-CSharp.dll ожидалась одна строка {old!r}, найдено {count}.",
                hint="Скорее всего, вышло обновление игры — нужна новая версия русификатора.")
        data = data.replace(ob, nb)
        n += count
    open(dst, "wb").write(data)
    return n


# ----------------------------------------------------------------- catalog
def patch_catalog(src, dst):
    import base64
    import re
    cat = json.load(open(src, encoding="utf-8"))
    blob = base64.b64decode(cat["m_ExtraDataString"])
    out, i, n = bytearray(), 0, 0
    while i < len(blob):
        if i + 6 <= len(blob) and blob[i + 4:i + 6] == b"{\x00":
            ln = struct.unpack_from("<i", blob, i)[0]
            if 0 < ln <= len(blob) - i - 4:
                text = blob[i + 4:i + 4 + ln].decode("utf-16-le")
                # length must stay identical: catalog entries index this blob by offset
                new, k = re.subn(r'("m_Crc":)(\d+)',
                                 lambda m: m.group(1) + "0" + " " * (len(m.group(2)) - 1), text)
                n += k
                enc = new.encode("utf-16-le")
                out += struct.pack("<i", len(enc)) + enc
                i += 4 + ln
                continue
        out += blob[i:i + 1]
        i += 1
    cat["m_ExtraDataString"] = base64.b64encode(bytes(out)).decode("ascii")
    # re-key the es-MX addressables entries to ru-RU; keys are length-prefixed
    # and offset-indexed, and the codes are the same length. m_InternalIds keep
    # es-MX on purpose — they must match container paths inside the bundles.
    kd = base64.b64decode(cat["m_KeyDataString"])
    rekeyed = kd.count(ES_CODE)
    cat["m_KeyDataString"] = base64.b64encode(kd.replace(ES_CODE, RU_CODE)).decode("ascii")
    json.dump(cat, open(dst, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    return n, rekeyed


# ----------------------------------------------------------------- payload
def load_payload():
    """Main payload merged with the not-yet-translated extras.

    Both files map table name -> {string id: text}. Extras win on a collision:
    a string that was moved into payload.json but left behind here would
    otherwise silently revert to English.
    """
    payload = json.load(open(res(PAYLOAD), encoding="utf-8"))
    base = sum(len(t) for t in payload.values())
    extra_path = res(PAYLOAD_EXTRA)
    if not os.path.exists(extra_path):
        return payload, base, 0, []
    extra = json.load(open(extra_path, encoding="utf-8"))
    added, clashes = 0, []
    for table, rows in extra.items():
        target = payload.setdefault(table, {})
        for sid, text in rows.items():
            if sid in target:
                clashes.append(f"{table}/{sid}")
            target[sid] = text
            added += 1
    return payload, base, added, clashes


# ------------------------------------------------------------------ backup
def backup_files(layout):
    """(source path, name inside the backup) for every file the patch replaces."""
    pairs = [(layout.catalog, "catalog.json")]
    for name in PATCHED_BUNDLES + (layout.images,):
        pairs.append((layout.bundle(name), name))
    pairs.append((os.path.join(layout.managed, DLL), DLL))
    return pairs


def check_writable(layout):
    """Fail before touching anything if the install cannot be written to.

    On Windows the game often sits under Program Files, where writing needs an
    elevated process; on macOS an external drive can be mounted read-only.
    Either way the player deserves this as a sentence, not as an OSError from
    somewhere deep inside a bundle rebuild.
    """
    for path in (layout.plat, layout.aa, layout.managed, layout.game):
        if not os.access(path, os.W_OK):
            raise NotWritable(
                f"Нет прав на запись в папку игры: {path}",
                hint="Запустите русификатор от имени администратора "
                     "или переустановите игру в папку, доступную для записи.")


def write_stamp(layout, payload_size):
    """Record what patched this game, next to the originals it saved."""
    stamp = {"version": VERSION, "strings": payload_size}
    with open(os.path.join(layout.backup, STAMP), "w", encoding="utf-8") as fh:
        json.dump(stamp, fh, ensure_ascii=False, indent=1)


def read_stamp(layout):
    try:
        with open(os.path.join(layout.backup, STAMP), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------- install
def install(layout, rep=None):
    """Apply the Russian translation to the game described by `layout`."""
    rep = rep or Reporter()
    check_writable(layout)

    rep.step("backup", "резервная копия")
    os.makedirs(layout.backup, exist_ok=True)
    for path, name in backup_files(layout):
        if not os.path.exists(path):
            raise GameLayoutError(
                f"В игре нет файла, который нужен патчеру: {os.path.basename(path)}",
                hint="Помогает «Проверить целостность файлов» в Steam.")
        target = os.path.join(layout.backup, name)
        if not os.path.exists(target):
            shutil.copy(path, target)
    rep.ok(layout.backup)

    payload, base, extra, clashes = load_payload()
    for c in clashes:
        rep.warn(f"{c} есть в обоих файлах перевода — берётся дополнительный")
    bake_chars = {ch for table in payload.values() for s in table.values()
                  for ch in s if ord(ch) >= 32}

    rep.step("fonts", "шрифты")
    n = patch_shared(os.path.join(layout.backup, SHARED), layout.bundle(SHARED),
                     bake_chars, rep)
    rep.ok(f"{n} объектов перезаписано")

    rep.step("strings", "строки")
    english = load_tables(layout.bundle(STRINGS_EN))  # never modified, read in place
    changed, rebased, added = patch_strings(
        os.path.join(layout.backup, STRINGS), layout.bundle(STRINGS), payload, english)
    rep.ok(f"{changed} переведено, {rebased} возвращено к английскому, {added} добавлено")

    rep.step("locales", "коды локали")
    n = patch_locale_codes(os.path.join(layout.backup, LOCALES), layout.bundle(LOCALES))
    rep.ok(f"{n} идентификаторов переименовано")

    rep.step("tables", "таблицы ресурсов")
    renamed, swapped, refonted = patch_asset_tables(
        os.path.join(layout.backup, ASSET_TABLES),
        layout.bundle(ASSET_TABLES_EN),                # read in place
        layout.bundle(ASSET_TABLES))
    rep.ok(f"{renamed} таблиц, {swapped} картинок с английских, "
           f"{refonted} шрифт консоли → FSEX302")

    rep.step("images", "картинки")
    art_dir = res(ART)
    if os.path.isdir(art_dir):
        done, skipped, unused = patch_images(
            os.path.join(layout.backup, layout.images), layout.bundle(layout.images), art_dir)
        for name, why in skipped:
            rep.warn(f"пропущено {name}: {why}")
        for name in unused:
            rep.warn(f"в игре нет такой текстуры: {name}")
        rep.ok(f"{len(done)} текстур заменено")
    else:
        rep.ok("нет папки с русской графикой — картинки остались английскими")

    rep.step("menu", "меню выбора языка")
    n = patch_dll(os.path.join(layout.backup, DLL), os.path.join(layout.managed, DLL))
    rep.ok(f"{n} строк заменено")

    rep.step("catalog", "каталог ресурсов")
    n, rekeyed = patch_catalog(os.path.join(layout.backup, "catalog.json"), layout.catalog)
    rep.ok(f"{n} контрольных сумм обнулено, {rekeyed} ключей → ru-RU")

    rep.step("settings", "сохранённый язык")
    switched = fix_saved_language(RU_CODE)
    rep.ok("игра запустится сразу на русском" if switched
           else "выбрать в игре: Options → Language → Русский язык")

    write_stamp(layout, base + extra)
    return {"strings": base, "extra": extra, "auto_language": bool(switched)}


# ----------------------------------------------------------------- restore
def restore(layout, rep=None):
    """Put the game back exactly as Steam installed it."""
    rep = rep or Reporter()
    if not os.path.isdir(layout.backup):
        raise NoBackup(
            "Резервной копии нет — восстанавливать нечего.",
            hint="Если перевод всё же стоит, вернуть оригиналы поможет "
                 "«Проверить целостность файлов» в Steam.")
    check_writable(layout)

    rep.step("restore", "восстановление файлов")
    restored = 0
    catalog_backup = os.path.join(layout.backup, "catalog.json")
    if os.path.exists(catalog_backup):
        shutil.copy(catalog_backup, layout.catalog)
        restored += 1
    for name in PATCHED_BUNDLES + (layout.images,):
        saved = os.path.join(layout.backup, name)
        if os.path.exists(saved):
            shutil.copy(saved, layout.bundle(name))
            restored += 1
    saved_dll = os.path.join(layout.backup, DLL)
    if os.path.exists(saved_dll):
        shutil.copy(saved_dll, os.path.join(layout.managed, DLL))
        restored += 1
    rep.ok(f"{restored} файлов возвращено")

    rep.step("settings", "сохранённый язык")
    n = fix_saved_language(ES_CODE)
    rep.ok("выбор языка сброшен на испанский" if n else "менять было нечего")

    # the stamp is what tells "never patched" apart from "patched, then wiped
    # by a game update", so a deliberate uninstall has to clear it
    try:
        os.remove(os.path.join(layout.backup, STAMP))
    except OSError:
        pass
    return {"restored": restored}
