"""Local process supervision and opt-in restoration; never replay an operation."""
from lumen_i18n import tr
import configparser
import faulthandler
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from lumen_store import state_path

NAMES = {'lumen': 'Lumen', 'files': 'Lumen Files', 'search': tr('Lumen Suche')}
RUN = None
LOCK = None
HEARTBEAT = None


def directory():
    path = state_path() / 'crashes'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise OSError(tr('Diagnoseverzeichnis darf kein Symlink sein.'))
    path.chmod(0o700)
    return path


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def read_json(path):
    try:
        if path.stat().st_size > 2_000_000: return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def inactive_runs():
    for path in sorted(directory().glob('run-*'), reverse=True):
        if not path.is_dir() or path.is_symlink(): continue
        try:
            with (path / 'lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                yield path
        except (OSError, BlockingIOError):
            continue


def recoveries(kind):
    result = []
    for path in inactive_runs():
        report = read_json(path / 'report.json')
        if report.get('app') != kind: continue
        if report.get('status') in ('running', 'hung'):
            report.update(status='interrupted', ended=time.time())
            write_json(path / 'report.json', report)
        if report.get('status') in ('crashed', 'interrupted') and not report.get('acknowledged'):
            result.append((path, report))
    return result


def acknowledge(path):
    report = read_json(path / 'report.json')
    report['acknowledged'] = True
    write_json(path / 'report.json', report)
    (path / 'state.json').unlink(missing_ok=True)


def enabled():
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'Lumen/Assistant.conf')
        return config.getboolean('General', 'crashDetection', fallback=True)
    except (configparser.Error, ValueError):
        return True


