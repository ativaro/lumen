"""Explicit source selection for a paired server project's private question."""
from uuid import uuid4
from urllib.parse import urlencode
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QListWidget,QListWidgetItem,QLabel,QDialogButtonBox,QPushButton
from tools_ui import Job
from lumen_i18n import tr
import lumen_connect


class ProjectQuestion(QDialog):
    def __init__(self,journal,question):
        super().__init__(journal);self.journal=journal;self.question=question;self.job=None;self.data=None;self.request_id=str(uuid4())
        from projects_sync import read_state,scope
        self.config=lumen_connect.read_config();state=read_state(journal.window.library)
        if state.get('scope')!=scope(self.config):raise ValueError(tr('Anderes Serverkonto. Bitte zuerst erneut abgleichen.'))
        self.identity=state['projects'][journal.project]['remote']
        self.setWindowTitle(tr('Lumen Projekte · Frage mit Quellen'));self.resize(650,560)
        box=QVBoxLayout(self);caption=QLabel(question);caption.setWordWrap(True);box.addWidget(caption)
        info=QLabel(tr('Wähle bis zu 20 Quellen. Zugriffsrechte, KI-Freigaben und Versionen werden beim Senden erneut geprüft.'));info.setWordWrap(True);box.addWidget(info)
        self.sources=QListWidget();self.sources.setAccessibleName(tr('Projektquellen'));box.addWidget(self.sources,1)
        self.more=QPushButton(tr('Weitere Inhalte'));self.more.clicked.connect(lambda:self.load(self.data['next_offset']));box.addWidget(self.more);self.more.hide()
        self.message=QLabel();self.message.setWordWrap(True);box.addWidget(self.message)
        self.controls=QDialogButtonBox(QDialogButtonBox.Cancel);self.ask=self.controls.addButton(tr('Mit Quellen fragen'),QDialogButtonBox.AcceptRole);box.addWidget(self.controls)
        self.controls.rejected.connect(self.reject);self.ask.clicked.connect(self.submit)
        self.load()

    def run(self,operation,done):
        if self.job:return
        self.ask.setEnabled(False);self.sources.setEnabled(False);self.more.setEnabled(False)
        self.job=Job(lambda _:operation(),self)
        self.job.result.connect(done);self.job.failed.connect(self.message.setText)
        def finished():
            self.job.deleteLater();self.job=None;self.ask.setEnabled(self.data is not None);self.sources.setEnabled(True);self.more.setEnabled(True)
        self.job.finished.connect(finished);self.job.start()

    def load(self,offset=0):
        def loaded(value):
            if offset and value['project']['revision']!=self.data['project']['revision']:
                self.message.setText(tr('Projekt inzwischen geändert. Bitte Quellen neu laden.'));self.data=None;return
            if not offset:self.sources.clear()
            self.data=value
            for source in value['items']:
                item=QListWidgetItem((source['title'] or tr('Inhalt nicht mehr verfügbar'))+'\n'+tr(source['reason']));item.setData(Qt.UserRole,source)
                if source['eligible']:item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Unchecked)
                else:item.setFlags(item.flags()&~Qt.ItemIsEnabled)
                self.sources.addItem(item)
            self.more.setVisible(value['next_offset'] is not None)
            self.message.setText(tr('Das Gespräch bleibt privat. Es öffnet sich in Lumen Server.'))
        self.run(lambda:lumen_connect.request(self.config,f'/bridge/project-collections/{self.identity}/question-sources?offset={offset}'),loaded)

    def submit(self):
        if not self.data or self.job:return
        selected=[self.sources.item(i).data(Qt.UserRole) for i in range(self.sources.count()) if self.sources.item(i).checkState()==Qt.Checked]
        if not selected or len(selected)>20:self.message.setText(tr('Bitte 1 bis 20 Quellen auswählen.'));return
        body=dict(request_id=self.request_id,revision=self.data['project']['revision'],question=self.question,sources=[{k:s[k] for k in ('id','kind','revision')} for s in selected])
        def opened(value):
            self.journal.question.clear()
            QDesktopServices.openUrl(QUrl(self.config['server']+'/?'+urlencode(dict(app='conversations',task=value['task']['id']))))
            self.accept()
        self.run(lambda:lumen_connect.request(self.config,f'/bridge/project-collections/{self.identity}/questions',body),opened)

    def reject(self):
        if not self.job:super().reject()
