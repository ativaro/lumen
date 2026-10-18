"""Portable definitions for the native and server Code & Automation collection."""
from html import escape
import json

KINDS = ('app', 'tool', 'automation', 'code')
LIMITS = {'prompt': 20000, 'html': 262144, 'directory': 4096, 'workflow_id': 80,
          'routine_id': 80, 'source_task': 80, 'session_id':512, 'draft_prompt':20000, 'flow':30000, 'tool_spec':24000, 'editor':20}
TEMPLATE_FORMAT = 'lumen-tool/1'
APP_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"


def definition(kind, title, description='', value=None):
    if kind not in KINDS:
        raise ValueError('Unbekannte Eintragsart.')
    if not isinstance(title, str) or not title.strip() or len(title) > 160 or '\x00' in title:
        raise ValueError('Ein Name mit höchstens 160 Zeichen ist erforderlich.')
    if not isinstance(description, str) or len(description) > 2000 or '\x00' in description:
        raise ValueError('Beschreibung: höchstens 2000 Zeichen.')
    value = {} if value is None else value
    if not isinstance(value, dict) or not set(value) <= LIMITS.keys():
        raise ValueError('Ungültige Werkzeugdefinition.')
    for key, text in value.items():
        if not isinstance(text, str) or len(text) > LIMITS[key] or '\x00' in text:
            raise ValueError('Ungültiges Definitionsfeld: ' + key)
    if value.get('tool_spec'):
        from code_tool import spec
        if kind!='tool':raise ValueError('Werkzeugregeln gehören zu einem Werkzeug.')
        spec(value['tool_spec'])
    if value.get('flow'):
        if __package__:
            from .code_flow import parse
        else:
            from code_flow import parse
        if kind!='automation':raise ValueError('Abläufe gehören zu einer Automation.')
        plan=parse(value['flow'])
        if value.get('editor')=='routine' and (plan.get('version')!=3 or any(n['kind'] in ('choose','condition','for_each') for n in plan['nodes'])):
            raise ValueError('Eine Routine verwendet feste Schritte. Für Bedingungen und Verzweigungen Automation wählen.')
    if 'editor' in value and (value['editor']!='routine' or kind!='automation' or not value.get('flow')):
        raise ValueError('Ungültiger Ablaufeditor.')
    if kind != 'app' and value.get('html'):
        raise ValueError('HTML gehört zu einer kleinen App.')
    if kind != 'automation' and (value.get('workflow_id') or value.get('routine_id')):
        raise ValueError('Zeitpläne gehören zu einer Automation.')
    if kind != 'code' and (value.get('session_id') or value.get('draft_prompt')):
        raise ValueError('Coding-Gespräche gehören zu einem Code-Projekt.')
    return {'kind': kind, 'title': title.strip(), 'description': description.strip(), 'definition': dict(value)}


def export_template(item):
    # Local paths, identity references, grants and run history never travel with a template.
    portable = {key: value for key, value in item['definition'].items() if key in ('prompt', 'html')}
    if item['definition'].get('flow'):
        if __package__:
            from .code_flow import parse,prompt
        else:
            from code_flow import parse,prompt
        portable['prompt']=prompt(parse(item['definition']['flow']))
    return {'format': TEMPLATE_FORMAT, **definition(item['kind'], item['title'], item['description'], portable)}


def import_template(value):
    if isinstance(value, str):
        if len(value.encode('utf-8')) > 2000000:
            raise ValueError('Vorlage ist zu groß.')
        value = json.loads(value)
    if not isinstance(value, dict) or set(value) != {'format', 'kind', 'title', 'description', 'definition'}:
        raise ValueError('Ungültige Lumen-Vorlage.')
    if value['format'] != TEMPLATE_FORMAT or not isinstance(value['definition'], dict):
        raise ValueError('Diese Vorlagenversion wird nicht unterstützt.')
    if not set(value['definition']) <= {'prompt', 'html'}:
        raise ValueError('Vorlagen dürfen keine persönlichen Quellen oder Freigaben enthalten.')
    return definition(value['kind'], value['title'], value['description'], value['definition'])


def app_document(source):
    definition('app', 'Lumen App', value={'html': source})
    child = '<meta http-equiv="Content-Security-Policy" content="' + escape(APP_CSP, quote=True) + '">' + source
    return ('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' +
            escape(APP_CSP + "; frame-src about:", quote=True) + '"><title>Lumen App</title>' +
            '<style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%}</style></head>' +
            '<body><iframe title="Lumen App" sandbox="allow-scripts allow-forms" srcdoc="' +
            escape(child, quote=True) + '"></iframe></body></html>')
