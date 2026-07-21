import base64
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

IMAGES = ("localization-assets-english(unitedstates)(en-us)_assets_all_"
          "deadbeefdeadbeefdeadbeef.bundle")


def write_catalog(path, patched):
    """A catalog.json shaped like the game's, with or without the ru-RU keys."""
    keys = b"\x05\x00\x00\x00ru-RU" if patched else b"\x05\x00\x00\x00es-MX"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"m_KeyDataString": base64.b64encode(keys).decode("ascii"),
                   "m_ExtraDataString": ""}, fh)


@pytest.fixture
def fake_game(tmp_path):
    """A directory tree with the pieces locate() looks for.

    Laid out the way a macOS install is — the Addressables and Managed folders
    buried inside the .app — so the walk has something realistic to find.
    """
    def build(name="Desktop Explorer", patched=False, stamp=None, images=IMAGES):
        game = tmp_path / name
        data = game / "Desktop Explorer.app" / "Contents" / "Resources" / "Data"
        plat = data / "StreamingAssets" / "aa" / "StandaloneOSX"
        managed = data / "Managed"
        plat.mkdir(parents=True)
        managed.mkdir(parents=True)
        (managed / "Assembly-CSharp.dll").write_bytes(b"MZ")
        if images:
            (plat / images).write_bytes(b"UnityFS")
        write_catalog(plat.parent / "catalog.json", patched)
        if stamp is not None:
            backup = game / "_ru_backup_original"
            backup.mkdir()
            (backup / ".deru.json").write_text(json.dumps(stamp), encoding="utf-8")
        return game
    return build


@pytest.fixture
def fake_steam(tmp_path, monkeypatch):
    """A Steam root whose libraryfolders.vdf points at a second library."""
    import steam

    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    other = tmp_path / "Elsewhere"
    (other / "steamapps" / "common").mkdir(parents=True)
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n'
        '\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n'
        '\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n' % (root, other),
        encoding="utf-8")
    monkeypatch.setattr(steam, "STEAM_ROOTS", [str(root)])
    return root, other
