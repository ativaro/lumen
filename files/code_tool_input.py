"""Explicit file/project text selection before a reusable tool is run."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QPlainTextEdit,QComboBox,QFileDialog
from lumen_jobs import Job
from tools_ui import button,label,row
from lumen_i18n import tr


class ToolInputDialog(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.job=None;self.closing=False;self.value=''
        self.setWindowTitle(tr('Lumen · Werkzeugeingabe'));self.resize(680,620)
        box=QVBoxLayout(self);box.addWidget(label(tr('Eingabe auswählen und prüfen'),'codeTitle'))
        box.addWidget(label(tr('Erst mit „Übernehmen“ geht der Text in die Werkzeugeingabe. An die KI wird hier nichts gesendet.'),'codeMuted'))
        box.addWidget(button(tr('Datei auswählen'),self.choose_file))
        from lumen_projects import projects
        self.projects={p['id']:p for p in projects(store)};self.project=QComboBox();self.project.setAccessibleName(tr('Lumen-Projekt'));self.project.addItem(tr('Projekt wählen'),'')
        for p in self.projects.values():self.project.addItem(p['name'],p['id'])
        box.addWidget(row(self.project,button(tr('Projektnotiz lesen'),self.project_text)))
        self.text=QPlainTextEdit();self.text.setAccessibleName(tr('Geprüfte Werkzeugeingabe'));box.addWidget(self.text,1)
        self.status=label('','codeMuted');box.addWidget(self.status)
        self.use=button(tr('Übernehmen'),self.apply,primary=True);box.addWidget(row(button(tr('Abbrechen'),self.reject),self.use))

    def choose_file(self):
        if self.job:return
        path=QFileDialog.getOpenFileName(self,tr('Lumen · Quelldatei auswählen'))[0]
        if not path:return
        from code_blocks_run import read_file
        self.use.setEnabled(False);self.job=Job(lambda job:read_file(path,job),self)
        self.job.result.connect(lambda value:self.text.setPlainText(value['text']) if not self.closing else None);self.job.failed.connect(lambda message:self.status.setText(tr(message)));self.job.finished.connect(self.finished);self.job.start()

    def project_text(self):
        from lumen_projects import projects
        current=next((p for p in projects(self.store) if p['id']==self.project.currentData()),None)
        if current is None:self.status.setText(tr('Bitte ein verfügbares Projekt auswählen.'));return
        self.text.setPlainText(current['name']+'\n'+current.get('note',''))

    def finished(self):
        job,self.job=self.job,None;job.deleteLater();self.use.setEnabled(True)
        if self.closing:super().reject()

    def apply(self):
        value=self.text.toPlainText()
        if not value.strip() or len(value)>20000:self.status.setText(tr('Einen Auszug mit höchstens 20.000 Zeichen übernehmen.'));return
        self.value=value;self.accept()

    def reject(self):
        if self.job:self.closing=True;self.job.cancelled.set();return
        super().reject()
