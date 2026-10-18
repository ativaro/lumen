"""Versioned native block plans. Paths and grants never leave portable templates."""
import json
from pathlib import Path
from uuid import uuid4
from lumen_i18n import tr

CATALOG = {
    'manual': ('Start', 'Manuell starten', 'Mit einem Knopf einen Durchlauf beginnen.'),
    'read_file': ('Verarbeiten', 'Datei lesen', 'Text aus einer ausgewählten Datei oder einem PDF lesen.'),
    'if_pdf': ('Steuern', 'Wenn PDF / Sonst', 'PDF weiterverarbeiten; andere Dateien direkt zum Melden überspringen.'),
    'ai': ('Verarbeiten', 'KI befragen', 'Lesen, vergleichen, übersetzen oder zusammenfassen; ohne Werkzeuge.'),
    'condition': ('Steuern', 'Bedingung prüfen', 'Nur bei erfüllter Bedingung fortfahren.'),
    'choose': ('Steuern', 'Passenden Weg wählen', 'Den ersten passenden Weg ausführen; sonst den Sonst-Weg.'),
    'ai_check': ('Verarbeiten', 'Inhalt mit KI prüfen', 'Inhaltsfrage prüfen und ein Ja/Nein-Ergebnis liefern.'),
    'for_each': ('Steuern', 'Für jede Textzeile', 'Bis zu zwanzig Textzeilen nacheinander durchlaufen und Ergebnisse sammeln.'),
    'end_each': ('Steuern', 'Ergebnisse sammeln', 'Interner Abschluss einer Wiederholung.'),
    'delay': ('Steuern', 'Warten', 'Eine gewählte Anzahl Sekunden warten; nach Unterbrechung fortsetzen.'),
    'filter_text': ('Verarbeiten', 'Textzeilen filtern', 'Nur Textzeilen behalten, die den gewählten Text enthalten.'),
    'project_note': ('Handeln', 'Projekt ergänzen', 'Das Ergebnis an die Notiz eines ausdrücklich gewählten Lumen-Projekts anhängen.'),
    'approval': ('Steuern', 'Auf Bestätigung warten', 'Ergebnis prüfen, bevor die nächsten Aktionen laufen.'),
    'save_file': ('Handeln', 'Datei speichern', 'Ergebnis als neue Textdatei im gewählten Ordner ablegen.'),
    'save_note': ('Handeln', 'Notiz speichern', 'Eine neue Notiz in Lumen Notes anlegen.'),
    'create_task': ('Handeln', 'Aufgabe erstellen', 'Eine offene Aufgabe in Lumen Inbox anlegen.'),
    'notify': ('Handeln', 'Mich informieren', 'Ergebnis in den Lumen-Benachrichtigungen zeigen.'),
}
LEGACY_KINDS = frozenset(('manual','read_file','if_pdf','ai','approval','save_file','save_note','create_task','notify'))
LATER = {'Start': ['Zeitpunkt', 'Neue Datei in Drive', 'Nachricht', 'Termin', 'Projektänderung'],
         'Verarbeiten': ['Quellen durchsuchen'], 'Handeln': ['Projekt ergänzen'],
         'Steuern': ['Mehrere Elemente durchlaufen']}


def node(kind, config='', title=None):
    return dict(id=uuid4().hex, kind=kind, title=title or tr(CATALOG[kind][1]), config=config)


def starter():
    return dict(version=2, nodes=[node('manual'),node('read_file'),node('ai',tr('Fasse den Inhalt zusammen und nenne offene Punkte.')),node('approval'),node('save_note'),node('notify')])