def notify(kind, hung=False):
    if not shutil.which('notify-send'): return None
    text = (tr('Die Oberfläche antwortet seit mindestens einer Minute nicht. Du kannst weiter warten. Beim Beenden können laufende Vorgänge unterbrochen werden.') if hung else
            tr('Die Anwendung wurde unerwartet beendet. Beim nächsten Start kannst du die letzte Ansicht wiederherstellen.'))
    try:
        return subprocess.Popen(['notify-send', '--wait', '-a', 'Lumen', '-i', 'lumen',
            '-A', 'restart=' + (tr('Beenden und neu öffnen') if hung else tr('Erneut öffnen')),
            '-A', tr('wait=Weiter warten') if hung else tr('wait=Später'), NAMES[kind], text],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None


def monitor(command, kind, *, hang_after=60, poll=.5):
    """The GUI is a child, so SIGKILL and a blocked Qt event loop remain observable."""
    for index, old in enumerate(inactive_runs()):
        if index >= 19: shutil.rmtree(old)
    path = Path(tempfile.mkdtemp(prefix='run-' + str(time.time_ns()) + '-', dir=directory()))
    lock = (path / 'lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    report = {'app': kind, 'started': time.time(), 'status': 'running', 'python': sys.version.split()[0]}
    write_json(path / 'report.json', report)
    reader, writer = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    env = os.environ | {'LUMEN_CRASH_RUN': str(path), 'LUMEN_GUARD_PID': str(os.getpid()),
                        'LUMEN_CRASH_LOCK': str(lock.fileno()), 'LUMEN_HEARTBEAT_FD': str(writer)}
    log = os.fdopen(os.open(path / 'stderr.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'ab', buffering=0)
    child = subprocess.Popen(command, env=env, stderr=log, pass_fds=(lock.fileno(), writer))
    os.close(writer)
    report['pid'] = child.pid
    write_json(path / 'report.json', report)
    last = time.monotonic(); hung = False; notice = None; restart = False; stopping = False
    previous = {}
    def stop(signum, _frame):
        nonlocal stopping
        stopping = True
        if child.poll() is None: child.send_signal(signum)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous[signum] = signal.signal(signum, stop)
    try:
        while child.poll() is None:
            try:
                if os.read(reader, 4096): last = time.monotonic()
            except BlockingIOError: pass
            now_hung = time.monotonic() - last >= hang_after
            if now_hung and not hung:
                report.update(status='hung', hang_detected=time.time())
                write_json(path / 'report.json', report)
                # Only signal after the child has installed faulthandler.
                if (path / 'ready').exists(): child.send_signal(signal.SIGUSR1)
                notice = notify(kind, True)
            elif hung and not now_hung:
                report.update(status='running', responsive_again=time.time())
                write_json(path / 'report.json', report)
                if notice and notice.poll() is None: notice.terminate()
                notice = None
            hung = now_hung
            if notice and notice.poll() is not None:
                choice = notice.communicate()[0].strip(); notice = None
                if choice == 'restart' and hung:
                    restart = True; child.terminate()
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired: child.kill(); child.wait()
            # Bound diagnostics even when a noisy Qt plugin keeps writing.
            if (path / 'stderr.log').stat().st_size > 1_000_000:
                with (path / 'stderr.log').open('rb+') as stream:
                    stream.seek(-64_000, os.SEEK_END); tail = stream.read()
                    stream.seek(0); stream.write(tail); stream.truncate()
            time.sleep(poll)
        code = child.wait()
    finally:
        if notice and notice.poll() is None: notice.terminate()
        for signum, handler in previous.items(): signal.signal(signum, handler)
        log.close(); os.close(reader)
    if code == 0:
        if 'hang_detected' in report:
            report.update(status='closed', ended=time.time(), exit_code=code)
            write_json(path / 'report.json', report)
            (path / 'state.json').unlink(missing_ok=True)
        else: shutil.rmtree(path)
    else:
        report.update(status='interrupted' if stopping or restart else 'crashed', ended=time.time(), exit_code=code)
        write_json(path / 'report.json', report)
    lock.close()
    if code != 0 and not restart and not stopping:
        notice = notify(kind)
        if notice:
            try: restart = notice.communicate(timeout=300)[0].strip() == 'restart'
            except subprocess.TimeoutExpired: notice.terminate(); notice.wait()
    if restart:
        # Original arguments can perform actions or send prompts. Never replay them.
        clean = dict(os.environ)
        for key in ('LUMEN_ASK_PROMPT', 'LUMEN_CRASH_RUN', 'LUMEN_GUARD_PID', 'LUMEN_CRASH_LOCK', 'LUMEN_HEARTBEAT_FD'): clean.pop(key, None)
        subprocess.Popen(command[:2], env=clean, start_new_session=True)
    return code


def supervise(kind):
    """Call before importing Qt at each real application entry point."""
    global RUN, LOCK, HEARTBEAT
    run = os.environ.pop('LUMEN_CRASH_RUN', '')
    parent = os.environ.pop('LUMEN_GUARD_PID', '')
    fd = os.environ.pop('LUMEN_CRASH_LOCK', '')
    heartbeat = os.environ.pop('LUMEN_HEARTBEAT_FD', '')
    if run and parent == str(os.getppid()) and fd:
        RUN = Path(run); LOCK = int(fd); HEARTBEAT = int(heartbeat)
        faulthandler.enable()
        faulthandler.register(signal.SIGUSR1, all_threads=True)
        (RUN / 'ready').touch(mode=0o600)
        return
    if enabled():
        code = monitor([sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]], kind)
        raise SystemExit(code if code >= 0 else 128 - code)


def attach(app, window, kind, offer_recovery=True):
    """Checkpoint an idle UI, not backend operations, and offer explicit recovery."""
    if RUN is None: return
    from lumen_qt import QTimer, QUrl
    timer = QTimer(app); timer.setInterval(1000)
    previous = None
    def checkpoint():
        nonlocal previous
        try: os.write(HEARTBEAT, b'1')
        except OSError: pass
        try:
            state = window.recovery_state()
            if state != previous:
                write_json(RUN / 'state.json', state); previous = state
            return True
        except (OSError, RuntimeError):
            # A full disk or a closing window must not itself crash the app.
            return False
    def offer():
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtWidgets import QMessageBox
        for path, report in recoveries(kind):
            lock = (path / 'lock').open('a')
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close(); continue
            if read_json(path / 'report.json').get('acknowledged'):
                lock.close(); continue
            box = QMessageBox(window)
            box.setWindowTitle(tr('Sitzung wiederherstellen'))
            box.setText(NAMES[kind] + tr(' wurde unerwartet beendet.') if report.get('status') == 'crashed'
                        else tr('Eine vorherige Sitzung von ') + NAMES[kind] + tr(' wurde unterbrochen.'))
            box.setInformativeText(tr('Letzte Ansicht und Entwurf wiederherstellen? Laufende Dateiaktionen und KI-Aufträge werden nicht erneut gestartet.'))
            restore = box.addButton(tr('Wiederherstellen'), QMessageBox.AcceptRole)
            later = box.addButton(tr('Später'), QMessageBox.RejectRole)
            discard = box.addButton(tr('Verwerfen'), QMessageBox.DestructiveRole)
            details = box.addButton(tr('Fehlerbericht'), QMessageBox.ActionRole)
            box.setDefaultButton(restore); box.setEscapeButton(later)
            details.clicked.connect(lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            try:
                box.exec_()
                if box.clickedButton() is restore:
                    state = read_json(path / 'state.json')
                    if not state: raise ValueError(tr('Für diese Sitzung wurde keine lesbare Ansicht gespeichert. Der Fehlerbericht bleibt verfügbar.'))
                    window.restore_recovery(state)
                    if not checkpoint(): raise OSError(tr('Die wiederhergestellte Ansicht konnte nicht gesichert werden. Die bisherige Sicherung bleibt erhalten.'))
                    acknowledge(path)
                    break
                elif box.clickedButton() is discard: acknowledge(path)
                else: break
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                QMessageBox.warning(window, tr('Wiederherstellung nicht möglich'), str(error))
                break
            finally:
                lock.close(); box.deleteLater()
    timer.timeout.connect(checkpoint)
    app.aboutToQuit.connect(timer.stop)
    timer.start(); checkpoint()
    app.crash_timer = timer
    if offer_recovery: QTimer.singleShot(0, offer)
