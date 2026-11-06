"""Selection-aware personal actions stored as ordinary manual Lumen workflows."""
from lumen_i18n import worker_environment, tr
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from lumen_store import Store

PREFIX = 'fileAction/'
TOKENS = {'datei', 'ordner', 'name', 'stamm', 'endung', 'auswahl'}


def template(task, paths=()):
    if any(s['action'] not in ('open', 'copy', 'write') for s in task['steps']):
        raise ValueError(tr('Systemschritte als normalen Ablauf speichern; Dateiaktionen verwenden nur Dateischritte.'))
    value = copy.deepcopy(task)
    value['prompt'] = value.get('prompt', '')
    # Tasks keep their original language after the interface language changes.
    for marker in ('\n\nAusgewählte Pfade (Kontext):', '\n\nSelected paths (context):'):
        value['prompt'] = value['prompt'].split(marker, 1)[0]
    source = next((s.get('source') for s in value['steps'] if s.get('source')), None) or (paths[0] if paths else '')
    def convert(text):
        if source: text = text.replace(source, '{{datei}}')
        return text.replace(task['directory'].rstrip('/') + '/', '{{ordner}}/')
    value['prompt'] = convert(value['prompt'])
    if not value['steps'] and '{{auswahl}}' not in value['prompt']:
        value['prompt'] += tr('\n\nWende diesen Auftrag auf die folgende Auswahl an:\n{{auswahl}}')
    for step in value['steps']:
        for key in ('path', 'source'):
            if key in step: step[key] = convert(step[key])
    return value


def expand(flow, paths):
    if not paths: raise ValueError(tr('Zuerst eine Datei auswählen.'))
    selection = [Path(p).absolute() for p in paths]
    if any(not p.exists() or p.is_symlink() for p in selection): raise ValueError(tr('Eine ausgewählte Datei ist nicht mehr verfügbar oder ist eine Verknüpfung.'))
    def render(text, path):
        values = dict(datei=str(path), ordner=str(path.parent), name=path.name, stamm=path.stem,
                      endung=path.suffix, auswahl=json.dumps([str(p) for p in selection], ensure_ascii=False))
        def substitute(match):
            if match[1] not in TOKENS: raise ValueError(tr('Unbekannter Platzhalter: ') + match[0])
            return values[match[1]]
        return re.sub(r'\{\{(\w+)\}\}', substitute, text)
    steps = []
    for path in selection:
        steps.extend({key: render(value, path) if key != 'action' else value for key, value in step.items()} for step in flow['steps'])
    if steps:
        from lumen_actions import validate_steps
        validate_steps(steps)
        targets = [s['path'] for s in steps if s['action'] in ('copy','write')]
        if len(targets) != len(set(targets)): raise ValueError(tr('Mehrere Dateien hätten dasselbe Ziel. In der Aktion {{stamm}} oder {{name}} verwenden.'))
    return dict(title=flow['name'], prompt=render(flow['prompt'], selection[0]), steps=steps,
                roots=list(dict.fromkeys(str(p.parent) for p in selection)), directory=str(selection[0].parent))


def save_action(parent, store, task, paths=()):
    if task['status'] != 'completed': raise ValueError(tr('Zuerst die Aufgabe erfolgreich abschließen.'))
    from lumen_workspace import PlanDialog
    from PySide6.QtWidgets import QLabel
    dialog = PlanDialog(parent, template(task, paths), workflow=True)
    dialog.setWindowTitle(tr('Eigene Dateiaktion speichern'))
    hint = QLabel(tr('Platzhalter: {{datei}}, {{ordner}}, {{name}}, {{stamm}}, {{endung}}, {{auswahl}}.\nDie neue Auswahl wird vor jedem Start angezeigt. KI-Aufträge behalten ihre Werkzeugfreigaben.')); hint.setWordWrap(True)
    dialog.layout().insertWidget(0, hint)
    dialog.trigger.setCurrentIndex(0); dialog.trigger.setEnabled(False); dialog.enable.hide(); dialog.interval.hide(); dialog.watch.hide()
    if dialog.exec():
        identity = store.save_workflow(**dialog.value)
        store.set_setting(PREFIX + identity, True)
        return identity


def run_action(window, flow, paths):
    from lumen_workspace import PlanDialog
    value = expand(flow, paths); dialog = PlanDialog(window, value)
    dialog.setWindowTitle(tr('Dateiaktion prüfen · ') + flow['name'])
    if not dialog.exec(): return
    config = dialog.value; store = Store()
    if config['steps']:
        identity = store.create_task(config['name'], directory=value['directory'], roots=config['roots'], steps=config['steps'], approved=True)
        store.event(identity, 'workflow', flow['id'])
        subprocess.Popen([sys.executable, str(Path(__file__).with_name('lumen_tasks.py')), '--task', identity],
                         env=worker_environment(LUMEN_DATA=str(store.directory)), start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        window.activity.setText(tr('Dateiaktion gestartet · ') + config['name'])
    else:
        window.ask_lumen('open', paths)
        panel = window.lumen_host.chat if hasattr(window, 'lumen_host') else window.assistant
        if panel.backend.busy: raise ValueError(tr('Bitte die laufende Lumen-Aufgabe zuerst abschließen.'))
        panel.set_action(''); panel.submit(config['prompt'])


def menu(window, menu, paths):
    store = Store(); sub = menu.addMenu(tr('Eigene Aktionen'))
    flows = [flow for flow in store.workflows() if flow['trigger'] == 'manual' and store.setting(PREFIX + flow['id'], False)]
    def run(flow):
        try: run_action(window, flow, paths)
        except (ValueError, OSError) as error: window.error(str(error))
    for flow in flows: sub.addAction(flow['name'] + ' …', lambda _=False, f=flow: run(f))
    if not flows: sub.addAction(tr('Nach erledigten Lumen-Aufgaben als Dateiaktion speichern')).setEnabled(False)
