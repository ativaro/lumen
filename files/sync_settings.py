"""Settings over the existing synchronizers; no model or new data transport."""
import fcntl
import json
import os
import time
from pathlib import Path

import lumen_connect as connector
from lumen_i18n import tr
from lumen_store import Store


def vault_root():
    return Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'lumen-vault-lab'


def prepare_connection():
    from sync_identity import prepare
    import memory_sync, projects_sync, drive_sync, wissen_sync, vault_sync
    from wissen_data import Notebook
    store = Store()
    connector.ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (connector.ROOT/'pairing.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = connector.read_config()
        if config.get('sync_binding'):
            return prepare(config, [])
        aliases = [(['memory'], memory_sync.connection_scope(config)),
                   (['projects'], projects_sync.scope(config)), (['drive'], drive_sync.scope(config))]
        roots = []
        if store.setting('knowledge/notebook'):
            roots.append(Notebook(store))
        choice = store.setting('knowledge/background-sync', {})
        if choice.get('root') and choice['root'] not in [str(book.root) for book in roots]:
            roots.append(Notebook(store, choice['root'], identity=choice['identity']))
        for book in roots:
            with book.directory(): pass
            aliases.append((['notes', str(book.root), list(book.identity), wissen_sync.workspace(book)],
                            wissen_sync.scope(book, config)))
        root = vault_root()
        if root.is_dir() and not root.is_symlink():
            meta = root.stat()
            aliases.append((['vault', str(root.absolute()), [meta.st_dev, meta.st_ino]], vault_sync.scope(root, config, meta)))
        prepared = prepare(config, aliases)
        if connector.read_config() != config: raise ValueError("Connection changed during setup")
        connector.save_private(connector.CONFIG, json.dumps(prepared))
        return prepared


def project_library():
    from tools_data import Library
    from projects_data import Projects
    library = Library('workbench')
    Projects(library)
    return library


def snapshot():
    import drive_sync, projects_sync
    store = Store()
    choice = store.setting('knowledge/background-sync', {})
    notes = store.setting('knowledge/server-sync/'+choice.get('scope', ''), {})
    memory = store.setting('memory/sync-choice', {})
    memory_state = store.setting('memory/server-sync/'+memory.get('scope', ''), {})
    projects = projects_sync.read_state(project_library())
    try:
        from vault_sync import execute
        vault = execute(dict(op='auto-status', root=str(vault_root()))) if vault_root().exists() else {}
    except (OSError, ValueError):
        vault = dict(enabled=False, reason='error')
    try:
        config = connector.read_config()
        server = config['server']
    except (OSError, ValueError): server = ''
    rows = dict(
        notes=dict(enabled=bool(choice.get('enabled')), last_sync=notes.get('last_sync', 0),
                   conflicts=store.setting('knowledge/background-status', {}).get('conflicts', 0)),
        attachments=dict(enabled=bool(notes.get('attachments')), last_sync=notes.get('last_sync', 0)),
        memory=dict(enabled=bool(memory.get('enabled')), last_sync=memory_state.get('last_sync', 0),
                    conflicts=len(memory_state.get('conflicts', {}))),
        projects=dict(enabled=bool(projects.get('enabled')), count=len(projects.get('projects', {})),
                      all_projects=bool(projects.get('all_projects')), conflicts=len(projects.get('conflicts', {})),
                      last_sync=projects.get('last_sync', 0)),
        vault=vault,
        preferences={k:v for k,v in store.setting('sync/preferences', {}).items() if k in ('enabled','last_sync','conflicts','reason')},
    )
    for domain, row in rows.items():
        report = store.setting('sync/report/'+domain, {})
        if report.get('time', 0) > row.get('last_sync', 0) and report.get('ok') is False:
            row['error'] = report.get('error', tr('Abgleich nicht abgeschlossen'))
        row['status'] = state_label(row)
    if not choice.get('enabled'): rows['attachments']['status'] = tr('Pausiert')
    rows['drive'] = [dict(id=r['id'], name=Path(r['path']).name, enabled=r['enabled'],
                          status=r.get('status', ''), conflicts=len(r.get('conflicts', {})),
                          skipped=len(r.get('errors', [])), last_sync=r.get('last_sync', 0))
                     for r in drive_sync.read()['roots']]
    rows['server'] = server
    return rows


def state_label(row):
    reason = row.get('reason', '')
    if row.get('conflicts') or reason in ('conflict', 'incoming'): return tr('Konflikt / neue Fassung prüfen')
    if reason in ('connection_changed', 'uncertain', 'remote_changed', 'error'): return tr('Prüfung erforderlich')
    if not row.get('enabled'): return tr('Pausiert')
    if reason == 'server_paused': return tr('Am Server pausiert')
    if row.get('error'): return tr('Prüfung erforderlich')
    if not row.get('last_sync') or time.time()-row['last_sync'] > 180: return tr('Wartet auf Abgleich')
    return tr('Aktuell')


def configure(domain, enabled):
    store = Store()
    if domain in ('notes', 'attachments'):
        from wissen_data import Notebook, activate
        import wissen_sync
        if not enabled:
            choice = store.setting('knowledge/background-sync', {})
            if choice.get('root'):
                book = Notebook(store, choice['root'], identity=choice['identity'])
                with book.lock('wissen-sync.lock'):
                    key = 'knowledge/server-sync/'+choice['scope']
                    state = store.setting(key, {})
                    state['enabled' if domain == 'notes' else 'attachments'] = False
                    store.set_setting(key, state)
                    if domain == 'notes':
                        choice['enabled'] = False
                        store.set_setting('knowledge/background-sync', choice)
            return
        activate(store)
        config = prepare_connection()
        book = Notebook(store)
        return wissen_sync.sync_config(book, wissen_sync.scope(book, config), True,
                                       attachments=True if domain == 'attachments' else None)
    if domain == 'memory':
        import memory_sync
        config = prepare_connection() if enabled else None
        return memory_sync.configure(store, enabled, memory_sync.connection_scope(config) if enabled else '')
    if domain == 'projects':
        import projects_sync
        if enabled: prepare_connection()
        return projects_sync.configure(project_library(), enabled, all_projects=True)
    if domain == 'drive':
        import drive_sync
        config = prepare_connection() if enabled else None
        with drive_sync.locked():
            state = drive_sync.read()
            if enabled and state['scope'] != drive_sync.scope(config):
                raise ValueError('Drive account changed; select folders again.')
            for root in state['roots']: root['enabled'] = bool(enabled)
            drive_sync.save(state)
        return
    if domain == 'vault':
        from vault_sync import execute
        if not enabled: return execute(dict(op='auto-disable', root=str(vault_root())))
        prepare_connection()
        info = execute(dict(op='info', root=str(vault_root())))
        return execute(dict(op='auto-enable', root=str(vault_root()), scope=info['scope']))
    if domain == 'preferences':
        import preferences_sync
        return preferences_sync.configure(store, enabled)
    raise ValueError('Unknown synchronization area')


def sync_now(progress=lambda text: None, manual=False):
    import wissen_sync, memory_sync, projects_sync, drive_sync, vault_sync
    store = Store()
    try:
        prepare_connection()
    except Exception as error:
        for name in ('notes','attachments','memory','projects','vault','preferences'):
            store.set_setting('sync/report/'+name, dict(time=time.time(),ok=False,error=type(error).__name__))
        raise
    from preferences_sync import synchronize as preferences
    def drive():
        roots = [r for r in drive_sync.read()['roots'] if r['enabled']]
        if not roots: return {}
        if manual:
            for root in roots: drive_sync.synchronize(root['id'])
            return drive_sync.read()
        return drive_sync.synchronize()
    operations = dict(notes=lambda: wissen_sync.background(store), memory=lambda: memory_sync.synchronize(store),
                      projects=lambda: projects_sync.synchronize(project_library()),
                      drive=drive,
                      vault=lambda: vault_sync.execute(dict(op='auto-poll', root=str(vault_root()))) if vault_root().exists() else {},
                      preferences=lambda: preferences(store))
    results = {}
    for name, operation in operations.items():
        progress(name)
        try:
            result = operation() or {}
            report = dict(time=time.time(), ok=True)
            results[name] = result
            if name in ('notes','memory'):
                conflicts=result.get('conflicts',0)
                if isinstance(conflicts,list): conflicts=len(conflicts)
                report.update(enabled=result.get('enabled',False),conflicts=conflicts)
        except Exception as error:
            # Remote error bodies may contain private data; expose only an error class.
            report = dict(time=time.time(), ok=False, error=type(error).__name__)
            results[name] = report
        store.set_setting('sync/report/'+name, report)
        if name in ('notes','memory'):
            store.set_setting('knowledge/background-status' if name=='notes' else 'memory/sync-status', report)
        if name=='notes':store.set_setting('sync/report/attachments',report)
        if name in ('notes','memory','projects','vault'):
            from lumen_notifications import report as notify
            outcome=results[name]
            bad=not report['ok'] or bool(outcome.get('conflicts')) or outcome.get('reason') in ('conflict','incoming','uncertain','connection_changed')
            notify('Lumen Synchronisation',name,bad,
                   tr('Abgleich braucht Aufmerksamkeit') if bad else tr('Abgleich wieder in Ordnung'),
                   tr('Öffne Server & Synchronisation und prüfe den betroffenen Bereich.') if bad else '',
                   target='app:settings')

    return results


if __name__ == '__main__':
    import signal
    import sys
    signal.alarm(180)
    try:
        request = json.load(sys.stdin)
        if request['action'] == 'configure': configure(request['domain'], request['enabled'])
        elif request['action'] == 'sync': sync_now(manual=request.get('manual',False))
        elif request['action'] == 'prepare': prepare_connection()
        else: raise ValueError('Unknown action')
        print(json.dumps(snapshot()))
    except Exception as error:
        print(json.dumps(dict(error=type(error).__name__)))
        sys.exit(1)
