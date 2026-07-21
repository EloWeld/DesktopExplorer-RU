"""Finding the player's copy of Desktop Explorer and reading its layout.

Steam installs games into library folders that are not necessarily the default
one — a second drive, an external disk, a custom path. The list of those
folders lives in steamapps/libraryfolders.vdf inside every Steam root, so the
search reads it instead of guessing at three hardcoded paths.
"""
import os
import re
import sys

from errors import GameLayoutError, GameNotFound

GAME = "Desktop Explorer"
DLL = "Assembly-CSharp.dll"
CATALOG = "catalog.json"
IMAGES_EN = "localization-assets-english(unitedstates)(en-us)_assets_all"

# Steam's own installation, per platform. The library folders it knows about
# are read out of each of these; this list only has to find Steam itself.
STEAM_ROOTS = [
    "~/Library/Application Support/Steam",        # macOS
    "~/.steam/steam",                             # Linux
    "~/.local/share/Steam",                       # Linux (flatpak-ish layouts)
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
    "C:/Program Files (x86)/Steam",               # Windows
    "C:/Program Files/Steam",
]


def _steam_roots():
    return [p for p in (os.path.expanduser(r) for r in STEAM_ROOTS) if os.path.isdir(p)]


def _library_paths(steam_root):
    """Library folder paths declared in a Steam root's libraryfolders.vdf.

    The file is Valve's KeyValues format; every library is an object with a
    "path" key. Matching that key directly is enough and survives the format
    changes between Steam client versions, which have moved the surrounding
    structure around more than once.
    """
    vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    paths = [steam_root]
    try:
        with open(vdf, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return paths
    for raw in re.findall(r'"path"\s*"([^"]+)"', text):
        # Windows paths are written with escaped separators: D:\\SteamLibrary
        paths.append(raw.replace("\\\\", "\\"))
    return paths


def candidates():
    """Every plausible game folder, in the order they should be tried."""
    out, seen = [], set()
    for root in _steam_roots():
        for lib in _library_paths(root):
            path = os.path.join(lib, "steamapps", "common", GAME)
            if path not in seen:
                seen.add(path)
                out.append(path)
    return out


def clean_path(raw):
    """Turn what a player pasted into a usable path.

    Dropping a folder onto a macOS terminal pastes it shell-escaped —
    /Users/me/Library/Application\\ Support/... — and copying from Finder's
    "Copy as Pathname" wraps it in quotes. shlex undoes both, but only where
    the backslash is an escape character: on Windows it is a path separator,
    so there the string is taken as typed minus any surrounding quotes.
    """
    text = raw.strip()
    if not text:
        return ""
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]

    # A path is not a shell word: "Desktop Explorer" contains a space that is
    # meant literally, and unescaping it would cut the path in half. So the
    # unescaped reading is only a candidate, tried after the literal one and
    # only when a backslash suggests an escape was involved at all.
    readings = [text]
    if sys.platform != "win32" and "\\" in text:
        import shlex
        try:
            parts = shlex.split(text)
            if parts:
                readings.append(parts[0])
        except ValueError:                # unbalanced quote — leave it be
            pass

    def tidy(value):
        value = os.path.expanduser(value)
        return value.rstrip(os.sep) or os.sep

    for reading in readings:
        if os.path.exists(os.path.expanduser(reading)):
            return tidy(reading)
    return tidy(readings[-1])


def find_game(explicit=None):
    """Locate the game folder, or raise GameNotFound.

    An explicit path is taken at face value beyond existing — the player knows
    where their game is, and a layout problem is reported later by locate()
    with a far more specific message than "not found".
    """
    if explicit:
        path = clean_path(explicit)
        if not os.path.isdir(path):
            raise GameNotFound(
                f"Папки нет: {path}",
                hint="Проверьте путь или выберите папку с игрой заново.")
        return path
    for path in candidates():
        if os.path.isdir(path):
            return path
    raise GameNotFound(
        "Не удалось найти Desktop Explorer в библиотеках Steam.",
        hint="Укажите папку с игрой вручную — её можно перетащить сюда из Finder.")


class Layout:
    """Where the files this patcher touches live inside a game folder.

    game     — the installation root
    aa       — the Addressables folder holding catalog.json
    plat     — the StandaloneXxx folder inside it, holding the bundles
    managed  — the folder holding Assembly-CSharp.dll
    images   — file name of the English artwork bundle (it carries a hash)
    backup   — where originals are kept
    """

    def __init__(self, game, aa, plat, managed, images):
        self.game = game
        self.aa = aa
        self.plat = plat
        self.managed = managed
        self.images = images
        self.backup = os.path.join(game, "_ru_backup_original")

    @property
    def catalog(self):
        return os.path.join(self.aa, CATALOG)

    def bundle(self, name):
        return os.path.join(self.plat, name)


def locate(game):
    """Read a game folder's layout, or raise GameLayoutError.

    Walking is deliberate: the Addressables and Managed folders sit at
    different depths on macOS (inside the .app) and on Windows, and a walk
    finds both without a per-platform table that would rot.
    """
    if not os.path.isdir(game):
        raise GameNotFound(f"Папки нет: {game}")

    aa = plat = managed = None
    for root, dirs, files in os.walk(game):
        base = os.path.basename(root)
        if base == "Managed" and DLL in files:
            managed = root
        elif base == "aa" and CATALOG in files:
            standalone = sorted(d for d in dirs if d.startswith("Standalone"))
            if standalone:
                aa, plat = root, os.path.join(root, standalone[0])
        if aa and managed:
            break

    if aa is None:
        raise GameLayoutError(
            "В этой папке нет файлов локализации Desktop Explorer.",
            hint="Убедитесь, что выбрана папка самой игры, а не ярлык и не папка Steam.")
    if managed is None:
        raise GameLayoutError(
            "В папке игры не найден Assembly-CSharp.dll.",
            hint="Возможно, установка повреждена — помогает «Проверить целостность файлов» в Steam.")

    images = None
    for name in sorted(os.listdir(plat)):
        if name.startswith(IMAGES_EN) and name.endswith(".bundle"):
            images = name
            break
    if images is None:
        raise GameLayoutError(
            "Не найден бандл с английской графикой — версия игры не та, что ожидает патчер.",
            hint="Обновите русификатор: возможно, для новой версии игры уже есть свежая сборка.")

    return Layout(game, aa, plat, managed, images)


def is_running():
    """True when a Desktop Explorer process appears to be running.

    Patching bundles under a running player is how you get a half-read atlas
    and a confusing crash, so the wizard checks first. Best-effort by design:
    on any platform where the probe fails we return False and let the patch
    proceed rather than blocking on a failed subprocess call.
    """
    import subprocess
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist"], capture_output=True, text=True,
                                 timeout=10, errors="replace").stdout
            return "DesktopExplorer" in out.replace(" ", "")
        out = subprocess.run(["ps", "-Ao", "command"], capture_output=True,
                             text=True, timeout=10, errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for line in out.splitlines():
        if GAME in line and "_ru_backup_original" not in line:
            return True
    return False
