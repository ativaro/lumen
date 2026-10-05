"""Maintenance results with explicit links to the existing repair/setup flows."""
import json
from pathlib import Path
import sys
from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget
from lumen_i18n import tr, worker_process


def label(value):
    widget = QLabel(value); widget.setWordWrap(True); widget.setTextFormat(Qt.PlainText)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


class Troubleshooter(QWidget):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog; self.job = None; self.report = ''
        self.actions = {
            'updater': (tr('Lumen Updater öffnen'), lambda: self.open_updater()),
            'model': (tr('KI-Anbindung prüfen'), lambda: dialog.open_setup_wizard(1)),
            'setup': (tr('Erweiterungen einrichten'), lambda: dialog.open_setup_wizard(0)),
            'speech': (tr('Sprache einrichten'), lambda: dialog.open_setup_wizard(2)),
            'system': (tr('Lumen System öffnen'), dialog.open_system),
            'services': (tr('Dienste & Berichte öffnen'), lambda: dialog.open_page(5)),
            'recovery': (tr('Stabilität öffnen'), lambda: dialog.open_page(7)),
        }
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(14)
        root.addWidget(label(tr('Prüfe die Grundlagen von Lumen und erhalte passende nächste Schritte. Die Prüfung ändert keine Einstellungen.')))
        controls = QHBoxLayout(); root.addLayout(controls)
        self.start = QPushButton(tr('Prüfung starten')); self.start.setObjectName('primary'); self.start.clicked.connect(self.run)
        self.cancel = QPushButton(tr('Abbrechen')); self.cancel.clicked.connect(self.stop); self.cancel.hide()
        self.copy = QPushButton(tr('Diagnose kopieren')); self.copy.setEnabled(False); self.copy.clicked.connect(self.copy_report)
        for item in (self.start, self.cancel, self.copy): item.setAutoDefault(False); controls.addWidget(item)
        controls.addStretch()
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setAccessibleName(tr('Lumen wird geprüft')); self.progress.hide(); root.addWidget(self.progress)
        self.status = label(tr('Noch nicht geprüft.')); root.addWidget(self.status)
        self.results = QVBoxLayout(); self.results.setSpacing(12); root.addLayout(self.results)
        self.timer = QTimer(self); self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.stop(tr('Die Prüfung hat zu lange gedauert. Bitte erneut versuchen.')))

    def open_updater(self):
        from lumen_apps import launch
        try: launch('updater')
        except (OSError, ValueError): self.status.setText(tr('Lumen Updater konnte nicht geöffnet werden.'))

    def run(self):
        if self.job: return
        while self.results.count():
            item = self.results.takeAt(0); item.widget().hide(); item.widget().deleteLater()
        self.report = ''; self.copy.setEnabled(False); self.start.setEnabled(False)
        self.cancel.show(); self.progress.show(); self.status.setText(tr('Installation, Speicher und Dienste werden geprüft …'))
        job = worker_process(self); self.job = job
        job.finished.connect(lambda code, _status: self.finished(job, code))
        job.errorOccurred.connect(lambda error: self.finished(job, -1) if error == QProcess.FailedToStart else None)
        settings = self.dialog.assistant
        values = {key: str(settings.value(key, '')) for key in ('model', 'speechModel')}
        job.start(sys.executable, [str(Path(__file__).with_name('troubleshooter.py'))])
        job.write(json.dumps(values).encode()); job.closeWriteChannel(); self.timer.start(25000)

    def finished(self, job, code):
        if self.job is not job: return
        self.job = None; self.timer.stop(); self.start.setEnabled(True); self.cancel.hide(); self.progress.hide()
        output = bytes(job.readAllStandardOutput()); job.deleteLater()
        try:
            if code: raise ValueError('Worker failed')
            report = json.loads(output)
            self.show_report(report)
        except (ValueError, KeyError, TypeError):
            self.status.setText(tr('Die Prüfung konnte nicht abgeschlossen werden. Bitte erneut versuchen.'))

    def show_report(self, report):
        states = {'ok': tr('In Ordnung'), 'info': tr('Hinweis'), 'warning': tr('Bitte prüfen')}
        lines = ['Lumen Troubleshooter', report['checked_at']]; warnings = 0
        for check in sorted(report['checks'], key=lambda row: {'warning': 0, 'info': 1, 'ok': 2}[row['state']]):
            state = states[check['state']]; warnings += check['state'] == 'warning'
            card = QFrame(); card.setObjectName('card'); content = QVBoxLayout(card)
            title = label(check['title'] + ' · ' + state); font = title.font(); font.setBold(True); title.setFont(font)
            content.addWidget(title); content.addWidget(label(check['message']))
            caption, action = self.actions[check['action']]
            button = QPushButton(caption); button.setAutoDefault(False); button.clicked.connect(action)
            content.addWidget(button, 0, Qt.AlignLeft); self.results.addWidget(card)
            lines.extend(['', check['title'] + ' · ' + state, check['message']])
        self.status.setText(tr('Prüfung abgeschlossen: {0} Hinweise zum Prüfen.', warnings) if warnings else tr('Prüfung abgeschlossen. Keine Auffälligkeiten bei den geprüften Grundlagen.'))
        self.report = '\n'.join(lines); self.copy.setEnabled(True); self.start.setText(tr('Erneut prüfen'))

    def copy_report(self):
        if self.report:
            QApplication.clipboard().setText(self.report)
            self.status.setText(tr('Diagnose kopiert. Sie enthält Prüfergebnisse, aber keine Zugangsdaten oder Gesprächsinhalte.'))

    def stop(self, message=None):
        if not self.job: return
        job = self.job; self.job = None; self.timer.stop()
        job.terminate()
        if not job.waitForFinished(1000): job.kill(); job.waitForFinished(1000)
        job.deleteLater()
        self.start.setEnabled(True); self.cancel.hide(); self.progress.hide()
        self.status.setText(message if isinstance(message, str) else tr('Prüfung abgebrochen.'))
