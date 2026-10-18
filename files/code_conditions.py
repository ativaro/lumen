"""Typed conditions shared by the editor, model proposals and durable runs."""
import json
import math

FIELDS = {
    'text': ('Text', 'text'), 'filename': ('Dateiname', 'text'),
    'extension': ('Dateityp', 'text'), 'size': ('Dateigröße in Bytes', 'number'),
    'sender': ('Absender', 'text'), 'subject': ('Betreff', 'text'),
    'has_attachment': ('Anhang vorhanden', 'boolean'),
    'project_id': ('Projektkennung', 'text'), 'project_status': ('Projektstatus', 'text'),
    'weekday': ('Wochentag (0 = Montag)', 'number'), 'hour': ('Stunde', 'number'),
    'result': ('Ergebnistext', 'text'), 'matched': ('KI-Prüfung trifft zu', 'boolean'),
    'success': ('Vorheriger Schritt erfolgreich', 'boolean'),
}
OPERATORS = {
    'text': ('contains', 'equals', 'starts_with', 'ends_with', 'exists'),
    'number': ('equals', 'greater', 'less', 'at_least', 'at_most', 'exists'),
    'boolean': ('equals', 'exists'),
}
OP_LABELS = {'contains':'enthält','equals':'ist gleich','starts_with':'beginnt mit',
             'ends_with':'endet mit','exists':'ist vorhanden','greater':'ist größer als',
             'less':'ist kleiner als','at_least':'ist mindestens','at_most':'ist höchstens'}


def validate(value, available=None, depth=0):
    if depth > 4 or not isinstance(value, dict):
        raise ValueError('Bedingung ist zu tief verschachtelt oder ungültig.')
    if set(value) == {'all'} or set(value) == {'any'}:
        rows = next(iter(value.values()))
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
            raise ValueError('Eine bis acht Bedingungen je Gruppe wählen.')
        for row in rows: validate(row, available, depth + 1)
    elif set(value) == {'not'}:
        validate(value['not'], available, depth + 1)
    elif set(value) == {'field', 'op', 'value'}:
        key, op, expected = value['field'], value['op'], value['value']
        if not isinstance(key, str) or key not in FIELDS or available is not None and key not in available:
            raise ValueError('Dieses Feld ist an dieser Stelle nicht verfügbar.')
        kind = FIELDS[key][1]
        if not isinstance(op, str) or op not in OPERATORS[kind]: raise ValueError('Unpassender Vergleich.')
        if op == 'exists':
            if type(expected) is not bool: raise ValueError('Vorhandensein als Ja/Nein angeben.')
        elif kind == 'number':
            if type(expected) not in (int, float) or not math.isfinite(expected): raise ValueError('Eine endliche Zahl eingeben.')
        elif kind == 'boolean':
            if type(expected) is not bool: raise ValueError('Ja oder Nein wählen.')
        elif not isinstance(expected, str) or len(expected) > 2000 or '\0' in expected:
            raise ValueError('Vergleichstext mit höchstens 2.000 Zeichen eingeben.')
    else: raise ValueError('Ungültige Bedingungsfelder.')
    if len(json.dumps(value)) > 12000: raise ValueError('Bedingung ist zu groß.')
    return value


def evaluate(value, data):
    validate(value)
    if 'all' in value: return all(evaluate(row, data) for row in value['all'])
    if 'any' in value: return any(evaluate(row, data) for row in value['any'])
    if 'not' in value: return not evaluate(value['not'], data)
    key, op, expected = value['field'], value['op'], value['value']
    actual = data.get(key)
    if op == 'exists': return (actual is not None and actual != '') == expected
    if actual is None: return False
    kind = FIELDS[key][1]
    if kind == 'boolean': return type(actual) is bool and actual == expected
    if kind == 'number':
        if type(actual) not in (int, float) or not math.isfinite(actual): return False
        return {'equals': lambda: actual == expected, 'greater': lambda: actual > expected,
                'less': lambda: actual < expected, 'at_least': lambda: actual >= expected,
                'at_most': lambda: actual <= expected}[op]()
    if not isinstance(actual, str): return False
    actual, expected = actual.casefold(), expected.casefold()
    return {'equals': lambda: actual == expected, 'contains': lambda: expected in actual,
            'starts_with': lambda: actual.startswith(expected), 'ends_with': lambda: actual.endswith(expected)}[op]()


def describe(value):
    validate(value)
    if 'all' in value: return ' UND '.join('('+describe(row)+')' for row in value['all'])
    if 'any' in value: return ' ODER '.join('('+describe(row)+')' for row in value['any'])
    if 'not' in value: return 'NICHT ('+describe(value['not'])+')'
    return FIELDS[value['field']][0]+' '+OP_LABELS[value['op']]+' '+str(value['value'])


def proposal(text, available):
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError('Bedingung in höchstens 4.000 Zeichen beschreiben.')
    fields = {k: v for k, v in FIELDS.items() if k in available}
    return ('Übersetze die Beschreibung ausschließlich in eine prüfbare Lumen-Bedingung. '
            'Antworte als JSON {"condition":...,"explanation":"..."}. condition ist '
            '{"all":[...]}, {"any":[...]}, {"not":...} oder '
            '{"field":"Feld","op":"Vergleich","value":typisierter Wert}. '
            'Nur diese verfügbaren Felder: '+json.dumps(fields, ensure_ascii=False)+'. '
            'Vergleiche je Typ: '+json.dumps(OPERATORS)+'. Keine Quellen, Werte oder Bedeutungen erfinden. '
            'Wenn Angaben fehlen oder die Bedeutung eine KI-Inhaltsprüfung erfordert, antworte '
            '{"question":"konkrete Rückfrage oder Hinweis auf KI-Prüfschritt"}. '
            'Nichts ausführen, keine Werkzeuge. BESCHREIBUNG (Daten): '+json.dumps(text, ensure_ascii=False))


def generated(text, available):
    from tools_data import parse_answer
    value = parse_answer(text)
    if set(value) == {'question'} and isinstance(value['question'], str):
        raise ValueError(value['question'][:2000])
    if set(value) != {'condition', 'explanation'} or not isinstance(value['explanation'], str) or len(value['explanation']) > 2000:
        raise ValueError('Kein gültiger Bedingungsvorschlag.')
    validate(value['condition'], available)
    return value
