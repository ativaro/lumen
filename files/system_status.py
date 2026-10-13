"""The existing system metrics and watcher report, now owned by diagnostics."""
import os
import shutil
from pathlib import Path
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QMessageBox
from lumen_i18n import tr
from preview import label
from app import button
from assistant import Transcript


class SystemStatus(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.jobs = []; self.cpu_previous = None; self.report_text = ''
        QVBoxLayout(self).addWidget(self.build_system())
        self.timer = QTimer(self); self.timer.timeout.connect(lambda: self.refresh_system() if self.isVisible() else None)
        self.timer.start(5000)

    def showEvent(self, event):
        super().showEvent(event); self.refresh_system()

    def can_close(self):
        if not self.watch_button.isEnabled():
            self.report_status.setText(tr('Bitte die laufende Wächter-Prüfung vor dem Schließen abwarten.')); return False
        return True

    def shutdown(self):
        self.timer.stop()
        for job in self.jobs[:]: job.kill(); job.waitForFinished(1000)

    def build_system(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(label(tr('Systemstatus'), 'heading'))
        layout.addWidget(label(tr('Auslastung und der letzte Wächter-Bericht'), 'muted'))
        grid = QGridLayout()
        self.metrics = {}
        for i, (name, title) in enumerate((('CPU', 'CPU'), ('Arbeitsspeicher', tr('Arbeitsspeicher')),
                ('Laufwerk /', tr('Laufwerk /')), ('Grafikkarte', tr('Grafikkarte')),
                ('Benutzerdienste', tr('Benutzerdienste')), ('Systemdienste', tr('Systemdienste')))):
            card = QWidget()
            box = QVBoxLayout(card)
            box.addWidget(label(title, 'muted'))
            value = label('…', 'previewTitle')
            value.setWordWrap(True)
            box.addWidget(value)
            self.metrics[name] = value
            grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(grid)
        self.report = Transcript()
        self.report.setAccessibleName(tr('Letzter Systembericht'))
        layout.addWidget(self.report, 1)
        self.report_status = label('', 'muted')
        self.report_status.setWordWrap(True)
        layout.addWidget(self.report_status)
        actions = QHBoxLayout()
        actions.addWidget(button(tr('Aktualisieren'), self.refresh_system))
        self.watch_button = button(tr('Wächter prüfen'), self.run_watch)
        actions.addWidget(self.watch_button)
        actions.addWidget(button(tr('Mit Lumen besprechen'), self.discuss_report))
        layout.addLayout(actions)
        return page

    def run_job(self, program, arguments, callback, timeout=10000):
        job = QProcess(self)
        self.jobs.append(job)
        done = False
        timer = QTimer(job)
        timer.setSingleShot(True)
        timer.timeout.connect(job.kill)
        def finish(code):
            nonlocal done
            if done:
                return
            done = True
            timer.stop()
            output = bytes(job.readAllStandardOutput()).decode(errors='replace').strip()
            callback(code, output)
            self.jobs.remove(job)
            job.deleteLater()
        job.finished.connect(lambda code, _status: finish(code))
        job.errorOccurred.connect(lambda error: finish(-1) if error == QProcess.FailedToStart else None)
        job.start(program, arguments)
        timer.start(timeout)

    def refresh_system(self):
        try:
            cpu = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
            total, idle = sum(cpu), cpu[3] + cpu[4]
            if self.cpu_previous and total > self.cpu_previous[0]:
                usage = 100 * (1 - (idle - self.cpu_previous[1]) / (total - self.cpu_previous[0]))
                self.metrics['CPU'].setText(f'{usage:.0f} %')
            self.cpu_previous = (total, idle)
            mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
            self.metrics['Arbeitsspeicher'].setText(f"{(mem['MemTotal'] - mem['MemAvailable']) / 1048576:.1f} / {mem['MemTotal'] / 1048576:.1f} GiB")
            disk = shutil.disk_usage('/')
            self.metrics['Laufwerk /'].setText(tr('{0:.0f} % belegt', 100 * disk.used / disk.total))
        except (OSError, ValueError, KeyError):
            self.report_status.setText(tr('Einige Systemwerte sind nicht verfügbar.'))
        if not self.jobs:
            self.run_job('nvidia-smi', ['--query-gpu=utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'],
                         lambda code, out: self.metrics['Grafikkarte'].setText(out.replace(',', ' % ·') + ' °C' if code == 0 else tr('Nicht verfügbar')))
            for user, name in [(True, 'Benutzerdienste'), (False, 'Systemdienste')]:
                self.run_job('systemctl', (['--user'] if user else []) + ['--failed', '--no-legend', '--plain'],
                             lambda code, out, n=name: self.metrics[n].setText(tr('{0} fehlgeschlagen', len(out.splitlines())) if code == 0 else tr('Nicht verfügbar')))
        reports = [Path(os.environ.get('LUMEN_STATE', str(Path.home() / '.cache/lumen'))) / 'latest-analysis.md', Path('/var/lib/lumen/findings.md')]
        self.report_text = ''
        for path in reports:
            try:
                self.report_text += f'## {path.name}\n\n' + path.read_text() + '\n\n'
            except OSError:
                pass
        self.report.document().setMarkdown(self.report_text or tr('Noch kein Systembericht vorhanden.'), QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))

    def run_watch(self):
        self.watch_button.setEnabled(False)
        self.report_status.setText(tr('Wächter-Prüfung wird angefordert …'))
        system_install = Path('/usr/share/dbus-1/system-services/org.lumen.Agent.service').exists()
        def finished(code, out):
            self.watch_button.setEnabled(True)
            self.refresh_system()
            okay = code == 0 and (not system_install or out == 'b true')
            self.report_status.setText(tr('Prüfung angefordert. Der Bericht wird automatisch aktualisiert.') if okay
                                       else tr('Prüfung konnte nicht gestartet werden. Der Wächter-Dienst ist möglicherweise nicht verfügbar.'))
        if system_install:
            self.run_job('busctl', ['--system', '--timeout=10s', 'call', 'org.lumen.Agent',
                                  '/org/lumen/Agent', 'org.lumen.Agent', 'RefreshWatch'], finished)
        else:
            self.run_job(str(Path(os.environ.get('LUMEN_BIN_DIR', '/usr/bin')) / 'lumen-watch'), [], finished, 300000)

    def discuss_report(self):
        from lumen_detail_routes import launch
        try: launch('lumen-agent-app', ['--prompt', tr('Erkläre den folgenden Systembericht und priorisiere sinnvolle nächste Schritte.\n\n') + self.report_text])
        except OSError as error: self.report_status.setText(str(error))
