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
    from topbar_activity import snapshot as activity

    config = configparser.ConfigParser(interpolation=None)
    config.read(Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'plasmarc')
    theme = config.get('Theme', 'name', fallback='org.lumen.graphite').removeprefix('org.lumen.')
    colors = COLORS.get(theme)
    palette = dict(zip(('window','base','alternate','text','button','border','muted','accent','onAccent'), colors)) if colors else None
    if palette:
        palette.update(zip(('key','inset','highlight','shadow','ring','ink'), TOPBAR_KEYS.get(theme, TOPBAR_KEYS['graphite'])))
        palette['radius'] = RADII.get(theme, 8)
        # Controls inside a surface use a smaller corner than the surface itself.
        palette['innerRadius'] = round(palette['radius'] * 0.65)
    try:
        unread = notifications(wake=False)['unread']
        fresh = None
        # The background Plasma host publishes the combined system/local count.
        host = configparser.ConfigParser(interpolation=None, strict=False)
        host.read(Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'plasma-org.kde.plasma.desktop-appletsrc')
        for section in host.sections():
            if host.get(section,'plugin',fallback='') == 'org.lumen.notificationhost':
                # configparser keeps the inner brackets of Plasma's nested group names.
                group = section+'][Configuration][General'
                unread = host.getint(group,'unread',fallback=unread)
                # Hosts from before the count of new notices existed only publish the unread total.
                fresh = host.getint(group,'fresh',fallback=unread)
                break
    except (OSError, ValueError, sqlite3.Error, configparser.Error):
        unread = fresh = None
    labels = json.loads(Path(__file__).with_name("translations").joinpath("en/topbar.json").read_text())
    return dict(version=1, language=language(), labels={key: tr(key) for key in labels}, apps=applications(), system=controls(),
                operations=operations(), activity=activity(), unread=unread, fresh=unread if fresh is None else fresh,
                palette=palette)
