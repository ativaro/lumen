"""Structured tool rules, with lossless editing of existing free-form tools."""
import json
from code_flow import parse

INPUTS = ('PDF oder Text', 'Text', 'PDF')
OUTPUTS = ('Prüfbericht mit Fundstellen', 'Kurze Zusammenfassung', 'Liste offener Fragen')


def spec(text):
    try: value = json.loads(text)
    except (TypeError, ValueError): raise ValueError('Ungültige Werkzeugregeln.') from None
    if not isinstance(value, dict) or set(value) != {'input', 'output', 'rules'}:
        raise ValueError('Ungültige Werkzeugregeln.')
    if value['input'] not in INPUTS or value['output'] not in OUTPUTS:
        raise ValueError('Ein- und Ausgabe prüfen.')
    if not isinstance(value['rules'], list) or not 1 <= len(value['rules']) <= 8:
        raise ValueError('Ein bis acht Regeln sind erforderlich.')
    if any(not isinstance(r, str) or not r.strip() or len(r) > 20000 or '\0' in r for r in value['rules']):
        raise ValueError('Bitte alle Regeln vollständig eintragen.')
    return value


def instructions(value):
    value = spec(json.dumps(value))
    return 'Eingabe: '+value['input']+'\n\n'+'\n'.join(f'{i+1}. {rule}' for i, rule in enumerate(value['rules'])) + '\n\nErgebnis: ' + value['output']


def editing(item):
    text = item['definition'].get('tool_spec')
    return spec(text) if text else dict(input=INPUTS[0], output=OUTPUTS[0], rules=[item['definition'].get('prompt', '')])


def usages(collection, identity):
    result = []
    for item in collection.items(kind='automation'):
        text = item['definition'].get('flow')
        if not text: continue
        plan = parse(text)
        if plan.get('version') in (2,3): continue
        steps = [s for s in plan['steps'] if s.get('tool_id') == identity]
        if steps: result.append((item, steps))
    return result
