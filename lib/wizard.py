"""Экранный прогресс мастера: чеклист со спиннером на текущем шаге.

Вынесено из deru.py, чтобы тот же репортёр могли использовать необязательные
надстройки мастера (например, локальный установщик хоткеев из mod/), не
импортируя сам deru.py.
"""
from rich.text import Text

import patcher


class WizardReporter(patcher.Reporter):
    """Progress as a checklist: a spinner on the running step, a tick behind it.

    Verbose detail (which atlas got repacked at what size) goes to the log file
    rather than the screen — it matters when something breaks and only then.
    """

    def __init__(self, console, log):
        self.console = console
        self.log = log
        self.status = None
        self.title = ""

    def step(self, key, title):
        self._stop()
        self.title = title
        self.log.write(f"\n== {title}\n")
        self.status = self.console.status(f"[cyan]{title}[/]", spinner="dots")
        self.status.start()

    def ok(self, detail=""):
        self._stop()
        self.log.write(f"   ok: {detail}\n")
        line = Text("  ✓ ", style="green")
        line.append(f"{self.title:<22}", style="white")
        line.append(detail, style="dim")
        self.console.print(line)

    def note(self, text):
        self.log.write(f"   {text}\n")

    def warn(self, text):
        self.log.write(f"   ! {text}\n")
        self.console.print(f"  [yellow]![/] [dim]{text}[/]")

    def _stop(self):
        if self.status is not None:
            self.status.stop()
            self.status = None

    def close(self):
        self._stop()
