"""Separate, staged project details and source dialogs with shared Lumen styling."""
import json
import sqlite3
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QWidget,QLineEdit,QPlainTextEdit,QComboBox,QListWidget,QListWidgetItem,QFileDialog,QMessageBox,QSizePolicy
from lumen_i18n import tr
from tools_ui import button,label,row,Job

STYLE='''
QDialog#projectDialog { background:#242929;color:#e9eeeb; }
QDialog#projectDialog QLabel { color:#e9eeeb;background:transparent; }
QDialog#projectDialog QLabel#dialogEyebrow { color:#afd3c5;font-size:10px;letter-spacing:1px; }
QDialog#projectDialog QLabel#dialogTitle { font-size:25px;font-weight:500; }
QDialog#projectDialog QLabel#muted { color:#a3b0aa;font-size:12px; }
QDialog#projectDialog QLineEdit,QDialog#projectDialog QPlainTextEdit,QDialog#projectDialog QComboBox,QDialog#projectDialog QListWidget { background:#1d2221;color:#e9eeeb;border:1px solid #46514a;border-radius:8px;padding:10px;font-size:13px; }
QDialog#projectDialog QLineEdit:focus,QDialog#projectDialog QPlainTextEdit:focus,QDialog#projectDialog QComboBox:focus { border-color:#afd3c5; }
QDialog#projectDialog QPushButton { background:transparent;color:#e9eeeb;border:1px solid #46514a;border-radius:8px;padding:10px 16px; }
QDialog#projectDialog QPushButton:hover,QDialog#projectDialog QPushButton:focus { border-color:#afd3c5;background:#303b35; }
QDialog#projectDialog QPushButton#primary { background:#afd3c5;color:#1b3027;border-color:#afd3c5;font-weight:600; }
QDialog#projectDialog QPushButton:disabled,QDialog#projectDialog QPushButton#primary:disabled { color:#88938d;background:#303632;border-color:#46514a; }
QDialog#projectDialog QWidget#dialogFooter { border-top:1px solid #3a4340;background:#222726; }
'''


class ProjectDialog(QDialog):
    def __init__(self,window,title,description):
        super().__init__(window);self.window=window;self.key=window.home.ensure_project()
        with window.library.connect() as db:
            record=db.execute('SELECT * FROM records WHERE id=?',(self.key,)).fetchone()
        if record is None:raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
        self.record=dict(json.loads(record['data']),title=record['title'],_archived=bool(record['archived']))
        self.revision=str(record['updated'])
        self.readonly=self.record['_archived'] or self.record.get('server_role')=='reader'
        self.setObjectName('projectDialog');self.setStyleSheet(STYLE);self.setWindowTitle(tr('Lumen Projekte')+' · '+title)
        self.setAttribute(Qt.WA_DeleteOnClose);self.setMinimumWidth(540);self.resize(620,640)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        header=QWidget();head=QVBoxLayout(header);head.setContentsMargins(32,28,32,22);head.setSpacing(8)
        head.addWidget(label(tr('LUMEN PROJEKTE'),'dialogEyebrow'));head.addWidget(label(title,'dialogTitle'));head.addWidget(label(description,'muted'));outer.addWidget(header)
        body=QWidget();self.form=QVBoxLayout(body);self.form.setContentsMargins(32,0,32,28);self.form.setSpacing(18);self.form.setAlignment(Qt.AlignTop);outer.addWidget(body,1)
        self.error=label('','muted');self.form.addWidget(self.error);self.error.hide()
        footer=QWidget();footer.setObjectName('dialogFooter');buttons=QVBoxLayout(footer);buttons.setContentsMargins(32,18,32,18)
        self.apply=button(tr('Änderungen speichern'),self.save,primary=True);self.apply.setEnabled(not self.readonly)
        controls=row(button(tr('Abbrechen'),self.reject),self.apply);controls.layout().insertStretch(0,1);buttons.addWidget(controls);outer.addWidget(footer)

    def field(self,title,widget):
        box=QWidget();box.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum);layout=QVBoxLayout(box);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        heading=label(title);heading.setBuddy(widget);widget.setAccessibleName(title)
        layout.addWidget(heading);layout.addWidget(widget);self.form.insertWidget(self.form.count()-1,box)
        return widget

    def commit(self,changes):
        try:
            if self.readonly:raise ValueError(tr('Dieses Projekt ist schreibgeschützt.'))
            self.window.library.update(self.key,expected_updated=self.revision,**changes)
            refresh_window(self.window,self.key);self.accept()
        except (ValueError,OSError,sqlite3.Error) as error:
            self.error.setText(str(error));self.error.show()


