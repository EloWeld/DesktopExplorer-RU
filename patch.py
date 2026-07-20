#!/usr/bin/env python3
"""Russian localisation patcher for Desktop Explorer.

Patches YOUR OWN copy of the game in place. No game assets are shipped with
this tool: the fonts and string tables are read out of your installation,
modified, and written back. Originals are backed up first.

    python3 patch.py                      # autodetect the game
    python3 patch.py --game "/path/to/Desktop Explorer"
    python3 patch.py --restore            # undo everything

Requires: UnityPy, fontTools, lz4   (pip install -r requirements.txt)
"""
import argparse, copy, json, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

import UnityPy
from PIL import Image
from unityfs import Bundle, SerializedFile
from writer import rebuild_serialized, rebuild_bundle
from glyphs import G

CELL, XOFF = 80, 40

DEFAULT_PATHS = [
    "~/Library/Application Support/Steam/steamapps/common/Desktop Explorer",
    "~/.steam/steam/steamapps/common/Desktop Explorer",
    "C:/Program Files (x86)/Steam/steamapps/common/Desktop Explorer",
]

STRINGS = "localization-string-tables-spanish(mexico)(es-mx)_assets_all.bundle"
STRINGS_EN = "localization-string-tables-english(unitedstates)(en-us)_assets_all.bundle"
SHARED = "localization-assets-shared_assets_all.bundle"
LOCALES = "localization-locales_assets_all.bundle"
ASSET_TABLES = "localization-asset-tables-spanish(mexico)(es-mx)_assets_all.bundle"
ASSET_TABLES_EN = "localization-asset-tables-english(unitedstates)(en-us)_assets_all.bundle"
# the artwork bundle carries a content hash in its file name, so it is matched
# by prefix; the localized tables point at the textures inside it
IMAGES_EN = "localization-assets-english(unitedstates)(en-us)_assets_all"
ART = "art/reference/ru"
DLL = "Assembly-CSharp.dll"

# The game formats dates with the CultureInfo of the selected locale's code, so
# a locale that still says es-MX shows Spanish weekday names ("jueves"). The
# code is renamed to ru-RU everywhere it acts as an identifier. ru-RU and es-MX
# are the same length, which keeps every offset-indexed structure valid.
ES_CODE, RU_CODE = b"es-MX", b"ru-RU"


# --------------------------------------------------------------- game layout
def find_game(explicit):
    candidates = [explicit] if explicit else [os.path.expanduser(p) for p in DEFAULT_PATHS]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    sys.exit("Game folder not found. Pass it with --game \"/path/to/Desktop Explorer\"")


def find_managed(game):
    for root, dirs, files in os.walk(game):
        if os.path.basename(root) == "Managed" and DLL in files:
            return root
    sys.exit("Managed folder not found — is this really the game directory?")


def find_aa(game):
    for root, dirs, files in os.walk(game):
        if os.path.basename(root) == "aa" and "catalog.json" in files:
            plat = [d for d in dirs if d.startswith("Standalone")]
            if plat:
                return root, os.path.join(root, plat[0])
    sys.exit("Addressables folder not found — is this really the game directory?")


def find_images(plat):
    """File name of the English artwork bundle (it carries a content hash)."""
    for f in sorted(os.listdir(plat)):
        if f.startswith(IMAGES_EN) and f.endswith(".bundle"):
            return f
    sys.exit("English image bundle not found — is this really the game directory?")


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


def patch_shared(src, dst, bake_chars):
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
        src = font_by_pid[d["m_SourceFontFile"]["m_PathID"]]
        data = ttf.get(src)
        if data is None:
            raw = fonts[src][1]["m_FontData"]
            data = bytes(raw) if isinstance(raw, (bytes, bytearray)) else bytes(bytearray(raw))
        print(f"  {name}:")
        repack(d, texture_dict(d["m_AtlasTextures"][0]["m_PathID"]),
               data, bake_chars, point_size=72)

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
        sys.exit("no .resS node in the image bundle — game files changed?")
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
    FontAssets entries are kept: they carry the fonts the Cyrillic glyphs are
    baked into. Table ids are renamed to ru-RU like everywhere else.
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
        sys.exit("English ImageFiles table not found — game files changed?")

    b = Bundle(src)
    sf = SerializedFile(b.node_bytes(0))
    new_objects, renamed, swapped = {}, 0, 0
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
        new_objects[o["path_id"]] = _build_table(head, entries, tail)
    rebuild_bundle(b, 0, rebuild_serialized(sf, new_objects), dst)
    return renamed, swapped


