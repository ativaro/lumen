"""Small local status for the bar; actions reuse the owning application."""
import math
import hashlib
from pathlib import Path
import re
import sqlite3
import subprocess
import time

from PySide6.QtCore import QSettings
from lumen_i18n import tr


def focus(settings=None, now=None):
    settings = settings or QSettings('Lumen', 'Assistant')
    settings.sync()
    now = time.time() if now is None else now
    end = settings.value('topbar/focusEnd', 0, type=float)
    remaining = settings.value('topbar/focusRemaining', 0, type=int)
    if not math.isfinite(end) or not 0 <= remaining <= 86400:
        return dict(end=0, remaining=0, state='off')
    return dict(end=end, remaining=max(0, math.ceil(end-now)) if end else remaining,
                state=('running' if end > now else 'finished') if end else 'paused' if remaining else 'off')


def focus_action(action, settings=None, now=None):
    settings = settings or QSettings('Lumen', 'Assistant')
    now = time.time() if now is None else now
    current = focus(settings, now)
    if action == 'start': end, remaining = now + 25*60, 0
    elif action == 'pause' and current['state'] == 'running': end, remaining = 0, current['remaining']
    elif action == 'resume' and current['state'] == 'paused': end, remaining = now + current['remaining'], 0
    elif action == 'stop': end, remaining = 0, 0
    else: raise ValueError(tr('Die Fokuszeit hat sich inzwischen geändert.'))
    settings.setValue('topbar/focusEnd', end)
    settings.setValue('topbar/focusRemaining', remaining)
    settings.sync()
    if settings.status() != QSettings.NoError:
        raise OSError(tr('Die Fokuszeit konnte nicht gespeichert werden.'))


def updates():
    from updater_data import read_json, state_root, installations
    plan = read_json(state_root()/'plan.json')
    rows = plan.get('rows', [])
    revision = plan.get('revision', '')
    if not isinstance(revision,str) or not re.fullmatch('[a-f0-9]{40}',revision) or not isinstance(rows,list):
        return dict(checked=False,pending=False,notes='')
    installed = [read_json(root/'install.json').get('revision') for root in installations()]
    saved = read_json(state_root()/'components.json')
    pending = [row for row in rows if isinstance(row, dict) and row.get('pending') and not row.get('optional')
               and (row.get('id') == 'lumen' and bool(installed) and any(r != revision for r in installed)
                    or row.get('id') != 'lumen' and saved.get(row.get('id')) != row.get('fingerprint'))]
    return dict(checked=bool(revision), pending=bool(pending), notes=str(plan.get('notes', ''))[:4000])


def snapshot():
    from lumen_panel import valid_task, running
    from lumen_store import VISIBLE_TASKS
    from lumen_store import state_path
    decisions, error = [], ''
    directory=state_path();path=directory/'lumen.sqlite3'
    if path.is_file():
        try:
            from contextlib import closing
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
                if db.execute('PRAGMA user_version').fetchone()[0]>3:raise ValueError('Newer tasks')
                for identity,title,engine in db.execute("SELECT id,substr(title,1,200),EXISTS(SELECT 1 FROM events WHERE task=tasks.id AND kind='input') FROM tasks WHERE status='needs_input' AND "+VISIBLE_TASKS+" ORDER BY updated DESC LIMIT 5"):
                    valid_task(identity)
                    if not engine or running(directory,identity): decisions.append(dict(id=identity,title=title))
        except (OSError,sqlite3.Error,ValueError): error=tr('Freigaben gerade nicht lesbar.')
    return dict(focus=focus(), decisions=decisions, decisionError=error, update=updates())


def recent():
    from search_home import recent_documents
    from lumen_store import state_path
    from contextlib import closing
    rows=[dict(row,target=row['path'],kind='file') for row in recent_documents() if Path(row['path']).exists()]
    path=state_path()/'lumen.sqlite3'
    if path.is_file():
        from desktop_backend import connection, PREFIX
        try: _,binding=connection()
        except (OSError,ValueError,KeyError): binding=''
        seen=set()
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0]>3:raise ValueError('Newer tasks')
            for session,title,directory,updated in db.execute("SELECT session,substr(title,1,200),directory,updated FROM tasks WHERE session!='' AND EXISTS(SELECT 1 FROM events WHERE task=tasks.id AND kind='input') ORDER BY updated DESC LIMIT 50"):
                if not isinstance(session,str) or not session or len(session)>256 or any(ord(c)<32 for c in session):continue
                if session.startswith(PREFIX) and (not binding or not session.startswith(PREFIX+binding+'/')):continue
                key=hashlib.sha256((str(directory)+'\0'+session).encode()).hexdigest()
                if key in seen:continue
                seen.add(key)
                rows.append(dict(target='conversation:'+key,kind='conversation',session=session,directory=directory,
                                 title=title or tr('Gespräch'),updated=updated,icon='dialog-messages'))
    return sorted(rows,key=lambda r:r['updated'],reverse=True)[:20]


def act(action, target=''):
    if action.startswith('focus:') and not target:
        focus_action(action.removeprefix('focus:'))
    elif action == 'recent':
        row=next((row for row in recent() if row['target']==target),None)
        if row is None:
            raise ValueError(tr('Dieser Inhalt ist nicht mehr verfügbar.'))
        from lumen_launch import executable
        if row['kind']=='conversation':
            directory=Path(row['directory'])
            if not directory.is_absolute() or not directory.is_dir():raise ValueError(tr('Dieser Inhalt ist nicht mehr verfügbar.'))
            command=[executable('lumen-agent-app'),'--directory',str(directory),'--session',row['session']]
        else:command=[executable('lumen-files'),row['path']]
        subprocess.Popen(command, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif action == 'update' and not target:
        from lumen_launch import executable
        subprocess.Popen([executable('lumen-updater')], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif action == 'decision':
        if not any(row['id'] == target for row in snapshot()['decisions']):
            raise ValueError(tr('Diese Freigabe ist nicht mehr offen.'))
        from lumen_launch import executable
        subprocess.Popen([executable('lumen-agent-app'), '--task', target], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise ValueError(tr('Ungültige Leistenaktion.'))


def act_request(topic, request):
    if (not isinstance(request,dict) or set(request)!={'action','target','value'}
            or not isinstance(request['action'],str) or not isinstance(request['target'],str)
            or '\0' in request['target'] or len(request['target'])>4096
            or type(request['value']) is not int or request['value']!=0
            or topic=='recent' and request['action']!='open'
            or topic=='activity' and request['action'] not in ('focus:start','focus:pause','focus:resume','focus:stop','decision','update')
            or topic not in ('activity','recent')):
        raise ValueError(tr('Ungültige Leistenaktion.'))
    act('recent' if topic=='recent' else request['action'],request['target'])
    return snapshot() if topic=='activity' else dict(items=recent())
