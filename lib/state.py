"""Is the translation installed, and is it still intact?

Three questions, three answers. The catalog is the ground truth for "is the
game patched right now"; the stamp left in the backup folder is the record of
"did we ever patch it". Disagreement between the two is the interesting case:
Steam updated the game and wiped the patch, which is the single most common
thing that happens to this mod and the one worth naming on screen.
"""
import base64
import json
import os

from patcher import read_stamp

CLEAN = "clean"           # never patched, or fully restored
INSTALLED = "installed"   # patched and intact
STALE = "stale"           # was patched, game files replaced since (Steam update)


class Status:
    def __init__(self, code, version=None):
        self.code = code
        self.version = version

    @property
    def installed(self):
        return self.code == INSTALLED

    @property
    def stale(self):
        return self.code == STALE

    def label(self):
        if self.code == INSTALLED:
            return f"перевод установлен, версия {self.version}" if self.version \
                else "перевод установлен"
        if self.code == STALE:
            return ("игра обновилась — перевод слетел; пока не поставить заново "
                    "или не удалить, игра может не запускаться")
        return "перевод не установлен"


# patcher.patch_catalog() zeroes each CRC and pads it with spaces to keep the
# entry's length; no build of the game writes a CRC that way
ZEROED_CRC = '"m_Crc":0 '.encode("utf-16-le")


def catalog_is_patched(catalog_path):
    """True when the Addressables catalog carries the zeroed CRCs we write.

    They live base64-encoded inside m_ExtraDataString, so the check decodes that
    blob rather than searching the JSON text. ru-RU keys used to be the sign,
    until 1.0.66 shipped its own ru-RU locale and every catalog got them.
    """
    try:
        with open(catalog_path, encoding="utf-8") as fh:
            cat = json.load(fh)
        blob = base64.b64decode(cat["m_ExtraDataString"])
    except (OSError, ValueError, KeyError):
        return False
    return ZEROED_CRC in blob


def status(layout):
    stamp = read_stamp(layout)
    patched = catalog_is_patched(layout.catalog)
    if patched:
        return Status(INSTALLED, (stamp or {}).get("version"))
    if stamp is not None and os.path.isdir(layout.backup):
        return Status(STALE, stamp.get("version"))
    return Status(CLEAN)
