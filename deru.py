#!/usr/bin/env python3
"""Русификатор Desktop Explorer — мастер установки.

Тот же патчер, что и в patch.py, только с меню, подсказками и понятными
ошибками. Это точка входа собранного приложения: игрок запускает один файл и
дальше отвечает на вопросы.
"""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from rich.console import Console                      # noqa: E402
from rich.panel import Panel                          # noqa: E402
from rich.prompt import Confirm, Prompt               # noqa: E402
from rich.table import Table                          # noqa: E402
from rich.text import Text                            # noqa: E402

import patcher                                        # noqa: E402
import state                                          # noqa: E402
import steam                                          # noqa: E402
from errors import DeruError, GameNotFound            # noqa: E402
from version import VERSION                           # noqa: E402
from wizard import WizardReporter                     # noqa: E402

# Необязательные надстройки мастера (локальный мод хоткеев) подключаются из
# mod/installer, который не коммитится и в релизные сборки не входит. Если
# папки нет, hkmod равен None и мастер работает без дополнительных пунктов.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "mod", "installer"))
try:
    import deru_hotkeys as hkmod                      # noqa: E402
except ImportError:
    hkmod = None

ISSUES = "https://github.com/EloWeld/DesktopExplorer-RU/issues"

WARNINGS = [
    "Русский язык занимает место испанского — пятый слот в игру добавить нельзя.",
    "После обновления игры в Steam перевод слетает: запустите русификатор заново.",
    "Оригиналы сохраняются рядом с игрой, откатить можно в любой момент — пункт 2.",
    "Перевод машинный и не вычитан, часть текста намеренно оставлена английской.",
]


def header(console, game, status, hk_status=None):
    """The panel at the top: where the game is and what state it is in."""
    body = Table.grid(padding=(0, 2))
    body.add_column(style="dim", justify="right")
    body.add_column()
    body.add_row("Игра:", game or "[yellow]не найдена[/]")
    if status is None:
        dot, style = "○", "yellow"
    elif status.installed:
        dot, style = "●", "green"
    elif status.stale:
        dot, style = "●", "yellow"
    else:
        dot, style = "○", "cyan"
    label = status.label() if status else "укажите папку с игрой"
    body.add_row("Перевод:", f"[{style}]{dot}[/] {label}")
    if hk_status is not None and hkmod is not None:
        hkmod.header_row(body, hk_status)
    console.print(Panel(body, title=f"Desktop Explorer — русификатор  v{VERSION}",
                        title_align="left", border_style="cyan"))


def menu(console, game, status, hk_status=None):
    """Draw the menu and return the chosen action key."""
    items = []
    if game and status is not None:
        if status.installed:
            items.append(("reinstall", "Переустановить перевод"))
        else:
            items.append(("install", "Установить русский язык"))
        if status.installed or status.stale:
            items.append(("restore", "Удалить русификатор (вернуть как было)"))
    if hkmod is not None:
        items.extend(hkmod.menu_items(game, hk_status))
    items.append(("path", "Указать папку с игрой вручную"))
    items.append(("quit", "Выход"))

    console.print()
    for i, (_, title) in enumerate(items, 1):
        console.print(f"  [bold cyan]{i}[/]  {title}")
    console.print()
    choice = Prompt.ask("  Выбор", choices=[str(i) for i in range(1, len(items) + 1)],
                        default="1", show_choices=False)
    return items[int(choice) - 1][0]


def ask_path(console):
    """Ask for the game folder. Dragging it into the terminal is the easy way."""
    console.print()
    console.print("  [dim]Перетащите папку с игрой прямо в это окно — "
                  "путь подставится сам.[/]")
    console.print("  [dim]Пустая строка — вернуться в меню.[/]")
    raw = Prompt.ask("  Папка", default="", show_default=False)
    return steam.clean_path(raw) if raw.strip() else None


