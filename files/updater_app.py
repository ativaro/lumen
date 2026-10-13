"""Native Lumen updater: review first, then apply one checked revision."""
import json
from pathlib import Path
import sys
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QScrollArea, QFrame, QProgressBar, QPlainTextEdit)
from lumen_i18n import tr, worker_process
from settings_navigation import Details


def label(text, style=''):
    item=QLabel(text); item.setWordWrap(True); item.setTextFormat(Qt.PlainText)
    if style:item.setObjectName(style)
    return item


class UpdaterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Lumen Updater'); self.setWindowIcon(QIcon.fromTheme('lumen-updater', QIcon.fromTheme('system-software-update')))
        self.resize(880,740); self.setMinimumSize(620,540)
        self.plan=None; self.rows={}; self.buffer=b''; self.running=False; self.received_result=False
        layout=QVBoxLayout(self); layout.setContentsMargins(32,28,32,24); layout.setSpacing(18)
        top=QHBoxLayout(); mark=QLabel(); mark.setPixmap(QIcon.fromTheme('lumen-updater', QIcon.fromTheme('system-software-update')).pixmap(42,42)); top.addWidget(mark)
        heading=QVBoxLayout(); heading.addWidget(label('Lumen Updater','heading'))
        heading.addWidget(label(tr('Updates an einem Ort.'),'muted')); top.addLayout(heading,1)
        self.check_button=QPushButton(tr('Nach Updates suchen')); self.check_button.clicked.connect(self.check); top.addWidget(self.check_button)
        layout.addLayout(top)
        self.status=label(tr('Ein Ort für Lumen, deine Apps und ihre Erweiterungen.'))
        layout.addWidget(self.status)
        self.version=label(tr('Noch nicht geprüft.'),'muted'); layout.addWidget(self.version)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        content=QWidget(); self.list=QVBoxLayout(content); self.list.setContentsMargins(0,0,8,0); self.list.setSpacing(8)
        self.scroll.setWidget(content); layout.addWidget(self.scroll,1)
        self.empty=label(tr('Bei der Prüfung werden nur bereits installierte Komponenten berücksichtigt.'))
        self.list.addWidget(self.empty); self.list.addStretch()
        self.details=Details(tr('Was ist neu?')); self.notes=QPlainTextEdit(); self.notes.setReadOnly(True)
        self.notes.setAccessibleName(tr('Änderungen im Update')); self.notes.setMaximumHeight(130)
        self.details.content.addWidget(self.notes); self.details.hide(); layout.addWidget(self.details)
        self.progress=QProgressBar(); self.progress.setAccessibleName(tr('Update-Fortschritt')); self.progress.hide(); layout.addWidget(self.progress)
        layout.addWidget(label(tr('Persönliche Daten und Einstellungen bleiben erhalten. Offene Apps werden nicht beendet.'),'muted'))
        footer=QHBoxLayout(); self.selection=label('','muted'); footer.addWidget(self.selection,1)
        self.install_button=QPushButton(tr('Alles aktualisieren')); self.install_button.setObjectName('primary')
        self.install_button.setMinimumHeight(42); self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.apply); footer.addWidget(self.install_button); layout.addLayout(footer)
        self.proc=worker_process(self)
        self.proc.readyReadStandardOutput.connect(self.receive)
        self.proc.readyReadStandardError.connect(lambda:self.proc.readAllStandardError())
        self.proc.finished.connect(self.finished)
        self.proc.errorOccurred.connect(self.process_error)

    def set_plan(self,plan):
        self.plan=plan; self.rows={}
        while self.list.count():
            item=self.list.takeAt(0)
            if item.widget():item.widget().deleteLater()
        for row in plan['rows']:
            card=QFrame(); card.setObjectName('updateCard')
            card.setStyleSheet('QFrame#updateCard {background:palette(base);border:1px solid palette(mid);border-radius:12px;}')
            box=QHBoxLayout(card); box.setContentsMargins(16,12,16,12); box.setSpacing(14)
            choose=QCheckBox(); choose.setAccessibleName(row['title']); choose.setChecked(row['pending'] and not row['optional'])
            choose.setEnabled(row['pending']); box.addWidget(choose)
            copy=QVBoxLayout(); title=label(row['title']); font=title.font();font.setBold(True);title.setFont(font)
            copy.addWidget(title);copy.addWidget(label(row['detail'],'muted'));box.addLayout(copy,1)
            status=label(tr('Optional') if row['optional'] else tr('Prüfen & aktualisieren') if row['pending'] else tr('Aktuell'),'muted')
            box.addWidget(status); self.list.addWidget(card)
            self.rows[row['id']]=(choose,status); choose.toggled.connect(self.update_selection)
        self.list.addStretch(); self.version.setText(tr('Geprüfte Lumen-Version: {0}',plan['revision'][:8]))
        self.notes.setPlainText(plan.get('notes',''));self.details.show()
        self.status.setText(tr('Wähle, was aktualisiert werden soll. Große Modelle werden nur bei Bedarf geladen.'))
        if not any(row['pending'] and not row['optional'] for row in plan['rows']):
            self.status.setText(tr('Deine Lumen-Komponenten sind aktuell.'))
        self.update_selection()

    def update_selection(self):
        count=sum(control.isChecked() and control.isEnabled() for control,_ in self.rows.values())
        self.selection.setText(tr('{0} Komponenten ausgewählt',count))
        self.install_button.setEnabled(bool(count) and not self.running)

    def start(self,action,extra=()):
        if self.running:return
        self.running=True;self.buffer=b'';self.received_result=False
        self.check_button.setEnabled(False);self.install_button.setEnabled(False);self.scroll.setEnabled(False)
        self.progress.setRange(0,0);self.progress.show()
        self.status.setText(tr('Updates werden geprüft …') if action=='check' else tr('Aktualisierung wird vorbereitet …'))
        self.proc.start(sys.executable,[str(Path(__file__).with_name('updater_data.py')),action,*extra])

    def check(self):self.start('check')

    def apply(self):
        if not self.plan:return
        selected=[key for key,(box,_) in self.rows.items() if box.isChecked() and box.isEnabled()]
        if selected:self.start('apply',['--revision',self.plan['revision'],'--components',*selected])

    def receive(self):
        self.buffer+=bytes(self.proc.readAllStandardOutput())
        if len(self.buffer)>2_000_000:
            self.buffer=b'';return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:data=json.loads(line)
            except ValueError:continue
            if 'plan' in data:self.set_plan(data['plan']);self.received_result=True
            if 'message' in data:self.status.setText(data['message'])
            if 'error' in data:self.status.setText(data['error']);self.received_result=True
            if 'progress' in data:self.progress.setRange(0,100);self.progress.setValue(data['progress'])
            if data.get('component') in self.rows:
                control,status=self.rows[data['component']]
                state=data.get('state')
                if state=='running':self.progress.setRange(0,0)
                status.setText({'running':tr('Wird aktualisiert …'),'done':tr('Aktuell'),'failed':tr('Fehlgeschlagen')}.get(state,''))
                if state=='failed':
                    status.setToolTip(data.get('message',''));self.notes.appendPlainText('\n'+data.get('message',''))
                    self.details.toggle.setChecked(True)
                if state=='done':control.setChecked(False);control.setEnabled(False)
            if data.get('finished'):self.received_result=True

    def finished(self,code,*_):
        self.receive();self.running=False;self.check_button.setEnabled(True);self.scroll.setEnabled(True)
        self.progress.hide();self.update_selection()
        if not self.received_result:
            self.plan=None;self.install_button.setEnabled(False)
            self.status.setText(tr('Die Aktualisierung wurde unterbrochen. Bitte erneut prüfen.'))

    def process_error(self,error):
        if error==QProcess.FailedToStart:self.finished(1)

    def closeEvent(self,event):
        if self.running:
            self.status.setText(tr('Bitte den laufenden Schritt abwarten. Installationen werden nicht unterbrochen.'))
            event.ignore();return
        event.accept()


# Keep integrations that construct the previous widget working.
UpdaterWindow = UpdaterPage


def main():
    from system_app import main as system_main
    return system_main(['--page', 'updates'])


if __name__=='__main__':raise SystemExit(main())
