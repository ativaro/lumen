"""Opt-in, read-only follow-up for an existing interrupted native copy."""
import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

from lumen_i18n import tr, worker_environment
from lumen_store import Store
import lumen_transfers as transfers


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError(tr('Ungültige Übertragungskennung.'))
    return value


def supported(value):
    return bool(value and value['action'] == 'copy' and value.get('copy_plan')
                and value.get('stage_identity') and not value.get('discard'))


def clear_notice(value):
    identity = value.get('followup', {}).get('notification_id')
    if identity:
        from lumen_notifications import database
        try:
            with database() as db:
                db.execute("UPDATE notifications SET archived=1,updated=? WHERE id=? AND scope='local' AND revision<=?",
                           (time.time(), identity, value['followup'].get('notice', 0)))
        except ValueError:
            pass  # The user may already have removed the card.
        except (OSError, sqlite3.Error):
            return False
    return True


def configure(store, identity, enabled, now=None):
    identifier(identity)
    if type(enabled) is not bool:
        raise ValueError('Invalid follow-up state')
    now = time.time() if now is None else now
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE key=?', (transfers.PREFIX + identity,)).fetchone()
        if not row:
            raise ValueError(tr('Transfer nicht gefunden.'))
        value = json.loads(row[0])
        if enabled and (not supported(value) or value['status'] not in ('paused', 'failed')):
            raise ValueError(tr('Dranbleiben benötigt eine unterbrochene Kopie mit gespeichertem Kopierstand.'))
        old = value.get('followup', {})
        value['followup'] = dict(old, enabled=enabled, state='waiting' if enabled else 'off',
                                 revision=old.get('revision', 0) + 1, attempts=0, next_check=now,
                                 pending_notice=False)
        value['followup']['archive_pending'] = not clear_notice(value)
        db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(value), transfers.PREFIX + identity))
    return value


def snooze(store, identity, now=None):
    now = time.time() if now is None else now
    value = configure(store, identity, True, now=now + 3600)
    return value


def inspect(value):
    """Metadata only; partial contents are verified by the existing resume worker."""
    import drive_local as local
    if not supported(value):
        return 'review'
    plan = value['copy_plan']
    try:
        with local.directory(plan['root']):
            pass
        with local.directory(plan['root'], plan['stage']) as fd:
            st = os.fstat(fd)
            if [st.st_dev, st.st_ino] != value['stage_identity']:
                return 'review'
        for item in plan['items']:
            if item['source'] in value['done']:
                continue
            with local.directory(item['root']) as fd:
                st = os.stat(Path(item['source']).name, dir_fd=fd, follow_symlinks=False)
                entry = item['entries'][0]
                current = local.signature(st)
                if (current[:2] != entry['stamp'][:2] if entry['kind'] == 'dir' else current != entry['stamp']):
                    return 'review'
        try:
            local.capacity(plan['root'], max(0, value['total'] - value['bytes']))
        except ValueError:
            return 'waiting'
        return 'ready'
    except OSError:
        return 'waiting'
    except (ValueError, KeyError, IndexError, TypeError):
        return 'review'


def probe(store, identity):
    """One bounded child; its inherited lease also bounds stuck kernel I/O."""
    identifier(identity)
    try:
        lease = store.acquire('transfer-followup-probe')
    except BlockingIOError:
        return None  # Busy is not evidence about this copy's destination.
    child = None
    try:
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__)), '--probe', identity],
            env=worker_environment(LUMEN_DATA=str(store.directory)), pass_fds=(lease,),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            output, _ = child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            try:
                child.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                pass  # The inherited lease prevents more children until the kernel releases it.
            return 'waiting'
        result = output.decode().strip() if child.returncode == 0 else ''
        return result if result in ('ready', 'waiting', 'review') else 'waiting'
    except OSError:
        return 'waiting'
    finally:
        if child is not None and child.stdout is not None:
            child.stdout.close()
        os.close(lease)


