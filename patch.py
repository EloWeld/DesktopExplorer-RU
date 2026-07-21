#!/usr/bin/env python3
"""Russian localisation patcher for Desktop Explorer — command line interface.

Patches YOUR OWN copy of the game in place. No game assets are shipped with
this tool: the fonts and string tables are read out of your installation,
modified, and written back. Originals are backed up first.

    python3 patch.py                      # autodetect the game
    python3 patch.py --game "/path/to/Desktop Explorer"
    python3 patch.py --restore            # undo everything
    python3 patch.py --status             # is it installed?

For the guided version, run deru.py instead.

Requires: UnityPy, fontTools, lz4, Pillow   (pip install -r requirements.txt)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import patcher                                        # noqa: E402
import state                                          # noqa: E402
import steam                                          # noqa: E402
from errors import DeruError                          # noqa: E402
from version import VERSION                           # noqa: E402


class PlainReporter(patcher.Reporter):
    """Line-per-step progress, the way this script has always printed it."""

    def step(self, key, title):
        print(f"{title}...")

    def ok(self, detail=""):
        print(f"  {detail}" if detail else "  готово")

    def note(self, text):
        print(f"    {text}")

    def warn(self, text):
        print(f"  ! {text}")


def main():
    ap = argparse.ArgumentParser(
        description="Русификатор Desktop Explorer (командная строка)")
    ap.add_argument("--game", help="папка с игрой, если она не найдена сама")
    ap.add_argument("--restore", action="store_true", help="вернуть игру к оригиналу")
    ap.add_argument("--status", action="store_true", help="показать состояние и выйти")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args()

    try:
        game = steam.find_game(args.game)
        layout = steam.locate(game)
        print(f"игра:      {game}")
        print(f"платформа: {os.path.basename(layout.plat)}")

        if args.status:
            print(f"состояние: {state.status(layout).label()}")
            return 0

        rep = PlainReporter()
        if args.restore:
            patcher.restore(layout, rep)
            print("\nГотово. Игра вернулась к исходному состоянию.")
            return 0

        if steam.is_running():
            print("! игра сейчас запущена — закройте её и повторите", file=sys.stderr)
            return 1

        result = patcher.install(layout, rep)
        print("\nГотово." + ("" if result["auto_language"]
                             else " В игре: Options → Language → Русский язык"))
        print("Откатить: python3 patch.py --restore")
        return 0

    except DeruError as err:
        print(f"\nОшибка: {err.message}", file=sys.stderr)
        if err.hint:
            print(err.hint, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nПрервано.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