def show_warnings(console):
    body = Text()
    for line in WARNINGS:
        body.append("• ", style="cyan")
        body.append(line + "\n")
    console.print()
    console.print(Panel(body, title="Перед установкой", title_align="left",
                        border_style="yellow"))
    return Confirm.ask("  Продолжить?", default=True)


def run_install(console, layout, log):
    if steam.is_running():
        console.print()
        console.print("  [yellow]Игра сейчас запущена.[/] Закройте её и повторите — "
                      "патчить файлы под работающей игрой нельзя.")
        return
    if not show_warnings(console):
        return
    console.print()
    rep = WizardReporter(console, log)
    try:
        result = patcher.install(layout, rep)
    finally:
        rep.close()
    tail = ("Игра запустится сразу на русском."
            if result["auto_language"]
            else "В игре выберите: Options → Language → Русский язык.")
    console.print()
    console.print(Panel(f"Перевод установлен. {tail}",
                        title="Готово", title_align="left", border_style="green"))


def run_restore(console, layout, log):
    console.print()
    if not Confirm.ask("  Вернуть игру к оригиналу?", default=False):
        return
    console.print()
    rep = WizardReporter(console, log)
    try:
        patcher.restore(layout, rep)
    finally:
        rep.close()
    console.print()
    console.print(Panel("Игра вернулась к исходному состоянию.",
                        title="Готово", title_align="left", border_style="green"))


def resolve(game):
    """Layout and status for a game folder, or (None, None) if it is unusable."""
    if not game:
        return None, None
    layout = steam.locate(game)
    return layout, state.status(layout)


def parse_args(argv):
    import argparse
    ap = argparse.ArgumentParser(
        prog="deru", description="Русификатор Desktop Explorer")
    ap.add_argument("--game", help="папка с игрой, если она не найдена сама")
    ap.add_argument("--version", action="version", version=VERSION)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    console = Console()
    log_path = os.path.join(tempfile.gettempdir(), "desktop-explorer-ru.log")
    log = open(log_path, "w", encoding="utf-8")
    log.write(f"Desktop Explorer RU v{VERSION}\n")

    game = layout = status = None
    try:
        game = steam.find_game(args.game)
    except GameNotFound:
        pass

    try:
        while True:
            problem = None
            hk_layout = hk_status = None
            if game:
                try:
                    layout, status = resolve(game)
                except DeruError as err:
                    problem, game, layout, status = err, None, None, None
                else:
                    hk_layout, hk_status = (hkmod.resolve(game)
                                            if hkmod is not None else (None, None))

            console.clear()
            header(console, game, status, hk_status)
            if problem is not None:
                console.print(f"  [yellow]{problem.message}[/]")
                if problem.hint:
                    console.print(f"  [dim]{problem.hint}[/]")

            action = menu(console, game, status, hk_status)
            if action == "quit":
                return 0
            if action == "path":
                picked = ask_path(console)
                if picked:
                    game = picked
                continue

            try:
                if action in ("install", "reinstall"):
                    run_install(console, layout, log)
                elif action == "restore":
                    run_restore(console, layout, log)
                elif hkmod is not None and hkmod.handle(action, console, hk_layout, log):
                    pass
            except DeruError as err:
                console.print()
                console.print(Panel(f"{err.message}\n\n[dim]{err.hint or ''}[/]",
                                    title="Не получилось", title_align="left",
                                    border_style="red"))

            console.print()
            Prompt.ask("  [dim]Enter — в меню[/]", default="", show_default=False)

    except KeyboardInterrupt:
        console.print("\n  Прервано.")
        return 130
    except Exception:                                  # noqa: BLE001 — last resort
        log.write("\n" + traceback.format_exc())
        log.flush()
        console.print()
        console.print(Panel(
            f"Непредвиденная ошибка. Подробности записаны в файл:\n{log_path}\n\n"
            f"Пожалуйста, приложите его к сообщению об ошибке:\n{ISSUES}",
            title="Ошибка", title_align="left", border_style="red"))
        try:
            Prompt.ask("  [dim]Enter — выход[/]", default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            pass
        return 1
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
