"""Shared task overview and dismissal of completed/cancelled tasks for Plasma."""
from lumen_i18n import tr, language
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess

from lumen_store import STATES, VISIBLE_TASKS, Store, state_path


def valid_task(value):
    if not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError(tr('Ungültige Auftragskennung.'))
    return value


def running(directory, task):
    try:
        fd = os.open(directory / ('task-' + valid_task(task) + '.lock'), os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return True
        return False
    finally:
        os.close(fd)


def applications():
    from lumen_apps import catalogue
    labels = {'lumen': 'Lumen', 'files': tr('Dateien'), 'search': tr('Suche'),
              'meetings': tr('Meetings'), 'household': tr('Haushalt'), 'workbench': tr('Werkbank'),
              'radio': tr('Radio')}
    return [dict(id=key, title=title, label=labels.get(key, title.removeprefix('Lumen ')),
                 description=description, icon=icon) for key,title,description,icon in catalogue()]


def snapshot(directory=None, task_limit=None):
    if task_limit is not None and (type(task_limit) is not int or not 1 <= task_limit <= 1000):
        raise ValueError('Invalid task limit')
    directory = Path(directory) if directory is not None else state_path()
    result = {'active': [], 'recent': [], 'busy': False, 'attention': False, 'error': '', 'language': language(), 'apps': applications(), 'more': False}
    path = directory / 'lumen.sqlite3'
    if not path.exists(): return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0] > 2:
                raise ValueError(tr('Die Auftragsdaten benötigen eine neuere Lumen-Version.'))
            columns = '''id, substr(title,1,200) AS title, status, updated, cursor,
                json_array_length(steps) AS total, substr(result,1,1600) AS result,
                length(result)>1600 AS truncated, substr(error,1,500) AS error,
                EXISTS (SELECT 1 FROM events WHERE task=tasks.id AND kind='input') AS engine'''
            for key, condition, order, limit in [
                ('active', "status IN ('running','needs_input','queued','paused','interrupted','draft')",
                 "CASE status WHEN 'needs_input' THEN 0 WHEN 'running' THEN 1 ELSE 2 END, updated DESC", 8),
                ('recent', "status IN ('completed','failed','cancelled')", 'updated DESC', 5)]:
                limit = task_limit or limit
                count = db.execute(f'SELECT count(*) FROM tasks WHERE {condition} AND {VISIBLE_TASKS}').fetchone()[0]
                result['more'] = result['more'] or count > limit
                for raw in db.execute(f'SELECT {columns} FROM tasks WHERE {condition} AND {VISIBLE_TASKS} ORDER BY {order} LIMIT {limit}'):
                    row = dict(raw)
                    valid_task(row['id'])
                    if (row['status'] == 'running' or row['status'] == 'needs_input' and row['engine']) and not running(directory, row['id']):
                        row['status'] = 'interrupted'
                        row['error'] = tr('Ausführung beendet. Letzten Stand in Lumen prüfen.')
                    row['state'] = STATES[row['status']]
                    row['cursor'] = max(0, min(row['cursor'], row['total']))
                    result[key].append(row)
            result['busy'] = any(row['status'] == 'running' for row in result['active'])
            result['attention'] = any(row['status'] == 'needs_input' for row in result['active'])
    except (OSError, sqlite3.Error, ValueError) as exc:
        result.update(active=[], recent=[], busy=False, attention=False,
                      error=tr('Aufträge gerade nicht lesbar. ') + str(exc)[:200])
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Lumen-Panel')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--language', action='store_true')
    group.add_argument('--snapshot', action='store_true')
    group.add_argument('--system-snapshot', action='store_true')
    group.add_argument('--control', choices=['volume', 'brightness', 'mute', 'search', 'network', 'audio', 'display', 'appearance', 'hardware', 'desktop-settings', 'lock'])
    parser.add_argument('--value', type=int)
    parser.add_argument('--task-limit', type=int, choices=range(1,1001), metavar='1..1000')
    group.add_argument('--open-app', choices=[item['id'] for item in applications()])
    group.add_argument('--open-task', type=valid_task)
    group.add_argument('--dismiss-task', type=valid_task)
    group.add_argument('--open-page', choices=['chat', 'files', 'system', 'tasks', 'settings', 'workplace'])
    group.add_argument('--search', action='store_true')
    group.add_argument('--voice', action='store_true')
    group.add_argument('--settings', action='store_true')
    args = parser.parse_args()
    if args.open_app:
        from lumen_launch import executable
        binary = executable('lumen-agent-app' if args.open_app == 'lumen' else 'lumen-'+args.open_app)
        subprocess.Popen([binary], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if args.language:
        print(json.dumps({'language': language()})); return
    if args.dismiss_task:
        error = ''
        try: Store().dismiss_task(args.dismiss_task)
        except (OSError, sqlite3.Error, ValueError) as exc: error = tr('Aufgabe konnte nicht geschlossen werden. ') + str(exc)[:200]
        result = snapshot(task_limit=args.task_limit)
        if error: result['error'] = error
        print(json.dumps(result, ensure_ascii=False)); return
    if args.system_snapshot or args.control:
        from lumen_controls import snapshot as system_snapshot, control
        try:
            if args.control: control(args.control, args.value)
            print(json.dumps({'system': system_snapshot(), 'error': '', 'language': language()}, ensure_ascii=False))
        except (OSError, subprocess.SubprocessError, ValueError):
            print(json.dumps({'error': tr('Systemaktion fehlgeschlagen. Bitte erneut versuchen.')}))
        return
    if args.open_task or args.open_page or args.search or args.voice or args.settings:
        name = 'lumen-search' if args.search or args.voice else 'lumen-settings' if args.settings else 'lumen-agent-app'
        from lumen_launch import executable
        binary = executable(name)
        arguments = ['--voice'] if args.voice else [] if args.search or args.settings else ['--task', args.open_task] if args.open_task else ['--page', args.open_page]
        subprocess.Popen([str(binary), *arguments], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    print(json.dumps(snapshot(task_limit=args.task_limit), ensure_ascii=False))


if __name__ == '__main__': main()