class ProjectDetails(ProjectDialog):
    def __init__(self,window):
        super().__init__(window,tr('Projekt bearbeiten'),tr('Worum geht es, und was möchtest du erreichen?'))
        self.title=self.field(tr('Projekttitel'),QLineEdit(self.record['title']))
        self.notes=self.field(tr('Anfängliche Notizen'),QPlainTextEdit(self.record.get('notes','')));self.notes.setFixedHeight(100)
        self.goal=self.field(tr('Ziele'),QPlainTextEdit(self.record.get('goal','')));self.goal.setFixedHeight(100)
        for control in (self.title,self.notes,self.goal):control.setReadOnly(self.readonly)
        self.title.setFocus()

    def save(self):self.commit(dict(title=self.title.text(),notes=self.notes.toPlainText(),goal=self.goal.toPlainText()))


class ProjectSources(ProjectDialog):
    def __init__(self,window,kind='file'):
        super().__init__(window,tr('Quelle hinzufügen'),tr('Wähle Inhalte aus, auf die Lumen Bezug nehmen soll.'))
        self.resize(620,500);self.pending=[];self.notes_job=None;self.serial=0
        self.kind=self.field(tr('Art der Quelle'),QComboBox())
        for title,value in [('Datei','file'),('Ordner','folder'),('Weblink','url'),('Lumen Notes','wissen')]:self.kind.addItem(tr(title),value)
        self.address=self.field(tr('Webadresse'),QLineEdit());self.address.setPlaceholderText('https://')
        self.pick=button(tr('Dateien auswählen …'),self.choose);self.form.insertWidget(self.form.count()-1,self.pick)
        self.notes=QListWidget();self.notes.setAccessibleName(tr('Notes auswählen'));self.notes.setMaximumHeight(140);self.form.insertWidget(self.form.count()-1,self.notes)
        self.notes.itemDoubleClicked.connect(lambda _:self.choose())
        self.hint=label('','muted');self.form.insertWidget(self.form.count()-1,self.hint)
        self.selected=QListWidget();self.selected.setAccessibleName(tr('Ausgewählte Quellen'));self.selected.setMaximumHeight(120);self.form.insertWidget(self.form.count()-1,self.selected)
        self.apply.setText(tr('Quelle verknüpfen'));self.apply.setEnabled(False)
        self.kind.currentIndexChanged.connect(self.change_kind);self.address.textChanged.connect(self.changed)
        self.kind.setCurrentIndex(max(0,self.kind.findData(kind)));self.change_kind()
        self.kind.setEnabled(not self.readonly);self.pick.setEnabled(not self.readonly);self.address.setReadOnly(self.readonly)

    def changed(self):self.apply.setEnabled(not self.readonly and bool(self.pending or self.kind.currentData()=='url' and self.address.text().strip()))

    def change_kind(self):
        self.serial+=1;kind=self.kind.currentData();self.notes.clear()
        self.address.parentWidget().setVisible(kind=='url');self.notes.setVisible(kind=='wissen');self.pick.setVisible(kind!='url')
        self.pick.setText(tr('Notes laden') if kind=='wissen' else tr('Ordner auswählen …') if kind=='folder' else tr('Dateien auswählen …'))
        self.hint.setText(tr('Dauerhafte Verknüpfung: neue und geänderte Textdateien und PDFs werden bei der nächsten Ordnersuche berücksichtigt. Kein automatischer Upload.') if kind=='folder' else tr('Verknüpfte Originale bleiben an ihrem Ort.'))
        self.selected.setVisible(bool(self.pending));self.changed()

    def append(self,kind,target,title):
        from projects_references import validate
        value=validate(dict(kind=kind,target=target,title=title),self.window.library.root.parent)
        self.pending=[r for r in self.pending if r['target']!=value['target']]+[value]
        self.selected.clear();self.selected.addItems([r['title'] for r in self.pending]);self.selected.show();self.changed()

    def choose(self):
        try:
            kind=self.kind.currentData()
            if kind=='wissen':
                item=self.notes.currentItem()
                if item:
                    from interop_data import Registry
                    ref=item.data(Qt.UserRole);self.append('object',Registry(self.window.library.root.parent).register(ref),ref['title']);return
                if self.notes_job:return
                from project_material_editor import note_sources
                from shiboken6 import isValid
                serial=self.serial;self.hint.setText(tr('Notes wird geladen …'))
                window=self.window;store=window.project_store;job=Job(lambda _:note_sources(store),window);self.notes_job=job;window.project_source_jobs.add(job)
                def ready(values,error=''):
                    if not isValid(self) or serial!=self.serial:return
                    self.notes.clear();self.hint.setText(error or tr('Eintrag auswählen und doppelklicken.'))
                    for ref in values:
                        item=QListWidgetItem(ref['title']);item.setData(Qt.UserRole,ref);self.notes.addItem(item)
                def done():
                    window.project_source_jobs.discard(job)
                    if isValid(self):self.notes_job=None
                    job.deleteLater()
                job.result.connect(ready);job.failed.connect(lambda error:ready([],error));job.finished.connect(done);job.start();return
            if kind=='folder':
                path=QFileDialog.getExistingDirectory(self,tr('Ordner verknüpfen'),str(Path.home()));paths=[path] if path else []
            else:paths,_=QFileDialog.getOpenFileNames(self,tr('Dateien verknüpfen'),str(Path.home()))
            for path in paths:self.append(kind,str(Path(path).resolve()),Path(path).name)
        except (ValueError,OSError,sqlite3.Error) as error:self.error.setText(str(error));self.error.show()

    def save(self):
        try:
            if self.kind.currentData()=='url' and self.address.text().strip():self.append('url',self.address.text().strip(),self.address.text().strip())
            if not self.pending:return
            resources=list(self.record.get('resources',[]))
            for value in self.pending:
                matches=[r for r in resources if r['target']==value['target']]
                if not matches:resources.append(value)
                elif value['kind']=='folder':resources=[value if r['target']==value['target'] else r for r in resources]
            self.commit(dict(resources=resources))
        except (ValueError,OSError,sqlite3.Error) as error:self.error.setText(str(error));self.error.show()


def open_dialog(window,kind='details'):
    if not window.editor.allow_leave():return
    window.editor.hide()
    # Both dialogs edit the project itself, independently of the selected task.
    dialog=ProjectDetails(window) if kind=='details' else ProjectSources(window,kind)
    window.project_dialog=dialog;dialog.open()
    return dialog


def refresh_window(window,key):
    if window.current==key and not window.scope:
        window.loading=True
        try:window.load_fields(window.library.get(key))
        finally:window.loading=False
    window.refresh();window.home.refresh()


def remove_source(window,key,value):
    if not window.editor.allow_leave():return
    with window.library.connect() as db:
        record=db.execute('SELECT * FROM records WHERE id=?',(key,)).fetchone()
    if record is None:raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
    resources=json.loads(record['data']).get('resources',[])
    if value not in resources:raise ValueError(tr('Die Quelle wurde inzwischen geändert.'))
    if QMessageBox.question(window,tr('Lumen Projekte · Quelle entfernen'),tr('Verknüpfung aus diesem Projekt entfernen? Das Original bleibt erhalten.'),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
    window.library.update(key,expected_updated=str(record['updated']),resources=[r for r in resources if r!=value])
    refresh_window(window,key)
