"""Errors raised by game rules."""


class GameRuleError(Exception):
    """A command was rejected because it breaks a game rule.

    Use cases raise this (or a subclass) before emitting any event, so a
    rejected command leaves no trace in storage or the room. The message is
    safe to show to players.
    """


class GameNotFoundError(GameRuleError):
    """No game exists with the given id or room code."""
