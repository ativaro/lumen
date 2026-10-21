"""Conversation identifier validation used by native desktop activation."""
from lumen_i18n import tr


def session(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
        raise ValueError(tr('Ungültiges Gespräch.'))
    return value
