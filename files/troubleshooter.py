"""Local, read-only maintenance checks; output contains no paths or credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from lumen_i18n import tr


def installation(_settings):
    root = Path(__file__).parent
    complete = all((root / name).is_file() for name in (
        'app.py', 'search_qml.py', 'settings_dialog.py', 'assistant_backend.py',
        'qml/search/Search.qml', 'qml/search/ResultView.qml'))
    return ('ok', tr('Die zentralen Programmdateien sind vorhanden.')) if complete else (
        'warning', tr('Programmdateien fehlen. Öffne Lumen Updater, um die Installation zu erneuern.'))


def assistant(settings):
    from assistant_backend import ENGINE_VERSION
    from lumen_setup import executable
    from setup_diagnostics import version_text
    binary = executable('opencode')
    if not binary: return 'warning', tr('Die KI-Engine fehlt. Richte sie im Einrichtungsassistenten ein.')
    result = subprocess.run([binary, '--version'], capture_output=True, timeout=8)
    version = version_text(result.stdout)
    if result.returncode or version == 'unavailable':
        return 'warning', tr('Die KI-Engine antwortet nicht mit einer gültigen Version. Prüfe die Einrichtung.')
    if version != ENGINE_VERSION:
        return 'warning', tr('Engine {0} gefunden. Lumen ist mit {1} geprüft; die Einrichtung bietet die passende Version an.', version, ENGINE_VERSION)
    if not settings.get('model'):
        return 'info', tr('Die KI-Engine ist vorhanden. Kein eigenes Modell gewählt; prüfe die Anbietervorgabe in der Einrichtung.')
    return 'ok', tr('KI-Engine und Modellwahl sind vorhanden. Die Anbieter-Verbindung kannst du in der Einrichtung testen.')


def storage(_settings):
    from lumen_store import state_path
    path = state_path()
    while not path.exists() and not path.is_symlink() and path.parent != path: path = path.parent
    if not path.is_dir() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        return 'warning', tr('Der Speicherort für Lumen-Daten ist nicht zugänglich oder nicht beschreibbar. Prüfe Laufwerk und Zugriffsrechte.')
    free = shutil.disk_usage(path).free
    if free < 1024**3:
        return 'warning', tr('Weniger als 1 GB frei. Schaffe Platz, damit Lumen Daten und Updates speichern kann.')
    return 'ok', tr('Der Speicherort ist zugänglich; {0} GB sind frei.', round(free / 1024**3, 1))


def services(_settings):
    from desktop_settings import SERVICES
    failures = []; unavailable = False
    for scope in ('system', 'user'):
        names = [unit for (group, unit) in SERVICES if group == scope]
        result = subprocess.run(['systemctl', *(['--user'] if scope == 'user' else []), 'show',
            '--property=Id,LoadState,ActiveState,UnitFileState', *names], capture_output=True, text=True, timeout=4)
        if result.returncode: unavailable = True
        for block in result.stdout.strip().split('\n\n'):
            row = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
            unit = row.get('Id'); title = SERVICES.get((scope, unit))
            if not title: unavailable = True; continue
            if row.get('LoadState') == 'not-found': unavailable = True; continue
            if row.get('ActiveState') == 'failed' or (
                    row.get('UnitFileState') in ('enabled', 'enabled-runtime') and row.get('ActiveState') == 'inactive'):
                failures.append(title)
    if failures: return 'warning', tr('Diese Hintergrunddienste benötigen Aufmerksamkeit: {0}. Prüfe ihren Zustand unter Dienste & Berichte.', ', '.join(failures))
    if unavailable: return 'info', tr('Einige Hintergrunddienste fehlen oder sind nicht prüfbar. Optionale Dienste müssen nicht aktiviert sein.')
    return 'ok', tr('Keine Fehler bei den geprüften Hintergrunddiensten. Absichtlich deaktivierte Dienste bleiben aus.')


def crashes(_settings):
    from lumen_store import state_path
    reports = (state_path() / 'crashes').glob('run-*/report.json')
    recent = 0
    for path in reports:
        if path.stat().st_size > 65536: continue
        try: report = json.loads(path.read_text())
        except (OSError, ValueError): continue
        if not isinstance(report, dict): continue
        stamps = [report.get('hang_detected', 0)]
        if report.get('status') == 'crashed': stamps.append(report.get('ended', report.get('started', 0)))
        if any(isinstance(stamp, (int, float)) and stamp >= time.time() - 86400 for stamp in stamps): recent += 1
    if recent: return 'warning', tr('{0} Absturz- oder Hängerberichte in den letzten 24 Stunden. Unter Stabilität kannst du sie öffnen.', recent)
    return 'ok', tr('Keine gespeicherten Absturz- oder Hängerberichte aus den letzten 24 Stunden.')


def extensions(_settings):
    from lumen_setup import FEATURES, executable
    missing = [FEATURES[key][0] for key in ('documents', 'media', 'network')
               if not all(executable(command) for command in FEATURES[key][1])]
    if missing: return 'info', tr('Optionale Erweiterungen fehlen teilweise: {0}. Bei Bedarf in der Einrichtung ergänzen.', ', '.join(missing))
    return 'ok', tr('Die Hilfsprogramme für PDF, Medien und Netzwerkordner sind vorhanden.')


def speech(settings):
    from lumen_setup import executable
    model = settings.get('speechModel', '')
    if not model: return 'info', tr('Lokales Diktieren ist noch nicht eingerichtet. Du kannst es bei Bedarf aktivieren.')
    if not (Path(model).is_file() and executable('whisper-cli') and executable('pw-record')):
        return 'warning', tr('Für das gewählte Diktiermodell fehlen Bestandteile. Öffne die Spracheinrichtung zum Ergänzen und Mikrofontest.')
    return 'ok', tr('Diktiermodell und Aufnahmeprogramm sind vorhanden. Den Mikrofontest findest du in der Spracheinrichtung.')


def collect(settings):
    rows = []
    for check, title, action in (
        (installation, tr('Lumen-Installation'), 'updater'), (assistant, tr('KI-Grundlagen'), 'model'),
        (storage, tr('Datenspeicher'), 'system'), (services, tr('Hintergrunddienste'), 'services'),
        (crashes, tr('Abstürze & Hänger'), 'recovery'), (extensions, tr('Dateien & Vorschauen'), 'setup'),
        (speech, tr('Diktieren & Mikrofon'), 'speech')):
        try: state, message = check(settings)
        except (ImportError, OSError, ValueError, subprocess.SubprocessError):
            state, message = 'warning', tr('Diese Prüfung konnte nicht abgeschlossen werden. Öffne den zugehörigen Bereich oder prüfe erneut.')
        rows.append(dict(title=title, state=state, message=message, action=action))
    return dict(checked_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), checks=rows)


if __name__ == '__main__':
    import signal
    # Let subprocess.run clean up its child when the UI cancels this worker.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(130))
    settings = json.loads(sys.stdin.read(65536))
    if not isinstance(settings, dict): raise ValueError('Expected settings object')
    print(json.dumps(collect(settings), ensure_ascii=False))