def fix_saved_language(to_code):
    """Rewrite the saved language choice in the game's own settings file.

    The game boots with SetLanguageFromLocaleCode(saved code) and crashes with
    an unhandled IndexOutOfRange (black screen) when the saved code is missing
    from its hardcoded list, so the stored value must follow the rename in both
    directions: es-MX -> ru-RU on patch, back again on --restore.
    """
    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "Library/Application Support/Recurring Dream/DesktopExplorer"),
        os.path.join(home, "AppData/LocalLow/Recurring Dream/DesktopExplorer"),
        os.path.join(home, ".config/unity3d/Recurring Dream/DesktopExplorer"),
    ]
    from_code = b"es-MX" if to_code == b"ru-RU" else b"ru-RU"
    n = 0
    for root in roots:
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
            sys.exit(f"expected exactly one {old!r} in {os.path.basename(src)}, found {count}")
        data = data.replace(ob, nb)
        n += count
    open(dst, "wb").write(data)
    return n


# ----------------------------------------------------------------- catalog
def patch_catalog(src, dst):
    import base64, struct, re
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


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    game = find_game(args.game)
    aa, plat = find_aa(game)
    images = find_images(plat)
    backup = os.path.join(game, "_ru_backup_original")
    print(f"game:     {game}")
    print(f"platform: {os.path.basename(plat)}")

    managed = find_managed(game)

    if args.restore:
        if not os.path.isdir(backup):
            sys.exit("No backup found — nothing to restore.")
        shutil.copy(os.path.join(backup, "catalog.json"), os.path.join(aa, "catalog.json"))
        for f in (SHARED, STRINGS, LOCALES, ASSET_TABLES, images):
            if os.path.exists(os.path.join(backup, f)):
                shutil.copy(os.path.join(backup, f), os.path.join(plat, f))
        if os.path.exists(os.path.join(backup, DLL)):
            shutil.copy(os.path.join(backup, DLL), os.path.join(managed, DLL))
        n = fix_saved_language(ES_CODE)
        if n:
            print(f"saved language reverted to es-MX in {n} settings file(s)")
        print("restored to factory state.")
        return

    os.makedirs(backup, exist_ok=True)
    for path, name in ((os.path.join(aa, "catalog.json"), "catalog.json"),
                       (os.path.join(plat, SHARED), SHARED),
                       (os.path.join(plat, STRINGS), STRINGS),
                       (os.path.join(plat, LOCALES), LOCALES),
                       (os.path.join(plat, ASSET_TABLES), ASSET_TABLES),
                       (os.path.join(plat, images), images),
                       (os.path.join(managed, DLL), DLL)):
        if not os.path.exists(path):
            sys.exit(f"Missing game file: {path}")
        if not os.path.exists(os.path.join(backup, name)):
            shutil.copy(path, os.path.join(backup, name))
    print(f"backup:   {backup}")

    payload = json.load(open(os.path.join(HERE, "data/payload.json"), encoding="utf-8"))
    bake_chars = {ch for table in payload.values() for s in table.values()
                  for ch in s if ord(ch) >= 32}

    print("patching fonts...")
    n = patch_shared(os.path.join(backup, SHARED), os.path.join(plat, SHARED), bake_chars)
    print(f"  {n} objects rewritten")

    print("patching strings...")
    english = load_tables(os.path.join(plat, STRINGS_EN))  # never modified, read in place
    changed, rebased, added = patch_strings(os.path.join(backup, STRINGS),
                                            os.path.join(plat, STRINGS), payload, english)
    print(f"  {changed} strings translated, {rebased} rebased to English, {added} entries added")

    print("patching locale codes (es-MX -> ru-RU for Russian dates)...")
    n = patch_locale_codes(os.path.join(backup, LOCALES), os.path.join(plat, LOCALES))
    print(f"  {n} identifiers renamed")

    print("patching asset tables (Spanish images -> English)...")
    renamed, swapped = patch_asset_tables(os.path.join(backup, ASSET_TABLES),
                                          os.path.join(plat, ASSET_TABLES_EN),  # read in place
                                          os.path.join(plat, ASSET_TABLES))
    print(f"  {renamed} tables renamed, {swapped} images re-pointed at English art")

    art_dir = os.path.join(HERE, ART)
    if os.path.isdir(art_dir):
        print("patching images (English art -> Russian art)...")
        done, skipped, unused = patch_images(os.path.join(backup, images),
                                             os.path.join(plat, images), art_dir)
        print(f"  {len(done)} textures replaced")
        for name, why in skipped:
            print(f"  skipped {name}: {why}")
        for name in unused:
            print(f"  no such texture in the game: {name}")
    else:
        print(f"no {ART} folder — images left in English")

    print("patching language menu (Assembly-CSharp.dll)...")
    n = patch_dll(os.path.join(backup, DLL), os.path.join(managed, DLL))
    print(f"  {n} strings replaced")

    print("patching catalog...")
    n, rekeyed = patch_catalog(os.path.join(backup, "catalog.json"), os.path.join(aa, "catalog.json"))
    print(f"  {n} checksums cleared, {rekeyed} keys renamed to ru-RU")

    n = fix_saved_language(RU_CODE)
    if n:
        print(f"saved language switched to ru-RU in {n} settings file(s)")
        print("\nDone. The game will start in Russian.")
    else:
        print("\nDone. In game: Options -> Language -> Русский язык")
    print("Undo with: python3 patch.py --restore")


if __name__ == "__main__":
    main()
