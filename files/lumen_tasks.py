"""Task lifecycle shared by the desktop and the opt-in user timer."""
import fcntl
import json
import os
from pathlib import Path
import subprocess

from lumen_store import Store
from lumen_actions import execute


def run_steps(store, task_id):
    lease = store.acquire(task_id)
    try: return _run_steps(store, task_id)
    finally: os.close(lease)


def _run_steps(store, task_id):
    task = store.task(task_id)
    if not task['steps']: raise ValueError('Dieser Auftrag benötigt Lumen im Vordergrund.')
    if not task['approved']: raise PermissionError('Auftrag zuerst freigeben.')
    if task['status'] not in ('queued', 'draft', 'paused', 'interrupted', 'failed', 'needs_input'):
        raise ValueError('Auftrag kann in diesem Zustand nicht gestartet werden.')
    with store.connect() as db:
        changed = db.execute("UPDATE tasks SET status='running',error='' WHERE id=? AND status=?", (task_id, task['status'])).rowcount
        if changed != 1: raise ValueError('Auftragsstatus wurde inzwischen geändert.')
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
    policy = store.setting('modelPolicy', {})
    if policy.get('pause_background', False): return 'Hintergrundaufträge sind pausiert.'
    limit = int(policy.get('gpu_limit', 90))
    if limit >= 100: return ''
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=3)
        if result.returncode == 0 and any(int(value.strip()) >= limit for value in result.stdout.splitlines()):
            return 'Auftrag wartet, bis die Grafikkarte weniger ausgelastet ist.'
    except (OSError, ValueError, subprocess.TimeoutExpired): pass
    return ''


def tick(store):
    lock = os.open(store.directory / 'worker.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        store.recover()
        store.enqueue_due()
        reason = defer_background(store)
        for item in store.rows("SELECT id FROM tasks WHERE status='queued' ORDER BY created LIMIT 20"):
            task = store.task(item['id'])
            if reason:
                store.update_task(task['id'], error=reason); continue
            if not task['steps'] or any(s['action'] in ('snapshot', 'install_packages', 'restart_service', 'launch', 'layout', 'open') for s in task['steps']):
                store.update_task(task['id'], status='needs_input', error='Lumen öffnen, um diesen Auftrag mit Werkzeugfreigaben fortzusetzen.')
                continue
            try: run_steps(store, task['id'])
            except Exception: pass  # The task stores the error; other approved tasks remain independent.
    finally: os.close(lock)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Lumen-Aufträge')
    parser.add_argument('--tick', action='store_true')
    parser.add_argument('--task')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args(); store = Store()
    if args.tick: tick(store)
    elif args.task: run_steps(store, args.task)
    else: print(json.dumps(store.tasks(), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
