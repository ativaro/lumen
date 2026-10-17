"""Collection actions reuse Lumen's task engine and workflow approvals."""
import os
from pathlib import Path
import stat
import tempfile
from uuid import uuid4
from code_library_contract import app_document


def directory(collection, item):
    selected = item['definition'].get('directory', '')
    if selected:
        path = Path(selected).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError('Der ausgewählte Projektordner ist nicht verfügbar.')
        return path
    path = collection.store.directory / 'code-work' / item['id']
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def prepare_run(collection, identity, user_input=''):
    item = collection.get(identity)
    if item['archived']:
        raise ValueError('Archivierte Einträge können nicht ausgeführt werden.')
    if not isinstance(user_input, str) or len(user_input) > 20000:
        raise ValueError('Eingabe: höchstens 20.000 Zeichen.')
    value = item['definition']; root = directory(collection, item)
    steps = []; approved = False; prompt = value.get('prompt', '')
    if item['kind'] == 'automation':
        flow = next((row for row in collection.store.workflows() if row['id'] == value.get('workflow_id')), None)
        if flow is None or not flow['approved']:
            raise ValueError('Die Automation zuerst mit ihren Quellen und Schritten einrichten und freigeben.')
        steps = flow['steps']; prompt = flow['prompt']; approved = True
        roots = flow['roots']
        if not roots:
            raise ValueError('Der Automation fehlt ein freigegebener Ordner.')
        root = Path(roots[0]).resolve(strict=True)
    else:
        roots = [str(root)]
    if item['kind'] == 'app':
        output=collection.store.directory/'code-work'/item['id']/uuid4().hex
        output.mkdir(parents=True,mode=0o700)
        roots=list(dict.fromkeys([str(output),*roots]));root=output
        prompt += '\nErstelle eine eigenständige kleine HTML-Anwendung und speichere sie als index.html im Auftragsordner. Verwende keine externen Ressourcen oder Netzwerkzugriffe. Behalte die Bedienung vollständig innerhalb dieser Datei.'
    if not prompt.strip() and not steps:
        raise ValueError('Bitte zuerst einen Auftrag oder feste Schritte hinterlegen.')
    if user_input.strip():
        prompt += '\n\nEingabe für diesen Durchlauf:\n' + user_input
    task = collection.store.create_task(item['title'], prompt=prompt, directory=str(root), roots=roots, steps=steps, approved=approved)
    if item['kind']=='automation' and flow.get('code_plan'):
        from code_flow_native import snapshot
        with collection.store.connect() as db:snapshot(db,task,flow,True)
    collection.store.event(task, 'code-library', item['id'])
    collection.used(identity, task)
    return task


def generated_html(collection, identity):
    item = collection.get(identity)
    if item['kind'] != 'app' or not item['last_task']:
        raise ValueError('Noch kein App-Auftrag vorhanden.')
    task = collection.store.task(item['last_task'])
    if task['status'] != 'completed':
        raise ValueError('Die App-Erstellung ist noch nicht erfolgreich abgeschlossen.')
    expected = Path(task['directory']).resolve()
    if expected.parent != (collection.store.directory/'code-work'/item['id']).resolve():
        raise ValueError('Der App-Auftrag gehört nicht zum erwarteten Ordner.')
    handle = os.open(expected / 'index.html', os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262144:
            raise ValueError('Die App-Datei fehlt oder ist zu groß.')
        with os.fdopen(handle, 'rb', closefd=False) as stream:
            source = stream.read(262145)
        if len(source) > 262144:
            raise ValueError('Die App-Datei ist zu groß.')
        return source.decode('utf-8')
    finally:
        os.close(handle)


def preview_file(collection, identity):
    item = collection.get(identity)
    if item['archived'] or item['kind'] != 'app':
        raise ValueError('Diese App ist nicht verfügbar.')
    source = item['definition'].get('html', '')
    if not source.strip():
        raise ValueError('Bitte zuerst App-Inhalt hinterlegen oder den abgeschlossenen Auftrag übernehmen.')
    root = collection.store.directory / 'code-previews'
    root.mkdir(mode=0o700, exist_ok=True)
    target = root / (item['id'] + '.html')
    fd, temporary = tempfile.mkstemp(dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(app_document(source))
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    collection.used(identity)
    return target
