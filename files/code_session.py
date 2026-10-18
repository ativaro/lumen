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
        from code_design import shell,navigation
        from tools_ui import label
        container=QWidget();main,nav,self.footer=shell(container);self.setCentralWidget(container)
        self.navigation=navigation(nav,self.close,self.open_category);self.navigation['code'].setChecked(True)
        self.footer.setText(tr('Meine Sammlung')+' / '+self.item['title'])
        body=QVBoxLayout(main);body.setContentsMargins(0,0,0,0);body.setSpacing(0)
        self.chat=StudioChat(str(self.root));self.chat.tracker.store=collection.store
        self.studio=StudioSurface(self.chat);body.addWidget(self.studio);self.studio.pane.show()
        self.studio.heading.hide();self.studio.close_preview.hide()
        self.chat.heading.hide();self.studio.directory.hide()
        heading=QWidget();head=QVBoxLayout(heading);head.setContentsMargins(0,8,0,8);head.setSpacing(3)
        self.code_context=label(str(self.root),'codeMuted');head.addWidget(self.code_context);head.addWidget(label(self.item['title'],'codeTitle'))
        header=self.studio.layout().itemAt(0).widget();header.setFixedHeight(96);header.layout().insertWidget(0,heading,1)
        self.project_status=QLabel(tr('Projekt wird gelesen …'))
        file_page=QWidget();layout=QVBoxLayout(file_page);layout.addWidget(self.project_status)
        layout.addWidget(button(tr('Projektdateien und Git-Änderungen aktualisieren'),self.inspect))
        split=QSplitter();self.files=QListWidget();self.files.setObjectName('codeSteps');self.files.setAccessibleName(tr('Projektdateien'));self.source=QPlainTextEdit();self.source.setObjectName('codeSource');self.source.setReadOnly(True);self.source.setAccessibleName(tr('Dateiinhalt'))
        split.addWidget(self.files);split.addWidget(self.source);split.setStretchFactor(1,1);layout.addWidget(split,1)
        self.diff=QPlainTextEdit();self.diff.setObjectName('codeSource');self.diff.setReadOnly(True);self.diff.setAccessibleName(tr('Git-Änderungen gegenüber HEAD'))
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
        self.studio.result_tabs.setCurrentIndex(3);self.update_inspector(3)
        self.studio.split.setSizes([620,500])
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
        self.studio.actions.parentWidget().setVisible(index==0)
        self.studio.choice.setVisible(index==0 and bool(self.studio.paths))

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
        self.project_status.setText(str(self.root)+(' · '+value['branch'] if value['branch'] else ''))
        self.code_context.setText(self.root.name+(' · '+value['branch'] if value['branch'] else '')+' · '+tr('{0} Dateien',len(value['files'])));self.code_context.setToolTip(str(self.root))
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
