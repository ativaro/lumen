"""Read-only data for the standalone system bar; no task history or notification delivery."""
import configparser
import os
import sqlite3
from pathlib import Path


def snapshot():
    from appearance_tokens import COLORS
    from lumen_i18n import language
    from lumen_panel import applications
    from lumen_controls import snapshot as controls
    from lumen_notifications import snapshot as notifications
    from topbar_context import snapshot as operations

    config = configparser.ConfigParser(interpolation=None)
    config.read(Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'plasmarc')
    theme = config.get('Theme', 'name', fallback='org.lumen.graphite').removeprefix('org.lumen.')
    colors = COLORS.get(theme, COLORS['graphite'])
    window, base, alternate, text, button, border, muted, accent, on_accent = colors
    try:
        unread = notifications(wake=False)['unread']
    except (OSError, ValueError, sqlite3.Error):
        unread = None
    return dict(version=1, language=language(), apps=applications(), system=controls(),
                operations=operations(), unread=unread,
                palette=dict(window=window, base=base, alternate=alternate, text=text,
                             button=button, border=border, muted=muted, accent=accent,
                             onAccent=on_accent))