def finish(store, value, result, now):
    identity = identifier(value['id'])
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE key=?', (transfers.PREFIX + identity,)).fetchone()
        if not row:
            return
        current = json.loads(row[0])
        follow = current.get('followup', {})
        if (not follow.get('enabled') or follow.get('revision') != value['followup']['revision']
                or current['status'] not in ('paused', 'failed') or current.get('discard')):
            return
        before = follow['state']
        follow['state'] = result
        if result == 'waiting':
            follow['pending_notice'] = False
            follow['attempts'] = min(6, follow.get('attempts', 0) + 1)
            follow['next_check'] = now + min(1800, 60 * 2 ** (follow['attempts'] - 1))
            follow['archive_pending'] = not clear_notice(current)
        else:
            follow.update(attempts=0, next_check=now + 300, enabled=result == 'ready')
            if before != result:
                follow['notice'] = follow.get('notice', 0) + 1
                # Reserve the exact existing notification key/revision before crossing databases.
                follow['notification_id'] = hashlib.sha256(json.dumps(
                    ['local', 'Lumen Files', 'transfer-followup:' + identity]).encode()).hexdigest()
                follow['pending_notice'] = True
                follow['archive_pending'] = False
        db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(current), transfers.PREFIX + identity))
    deliver(store, identity)


def deliver(store, identity):
    """Replay a committed intent; the Store lock fences opt-out/rearm through publication."""
    from lumen_notifications import publish
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE key=?', (transfers.PREFIX + identity,)).fetchone()
        if not row:
            return
        current = json.loads(row[0])
        follow = current.get('followup', {})
        if not follow.get('pending_notice'):
            return
        if current['status'] in ('paused', 'failed') and not current.get('discard') and follow['state'] in ('ready', 'review'):
            ready = follow['state'] == 'ready'
            title = tr('Dein Kopierziel ist wieder erreichbar.') if ready else tr('Deine Kopie benötigt eine erneute Prüfung.')
            body = tr('Die Kopie von „{0}“ ist noch unterbrochen. Öffne den gespeicherten Vorgang und wähle Fortsetzen. Vorhandene Teile werden dabei erneut geprüft.', Path(current['sources'][0]).name) if ready else tr('Ziel, Quelle oder Kopierzwischenablage wurden verändert. Öffne den Vorgang und prüfe ihn vor einem neuen Start.')
            publish('Lumen Files', 'transfer-followup:' + identity, title, body, target='transfer:' + identity,
                    revision=follow['notice'], attention=True)
        follow['pending_notice'] = False
        db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(current), transfers.PREFIX + identity))


def tick(store, now=None):
    now = time.time() if now is None else now
    try:
        lease = store.acquire('transfer-followup')
    except BlockingIOError:
        return
    try:
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute("SELECT key,value FROM settings WHERE key LIKE ? AND json_valid(value) AND json_extract(value,'$.followup.enabled')=0 AND json_extract(value,'$.followup.archive_pending')=1 LIMIT 3", (transfers.PREFIX + '%',)).fetchall()
            for row in rows:
                value = json.loads(row['value'])
                if clear_notice(value):
                    value['followup']['archive_pending'] = False
                    db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(value), row['key']))
        checked = 0
        pending = store.rows("SELECT value FROM settings WHERE key LIKE ? AND json_valid(value) AND json_extract(value,'$.followup.pending_notice')=1 ORDER BY json_extract(value,'$.followup.next_check') LIMIT 3", (transfers.PREFIX + '%',))
        for row in pending:
            checked += 1
            try:
                deliver(store, identifier(json.loads(row['value'])['id']))
            except (OSError, sqlite3.Error, ValueError):
                continue
        rows = store.rows("SELECT value FROM settings WHERE key LIKE ? AND json_valid(value) AND json_extract(value,'$.followup.enabled')=1 ORDER BY json_extract(value,'$.followup.next_check') LIMIT 20", (transfers.PREFIX + '%',))
        for row in rows:
            value = json.loads(row['value'])
            if value['status'] not in ('paused', 'failed') or not supported(value):
                configure(store, value['id'], False, now)
                continue
            if value['followup']['next_check'] > now:
                continue
            if checked == 3:
                break
            checked += 1
            try:
                result = probe(store, value['id'])
                if result is None:
                    continue
                finish(store, value, result, now)
            except (OSError, sqlite3.Error, ValueError):
                continue  # No committed result; the persisted due check retries next tick.
    finally:
        os.close(lease)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Lumen Dranbleiben')
    parser.add_argument('--probe', type=identifier, required=True)
    args = parser.parse_args()
    # Read-only access: a probe never constructs/migrates a Store or changes its ticket.
    from lumen_paths import state_path
    with sqlite3.connect((state_path() / 'lumen.sqlite3').as_uri() + '?mode=ro', uri=True, timeout=.2) as db:
        row = db.execute('SELECT value FROM settings WHERE key=?', (transfers.PREFIX + args.probe,)).fetchone()
    print(inspect(json.loads(row[0])) if row else 'review')
