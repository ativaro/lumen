"""Conflict-checked preference persistence shared by settings UI and MCP."""
from lumen_i18n import tr
from PySide6.QtCore import QSettings

# Deliberately excludes credentials, paths, auto-approval and privacy grants.
MCP_FIELDS = {
    'Assistant': {
        'uiLanguage': ('system', str, ('system','de','en')),
        'defaultMode': ('build', str, ('build','plan')),
        'appearance': ('glass', str, ('glass','graphite','atelier','midnight','clear','system')),
        'crashDetection': (True, bool, None),
    },
    'Files': {
        'restoreLastFolder': (True, bool, None), 'hidden': (False, bool, None),
        'previewVisible': (True, bool, None), 'documentWorkshopEnabled': (False, bool, None),
        'searchDelay': (250, int, (100,1500)), 'searchLimit': (5000, int, (100,50000)),
    },
}


def save_preferences(settings, values, expected):
    settings.sync()
    changes = {}
    for key, value in values.items():
        before = expected.get(key)
        if value != before:
            current = settings.value(key, before, type=type(before))
            if current != before and current != value:
                raise ValueError(tr('Diese Einstellung wurde in einem anderen Fenster geändert. Bitte die Einstellungen erneut öffnen.'))
            changes[key] = value
    for key, value in changes.items(): settings.setValue(key, value)
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError(tr('Einstellungen konnten nicht gespeichert werden.'))
    if changes:
        from lumen_history import record
        from lumen_store import Store
        record(Store(), tr('Lumen-Einstellungen angepasst'), 'preferences',
               {key:expected.get(key) for key in changes}, changes, settings.fileName())
    return list(changes)


def set_mcp_preference(settings, application, key, value, expected):
    field = MCP_FIELDS.get(application, {}).get(key)
    if field is None or key == 'appearance':
        raise ValueError('This preference is not writable through this tool. Use lumen_theme_set for appearance.')
    default, kind, choices = field
    if type(value) is not kind or type(expected) is not kind:
        raise ValueError('value and expected must have the preference type.')
    if choices and ((kind is int and not choices[0] <= value <= choices[1]) or
                    (kind is str and value not in choices)):
        raise ValueError('Unsupported preference value.')
    settings.sync()
    if settings.value(key, default, type=kind) != expected:
        raise ValueError('Preference changed. Read settings again before retrying.')
    return save_preferences(settings, {key:value}, {key:expected})