def parse(value):
    if isinstance(value,str):
        if len(value)>30000:raise ValueError('Ablauf ist zu groß.')
        try:value=json.loads(value)
        except (TypeError,ValueError):raise ValueError('Ungültiger Bausteinablauf.') from None
    if isinstance(value,dict) and value.get('version')==3:
        from code_block_paths import validate
        return validate(value)
    if not isinstance(value,dict) or set(value)!={'version','nodes'} or type(value['version']) is not int or value['version']!=2:
        raise ValueError('Ungültige Bausteinversion.')
    nodes=value['nodes']
    if not isinstance(nodes,list) or not 2<=len(nodes)<=14:raise ValueError('Zwei bis vierzehn Bausteine sind erforderlich.')
    ids=set();read=False
    for index,n in enumerate(nodes):
        if not isinstance(n,dict) or set(n)!={'id','kind','title','config'}:raise ValueError('Ungültiger Baustein.')
        if not isinstance(n['kind'],str) or n['kind'] not in LEGACY_KINDS:raise ValueError('Dieser Baustein wird noch nicht unterstützt.')
        for key,limit in [('id',32),('title',160),('config',4096)]:
            if not isinstance(n[key],str) or len(n[key])>limit or '\0' in n[key]:raise ValueError('Ungültiges Bausteinfeld: '+key)
        if len(n['id'])!=32 or any(c not in '0123456789abcdef' for c in n['id']) or n['id'] in ids:raise ValueError('Ungültige Bausteinkennung.')
        ids.add(n['id'])
        if not n['title'].strip():raise ValueError('Der Baustein braucht einen Namen.')
        if (index==0)!=(n['kind']=='manual'):raise ValueError('Der erste und einzige Start ist Manuell starten.')
        if n['kind']=='read_file':read=True
        if n['kind']=='if_pdf' and (not read or not any(x['kind']=='notify' for x in nodes[index+1:])):
            raise ValueError('Wenn PDF braucht zuerst Datei lesen und danach Mich informieren für den Sonst-Pfad.')
    if len(json.dumps(value))>30000:raise ValueError('Ablauf ist zu groß.')
    return json.loads(json.dumps(value))


def encode(plan):
    return json.dumps(parse(plan),ensure_ascii=False,separators=(',',':'))


def portable_prompt(plan):
    # Only instructions travel. Source/output paths, grants and identity never do.
    return '\n'.join(str(i+1)+'. '+CATALOG[n['kind']][1]+(': '+n['config'] if n['kind'] in ('ai','ai_check') else '') for i,n in enumerate(parse(plan)['nodes']))


def permissions(plan):
    result=[]
    for n in parse(plan)['nodes']:
        kind=n['kind'];config=n['config'].strip()
        if kind=='manual' and plan.get('version')==3:
            from code_block_paths import config,source
            inp=source(config(n))
            if inp['kind']=='file':
                if not inp.get('path') or not Path(inp['path']).is_absolute():raise ValueError('Bitte eine Quelldatei auswählen.')
                result.append('Datei lesen: '+inp['path'])
            elif inp['kind']=='project':result.append('Ausgewähltes Lumen-Projekt lesen: '+inp.get('project_id',''))
            else:result.append('Die ausdrücklich eingegebenen Inhalte verwenden.')
        elif kind in ('read_file','save_file'):
            if not config or not Path(config).is_absolute():raise ValueError('Bitte Datei und Zielordner ausdrücklich auswählen.')
            result.append(('Datei lesen: ' if kind=='read_file' else 'Neue Ergebnisdatei anlegen in: ')+config)
        elif kind in ('ai','ai_check'):
            if not config:raise ValueError('Bitte den KI-Auftrag beschreiben.')
            result.append('KI: Die bis hier gelesenen Inhalte an den eingerichteten Modellanbieter senden; keine Werkzeuge.')
        elif kind=='project_note':
            if not config:raise ValueError('Bitte ein Lumen-Projekt auswählen.')
            result.append('Projektnotiz ergänzen: '+config)
        elif kind=='save_note':result.append('Neue Notiz in Lumen Notes: '+(config or n['title']))
        elif kind=='create_task':result.append('Neue offene Aufgabe in Lumen Inbox: '+(config or n['title']))
        elif kind=='notify':result.append('Lumen-Benachrichtigung anzeigen.')
    return result


def generated(answer):
    from tools_data import parse_answer
    raw=parse_answer(answer)
    if set(raw)!={'nodes'} or not isinstance(raw['nodes'],list):raise ValueError('Die KI hat keinen gültigen Ablauf geliefert.')
    nodes=[]
    for row in raw['nodes']:
        if not isinstance(row,dict) or set(row)!={'kind','title','config'}:raise ValueError('Ungültiger KI-Baustein.')
        kind=row['kind']
        if not isinstance(kind,str) or kind not in CATALOG:raise ValueError('Die Beschreibung benötigt einen noch nicht verfügbaren Baustein.')
        if kind not in ('ai',):row={**row,'config':''}
        nodes.append(node(kind,row['config'],row['title']))
    return parse(dict(version=2,nodes=nodes))
