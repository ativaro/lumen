"""A real directory-scoped Lumen conversation with read-only project inspection."""
import sqlite3
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QListWidget,QSplitter,QLabel
from lumen_i18n import tr
from tools_ui import button
from studio_chat import StudioChat
from studio_preview import StudioSurface
from code_library_execution import directory
from code_project import inspect_project,source_text


class CodingWindow(QMainWindow):
    def __init__(self,collection,identity,parent=None):
        super().__init__(parent);self.collection=collection;self.identity=identity;self.job=None;self.closing=False
        self.item=collection.get(identity);self.root=directory(collection,self.item)
        if self.item['archived']:raise ValueError(tr('Archivierte Einträge können nicht ausgeführt werden.'))
        self.setAttribute(Qt.WA_DeleteOnClose);self.setWindowTitle('Lumen Code · '+self.item['title']);self.setWindowIcon(QIcon.fromTheme('lumen-code'));self.resize(1380,850)
        from code_design import editor_shell
        container=QWidget();main,self.header,self.footer=editor_shell(container,self.windowTitle(),str(self.root));self.setCentralWidget(container)
        container.setStyleSheet(Path(__file__).with_name('studio.qss').read_text()+'\n'+container.styleSheet())
        self.back_to_collection=button(tr('‹ Zur Sammlung'),lambda:self.open_category('code'));self.header.actions.addWidget(self.back_to_collection)
        self.footer.setText(tr('Meine Sammlung')+' / '+self.item['title'])
        body=QVBoxLayout(main);body.setContentsMargins(0,0,0,0);body.setSpacing(0)
        self.chat=StudioChat(str(self.root));self.chat.tracker.store=collection.store
        self.studio=StudioSurface(self.chat,conversation_focus=True);body.addWidget(self.studio)
        self.studio.preview_wanted=True;self.studio.pane.show();self.studio.pane.setMaximumWidth(720)
        self.studio.result_tabs.blockSignals(True)
        while self.studio.result_tabs.count():self.studio.result_tabs.removeTab(0)
        self.studio.result_tabs.addTab(tr('Arbeitsschritte'));self.studio.result_tabs.blockSignals(False);self.studio.result_tabs.show()
        self.studio.result_tabs.setDrawBase(False)
        self.studio.result_tabs.setStyleSheet('QTabBar#studioResultTabs::tab { min-width:0;padding:8px 9px;margin-right:0;font-size:12px; }')
        self.studio.heading.hide();self.studio.close_preview.hide()
        self.chat.heading.hide();self.studio.directory.hide()
        self.studio.layout().itemAt(0).widget().setFixedHeight(44)
        self.code_context=self.header.subtitle
        self.project_status=QLabel(tr('Projekt wird gelesen …'))
        self.project_status.setWordWrap(True)
        file_page=QWidget();layout=QVBoxLayout(file_page);file_heading=QHBoxLayout();file_heading.addWidget(self.project_status,1)
        refresh=button(tr('Aktualisieren'),self.inspect);refresh.setToolTip(tr('Projektdateien und Git-Änderungen neu einlesen'));file_heading.addWidget(refresh);layout.addLayout(file_heading)
        split=QSplitter();self.files=QListWidget();self.files.setObjectName('codeSteps');self.files.setAccessibleName(tr('Projektdateien'));self.source=QPlainTextEdit();self.source.setObjectName('codeSource');self.source.setReadOnly(True);self.source.setAccessibleName(tr('Dateiinhalt'))
        self.files.setMinimumWidth(100);self.files.setMaximumWidth(220);self.source.setLineWrapMode(QPlainTextEdit.NoWrap)
        split.addWidget(self.files);split.addWidget(self.source);split.setStretchFactor(1,1);split.setSizes([120,360]);layout.addWidget(split,1)
        self.diff=QPlainTextEdit();self.diff.setObjectName('codeSource');self.diff.setReadOnly(True);self.diff.setAccessibleName(tr('Git-Änderungen gegenüber HEAD'))
        self.diff.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.checks=QPlainTextEdit();self.checks.setObjectName('codeSource');self.checks.setReadOnly(True);self.checks.setAccessibleName(tr('Tatsächlicher Auftragsstatus und Rückmeldung'))
        for title,page in [('Dateien',file_page),('Änderungen',self.diff),('Prüfung',self.checks)]:
            self.studio.result_tabs.addTab(tr(title));self.studio.result_pages.addWidget(page)
        self.files.itemActivated.connect(lambda item:self.open_source(item.text()))
        self.chat.backend.sessionChanged.connect(self.persist);self.chat.tracker.changed.connect(self.persist)
        self.chat.backend.completed.connect(lambda *_:self.inspect())
        self.chat.closeRequested.connect(self.close)
        session=self.item['definition'].get('session_id','')
        if session:
            try:self.chat.backend.select_session(session)
            except (ValueError,OSError) as error:self.project_status.setText(str(error))
        self.chat.composer.setPlainText(self.item['definition'].get('draft_prompt',self.item['definition'].get('prompt','')))
        self.studio.result_tabs.currentChanged.connect(self.update_inspector)
        self.studio.result_tabs.setCurrentIndex(2);self.update_inspector(2)
        self.studio.conversation_sized=True;self.studio.split.setSizes([800,400])
        QTimer.singleShot(0,self.inspect)

    def open_category(self,kind):
        if not self.close():return
        parent=self.parent()
        if parent and hasattr(parent,'categories'):
            parent.categories.setCurrentRow(parent.category_keys.index(kind))
            from lumen_activation import present
            present(parent)

    def update_inspector(self,index):
        self.studio.heading.setText(self.studio.result_tabs.tabText(index))
        self.studio.pane.setAccessibleName(self.studio.result_tabs.tabText(index))

    def inspect(self):
        if self.job or self.closing:return
        from lumen_jobs import Job
        self.job=Job(lambda job:inspect_project(self.root,job.command),self)
        self.job.result.connect(self.project_loaded);self.job.failed.connect(self.project_status.setText)
        job=self.job
        def finished():
            if self.job is job:self.job=None
            job.deleteLater()
        job.finished.connect(finished);job.start()

    def project_loaded(self,value):
        count=tr('1 Datei') if len(value['files'])==1 else tr('{0} Dateien',len(value['files']))
        self.project_status.setText(count+(' · '+value['branch'] if value['branch'] else ''));self.project_status.setToolTip(str(self.root))
        self.code_context.setText(self.root.name+(' · '+value['branch'] if value['branch'] else '')+' · '+count);self.code_context.setToolTip(str(self.root))
        self.files.clear();self.files.addItems(value['files'])
        self.diff.setPlainText(value['diff'] or tr('Keine Git-Änderungen gegenüber HEAD. Nicht eingecheckte neue Dateien stehen unter Dateien.'))
        self.update_checks()

    def open_source(self,relative):
        try:self.source.setPlainText(source_text(self.root,relative))
        except (OSError,ValueError) as error:self.project_status.setText(str(error))

    def update_checks(self):
        from lumen_store import STATES
        task=self.chat.tracker.task_id
        if not task:self.checks.setPlainText(tr('Noch kein Auftrag ausgeführt. Prüfbefehle und Werkzeugausgaben erscheinen unter Arbeitsschritte.'));return
        value=self.collection.store.task(task)
        self.checks.setPlainText(STATES.get(value['status'],value['status'])+'\n\n'+(value['error'] or value['result']))

    def persist(self,*_):
        try:self.save_draft()
        except (ValueError,OSError,sqlite3.Error) as error:self.project_status.setText(str(error))

    def save_draft(self):
        value=self.collection.get(self.identity)
        if directory(self.collection,value)!=self.root:raise ValueError(tr('Der Projektordner wurde geändert. Bitte das Coding-Fenster neu öffnen.'))
        definition={**value['definition'],'draft_prompt':self.chat.composer.toPlainText(),'session_id':self.chat.backend.session or ''}
        self.collection.update(self.identity,value['revision'],definition=definition)
        if self.chat.tracker.task_id:self.collection.used(self.identity,self.chat.tracker.task_id)
        self.update_checks()

    def closeEvent(self,event):
        if not self.chat.can_close():event.ignore();return
        try:self.save_draft()
        except (ValueError,OSError,sqlite3.Error) as error:
            self.project_status.setText(str(error));event.ignore();return
        self.closing=True
        if self.job:
            self.job.cancelled.set();self.job.wait(6000)
            if self.job.isRunning():self.closing=False;event.ignore();return
        self.studio.preview.shutdown();self.chat.tracker.interrupt();self.chat.context_tools.close();self.chat.backend.shutdown()
        event.accept()
