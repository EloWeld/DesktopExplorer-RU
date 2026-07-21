"""Errors we can explain to a player in plain language.

Anything raised as one of these is a situation we anticipated: the message is
meant to be shown as-is, in Russian, with no traceback. Everything else is a
bug and gets logged.
"""


class DeruError(Exception):
    """Base class for expected, explainable failures."""

    def __init__(self, message, hint=None):
        super().__init__(message)
        self.message = message
        self.hint = hint       # what the player can do about it, one line


class GameNotFound(DeruError):
    """No Desktop Explorer installation could be located."""


class GameLayoutError(DeruError):
    """The folder is not a Desktop Explorer install, or its layout changed."""


class NoBackup(DeruError):
    """Restore was asked for but no backup exists."""


class NotWritable(DeruError):
    """The game folder cannot be written to."""


class GameRunning(DeruError):
    """The game is running; patching it now would be unsafe."""
