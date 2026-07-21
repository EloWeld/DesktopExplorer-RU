"""Where the shipped data lives.

Run from a checkout, data/ and art/ sit next to the repository root. Run from
a PyInstaller one-file build, they are unpacked into a temporary directory
whose path is in sys._MEIPASS. Everything that reads a shipped file asks here
instead of computing a path from __file__.
"""
import os
import sys


def frozen():
    """True when running from a PyInstaller build rather than a checkout."""
    return getattr(sys, "frozen", False)


def root():
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def res(*parts):
    """Absolute path to a shipped resource, e.g. res("data", "payload.json")."""
    return os.path.join(root(), *parts)
