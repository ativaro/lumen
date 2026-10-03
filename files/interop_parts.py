"""Content-checked references to native list entries, without persisted list IDs."""
import hashlib
import json
import re

from lumen_i18n import tr


FIELDS = {
    'resource': ('kind', 'title', 'target'),
    'question': ('text',),
    'segment': ('text', 'start', 'end'),
    'result': ('kind', 'text'),
    'source': ('title', 'text', 'url'),
    'rule': ('app', 'title', 'volume', 'mute', 'sink', 'role'),
}


def fingerprint(kind, value):
    content = {field: value.get(field, '') for field in FIELDS[kind]}
    if kind == 'result':
        content['kind'] = {'task': 'actions', 'decision': 'decisions'}.get(content['kind'], content['kind'])
    # Completion/selection state and list position do not identify the underlying content.
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def make_part(kind, index, value):
    return kind + ':' + str(index) + ':' + fingerprint(kind, value)


def match_part(kind, value, items):
    match = re.fullmatch(r'[0-9]+:([a-f0-9]{64})', value)
    if not match:
        raise ValueError(tr('Dieser ältere oder ungültige Verweis enthält keine Inhaltsprüfung. Den Eintrag in der Quelle erneut verknüpfen.'))
    matches = [index for index, item in enumerate(items) if fingerprint(kind, item) == match[1]]
    if len(matches) != 1:
        raise ValueError(tr('Der verknüpfte Inhalt wurde geändert, entfernt oder ist mehrfach vorhanden. Den Eintrag in der Quelle erneut auswählen.'))
    return matches[0]


def window_parts(window, kind):
    """Read live content in widget order, matching the persisted record field names."""
    from PyQt5.QtCore import Qt
    if kind == 'resource':
        return [window.resources.item(index).data(Qt.UserRole) for index in range(window.resources.count())]
    if kind == 'question':
        return [dict(text=window.questions.item(index).text()) for index in range(window.questions.count())]
    if kind == 'segment':
        return [dict(window.transcript.item(index, 0).data(Qt.UserRole), text=window.transcript.item(index, 1).text()) for index in range(window.transcript.rowCount())]
    if kind == 'result':
        return [dict(kind=window.results.item(index, 0).data(Qt.UserRole), text=window.results.item(index, 1).text()) for index in range(window.results.rowCount())]
    if kind == 'source':
        values = [dict(window.sources.item(index).data(Qt.UserRole)) for index in range(window.sources.count())]
        if 0 <= window.source_index < len(values):
            values[window.source_index].update(title=window.source_title.text().strip() or tr('Ohne Titel'), text=window.source_text.toPlainText())
        return values
    if kind == 'rule':
        rules = window.library.get(window.current).get('rules', {})
        keys = [window.rules.topLevelItem(index).data(0, Qt.UserRole) for index in range(window.rules.topLevelItemCount())]
        return [dict(rules[key], app=key) for key in keys]
    raise ValueError(tr('Diese verknüpfte Fundstelle wird nicht unterstützt.'))


def capture_part(window, kind, index):
    items = window_parts(window, kind)
    if not 0 <= index < len(items):
        raise ValueError(tr('Die verknüpfte Fundstelle ist nicht mehr vorhanden.'))
    return make_part(kind, index, items[index])
