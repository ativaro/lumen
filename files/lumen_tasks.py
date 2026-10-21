"""Task lifecycle shared by the desktop and the opt-in user timer."""
from lumen_i18n import tr
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sqlite3

from lumen_store import Store
from lumen_actions import execute


def run_steps(store, task_id):
    lease = store.acquire(task_id)
    try: return _run_steps(store, task_id)
    finally: os.close(lease)


def reject_code_task(store,task_id):
    from code_flow_native import check_task
    try:
        with store.connect() as db:check_task(db,task_id)
    except ValueError as error:
        store.update_task(task_id,status='failed',error=str(error))
        raise


def _run_steps(store, task_id):
    reject_code_task(store,task_id)
    task = store.task(task_id)
    if not task['steps']: raise ValueError(tr('Dieser Auftrag benötigt Lumen im Vordergrund.'))
    if not task['approved']: raise PermissionError(tr('Auftrag zuerst freigeben.'))
    if task['status'] not in ('queued', 'draft', 'paused', 'interrupted', 'failed', 'needs_input'):
        raise ValueError(tr('Auftrag kann in diesem Zustand nicht gestartet werden.'))
    with store.connect() as db:
        changed = db.execute("UPDATE tasks SET status='running',error='' WHERE id=? AND status=?", (task_id, task['status'])).rowcount
        if changed != 1: raise ValueError(tr('Auftragsstatus wurde inzwischen geändert.'))
    try:
        for position in range(task['cursor'], len(task['steps'])):
            status = store.task(task_id)['status']
            if status in ('paused', 'cancelled'): return
            store.event(task_id, 'checkpoint', str(position))
            result = execute(store, task_id, task['steps'][position])
            # Preserve a cancellation arriving while a non-interruptible action finishes.
            store.update_task(task_id, cursor=position + 1, result=result)
        if store.task(task_id)['status'] == 'running':
            store.update_task(task_id, status='completed')
    except Exception as exc:
        if store.task(task_id)['status'] in ('paused', 'cancelled'): return
        store.update_task(task_id, status='failed', error=str(exc))
        store.event(task_id, 'failed', str(exc))
        raise


def defer_background(store):
    from lumen_hardware import background_reason
    return background_reason(store)


def tick(store):
    try:
        from transfer_followup import tick as followup_tick
        followup_tick(store)
    except (ImportError, OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        print(tr('Lumen Dranbleiben konnte nicht prüfen. Die freigegebenen Aufträge werden weiter bearbeitet.'))
    lock = os.open(store.directory / 'worker.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        store.recover()
        store.enqueue_due()
        reason = defer_background(store)
        for item in store.rows("SELECT id FROM tasks WHERE status='queued' ORDER BY created LIMIT 20"):
            try:reject_code_task(store,item['id'])
            except ValueError:continue
            task = store.task(item['id'])
            if reason:
                store.update_task(task['id'], error=reason); continue
            if not task['steps'] or any(s['action'] in ('snapshot', 'install_packages', 'restart_service', 'launch', 'layout', 'open') for s in task['steps']):
                store.update_task(task['id'], status='needs_input', error=tr('Lumen öffnen, um diesen Auftrag mit Werkzeugfreigaben fortzusetzen.'))
                continue
            try: run_steps(store, task['id'])
            except Exception: pass  # The task stores the error; other approved tasks remain independent.
    finally: os.close(lock)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=tr('Lumen-Aufträge'))
    parser.add_argument('--tick', action='store_true')
    parser.add_argument('--task')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args(); store = Store()
    if args.tick: tick(store)
    elif args.task: run_steps(store, args.task)
    else: print(json.dumps(store.tasks(), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
