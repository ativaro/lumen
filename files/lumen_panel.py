"""Shared task overview and dismissal of completed/cancelled tasks for Plasma."""
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
        raise ValueError('Ungültige Auftragskennung.')
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


def snapshot(directory=None):
    directory = Path(directory) if directory is not None else state_path()
    result = {'active': [], 'recent': [], 'busy': False, 'attention': False, 'error': ''}
    path = directory / 'lumen.sqlite3'
    if not path.exists(): return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0] > 2:
                raise ValueError('Die Auftragsdaten benötigen eine neuere Lumen-Version.')
            columns = '''id, substr(title,1,200) AS title, status, updated, cursor,
                json_array_length(steps) AS total, substr(result,1,1600) AS result,
                length(result)>1600 AS truncated, substr(error,1,500) AS error,
                EXISTS (SELECT 1 FROM events WHERE task=tasks.id AND kind='input') AS engine'''
            for key, condition, order, limit in [
                ('active', "status IN ('running','needs_input','queued','paused','interrupted','draft')",
                 "CASE status WHEN 'needs_input' THEN 0 WHEN 'running' THEN 1 ELSE 2 END, updated DESC", 8),
                ('recent', "status IN ('completed','failed','cancelled')", 'updated DESC', 5)]:
                for raw in db.execute(f'SELECT {columns} FROM tasks WHERE {condition} AND {VISIBLE_TASKS} ORDER BY {order} LIMIT {limit}'):
                    row = dict(raw)
                    valid_task(row['id'])
                    if (row['status'] == 'running' or row['status'] == 'needs_input' and row['engine']) and not running(directory, row['id']):
                        row['status'] = 'interrupted'
                        row['error'] = 'Ausführung beendet. Letzten Stand in Lumen prüfen.'
                    row['state'] = STATES[row['status']]
                    row['cursor'] = max(0, min(row['cursor'], row['total']))
                    result[key].append(row)
            result['busy'] = any(row['status'] == 'running' for row in result['active'])
            result['attention'] = any(row['status'] == 'needs_input' for row in result['active'])
    except (OSError, sqlite3.Error, ValueError) as exc:
        result.update(active=[], recent=[], busy=False, attention=False,
                      error='Aufträge gerade nicht lesbar. ' + str(exc)[:200])
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Lumen-Panel')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--snapshot', action='store_true')
    group.add_argument('--system-snapshot', action='store_true')
    group.add_argument('--control', choices=['volume', 'brightness', 'mute', 'search', 'network', 'audio', 'display', 'appearance', 'desktop-settings', 'lock'])
    parser.add_argument('--value', type=int)
    group.add_argument('--open-task', type=valid_task)
    group.add_argument('--dismiss-task', type=valid_task)
    group.add_argument('--open-page', choices=['chat', 'files', 'system', 'tasks', 'settings', 'workplace'])
    group.add_argument('--search', action='store_true')
    group.add_argument('--settings', action='store_true')
    args = parser.parse_args()
    if args.dismiss_task:
        error = ''
        try: Store().dismiss_task(args.dismiss_task)
        except (OSError, sqlite3.Error, ValueError) as exc: error = 'Aufgabe konnte nicht geschlossen werden. ' + str(exc)[:200]
        result = snapshot()
        if error: result['error'] = error
        print(json.dumps(result, ensure_ascii=False)); return
    if args.system_snapshot or args.control:
        from lumen_controls import snapshot as system_snapshot, control
        try:
            if args.control: control(args.control, args.value)
            print(json.dumps({'system': system_snapshot(), 'error': ''}, ensure_ascii=False))
        except (OSError, subprocess.SubprocessError, ValueError):
            print(json.dumps({'error': 'Systemaktion fehlgeschlagen. Bitte erneut versuchen.'}))
        return
    if args.open_task or args.open_page or args.search or args.settings:
        name = 'lumen-search' if args.search else 'lumen-settings' if args.settings else 'lumen-agent-app'
        binary = Path(os.environ.get('LUMEN_BIN_DIR', '/usr/bin')) / name
        arguments = [] if args.search or args.settings else ['--task', args.open_task] if args.open_task else ['--page', args.open_page]
        subprocess.Popen([str(binary), *arguments], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    print(json.dumps(snapshot(), ensure_ascii=False))


if __name__ == '__main__': main()
