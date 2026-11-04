"""Read-only data for the standalone system bar; no task history or notification delivery."""
import configparser
import json
import os
import sqlite3
from pathlib import Path


def snapshot():
    from appearance_tokens import COLORS, TOPBAR_KEYS, RADII
    from lumen_i18n import language, tr
    from lumen_panel import applications
    from lumen_controls import snapshot as controls
    from lumen_notifications import snapshot as notifications
    from topbar_context import snapshot as operations

    config = configparser.ConfigParser(interpolation=None)
    config.read(Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'plasmarc')
    theme = config.get('Theme', 'name', fallback='org.lumen.graphite').removeprefix('org.lumen.')
    colors = COLORS.get(theme)
    palette = dict(zip(('window','base','alternate','text','button','border','muted','accent','onAccent'), colors)) if colors else None
    if palette:
        palette.update(zip(('key','inset','highlight','shadow','ring','ink'), TOPBAR_KEYS.get(theme, TOPBAR_KEYS['graphite'])))
        palette['radius'] = RADII.get(theme, 8)
    try:
        unread = notifications(wake=False)['unread']
        # The background Plasma host publishes the combined system/local count.
        host = configparser.ConfigParser(interpolation=None, strict=False)
        host.read(Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'plasma-org.kde.plasma.desktop-appletsrc')
        for section in host.sections():
            if host.get(section,'plugin',fallback='') == 'org.lumen.notificationhost':
                unread = host.getint(section+'[Configuration][General]','unread',fallback=unread)
                break
    except (OSError, ValueError, sqlite3.Error, configparser.Error):
        unread = None
    labels = json.loads(Path(__file__).with_name("translations").joinpath("en/topbar.json").read_text())
    return dict(version=1, language=language(), labels={key: tr(key) for key in labels}, apps=applications(), system=controls(),
                operations=operations(), unread=unread,
                palette=palette)
