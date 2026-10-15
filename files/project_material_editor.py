"""Material selection stays staged in the project sidebar until Save."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QComboBox,QLineEdit,QPlainTextEdit,QListWidget,QListWidgetItem,QFileDialog
from lumen_i18n import tr
from tools_ui import button,label,row
from tools_data import web_url


class MaterialEditor(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.serial=0;self.notes_job=None
        box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        self.kind=QComboBox();self.kind.setAccessibleName(tr('Materialart'))
        for title,value in [('Dateien','file'),('Ordner','folder'),('Weblink','url'),('Lumen Notes','wissen'),('Notiz','note')]:self.kind.addItem(tr(title),value)
        box.addWidget(self.kind);self.kind.currentIndexChanged.connect(self.change_kind)
        self.address=QLineEdit();self.address.setAccessibleName(tr('Webadresse'));self.address.setPlaceholderText('https://');box.addWidget(self.address)
        self.note=QPlainTextEdit();self.note.setAccessibleName(tr('Notiz'));self.note.setMaximumHeight(130);box.addWidget(self.note)
        self.pick=button(tr('Auswählen …'),lambda:window.safe(self.choose),'document-open');box.addWidget(self.pick)
        self.search=QLineEdit();self.search.setAccessibleName(tr('Notes durchsuchen'));self.search.setPlaceholderText(tr('Notes durchsuchen …'));box.addWidget(self.search)
        self.knowledge=QListWidget();self.knowledge.setAccessibleName(tr('Notes auswählen'));self.knowledge.setMaximumHeight(140);box.addWidget(self.knowledge)
        self.search.textChanged.connect(lambda text:[self.knowledge.item(i).setHidden(text.casefold() not in self.knowledge.item(i).text().casefold()) for i in range(self.knowledge.count())])
        self.knowledge.itemDoubleClicked.connect(lambda _:window.safe(self.choose))
        self.hint=label('','muted');self.hint.setWordWrap(True);box.addWidget(self.hint)
        self.stage_button=button(tr('Zur Auswahl hinzufügen'),lambda:window.safe(self.stage));box.addWidget(self.stage_button)
        self.empty=label(tr('Noch kein Material ausgewählt.'),'muted');box.addWidget(self.empty)
        window.resources=QListWidget();window.resources.setAccessibleName(tr('Projektmaterial'));window.resources.setMinimumHeight(100);window.resources.setMaximumHeight(190);window.resources.itemDoubleClicked.connect(lambda _:window.safe(window.open_resource));box.addWidget(window.resources,1)
        self.remove=button(tr('Verknüpfung entfernen'),lambda:window.safe(window.remove_resource))
        box.addWidget(row(button(tr('Öffnen'),lambda:window.safe(window.open_resource)),self.remove))
        window.resources.setContextMenuPolicy(Qt.CustomContextMenu);window.resources.customContextMenuRequested.connect(window.material_menu)
        window.server_material=QListWidget();window.server_material.setAccessibleName(tr('Material auf Lumen Server'));window.server_material.setMaximumHeight(110);box.addWidget(window.server_material)
        window.server_material.itemDoubleClicked.connect(lambda _:window.safe(window.open_server_material))
        box.addStretch(1)
        def selection_changed(*_):
            from shiboken6 import isValid
            if not isValid(self.empty) or not isValid(window.resources):return
            empty=window.resources.count()==0;self.empty.setVisible(empty);window.resources.setVisible(not empty)
        window.resources.model().rowsInserted.connect(selection_changed);window.resources.model().rowsRemoved.connect(selection_changed);window.resources.model().modelReset.connect(selection_changed);selection_changed()
        self.change_kind()

    def set_readonly(self,readonly):
        for control in (self.kind,self.address,self.note,self.pick,self.search,self.knowledge,self.stage_button,self.remove):control.setEnabled(not readonly)

    def reset(self):
        self.serial+=1;self.address.clear();self.note.clear();self.knowledge.clear();self.search.clear();self.change_kind()

    def dirty(self):return bool(self.address.text().strip() or self.note.toPlainText().strip())

    def change_kind(self,*_):
        kind=self.kind.currentData()
        self.address.setVisible(kind=='url');self.note.setVisible(kind=='note')
        self.pick.setVisible(kind in ('file','folder','wissen'));self.stage_button.setVisible(kind in ('url','note'))
        self.knowledge.setVisible(kind=='wissen');self.search.setVisible(kind=='wissen')
        self.pick.setText(tr('Notes laden') if kind=='wissen' else tr('Dateien auswählen …') if kind=='file' else tr('Ordner auswählen …'))
        self.hint.setText(tr('Dauerhafte Verknüpfung: neue und geänderte Textdateien und PDFs werden bei der nächsten Ordnersuche berücksichtigt. Kein automatischer Upload.') if kind=='folder' else tr('Dateien und Notes bleiben mit ihrem Original verknüpft.'))

    def choose(self):
        w=self.window;kind=self.kind.currentData()
        if kind=='wissen':
            item=self.knowledge.currentItem()
            if item and not item.isHidden():
                from interop_data import Registry
                ref=item.data(Qt.UserRole);self.append('file',Registry(w.library.root.parent).register(ref),ref['title']);return
            serial=self.serial;self.hint.setText(tr('Notes wird geladen …'))
            def ready(values,error):
                if serial!=self.serial:return
                self.knowledge.clear();self.hint.setText(error or tr('Eintrag auswählen und doppelklicken.'))
                for ref in values or []:
                    item=QListWidgetItem(ref['title']);item.setData(Qt.UserRole,ref);self.knowledge.addItem(item)
            self.load_notes(ready);return
        if kind=='file':paths,_=QFileDialog.getOpenFileNames(self,tr('Dateien verknüpfen'),str(Path.home()))
        else:
            path=QFileDialog.getExistingDirectory(self,tr('Ordner verknüpfen'),str(Path.home()));paths=[path] if path else []
        for path in paths:self.append('folder' if kind=='folder' else 'file',str(Path(path).resolve()) if kind=='folder' else path,Path(path).name)

    def load_notes(self, ready):
        if self.notes_job:return
        from tools_ui import Job
        job=Job(lambda _:note_sources(self.window.project_store),self);self.notes_job=job
        job.result.connect(lambda rows:ready(rows,''));job.failed.connect(lambda error:ready([],error))
        def finished():self.notes_job=None;job.deleteLater()
        job.finished.connect(finished);job.start()

    def append(self,kind,target,title):
        w=self.window
        for i in range(w.resources.count()):
            existing=w.resources.item(i);value=existing.data(Qt.UserRole)
            if value['target']==target:
                if kind=='folder' and value['kind']=='file':
                    existing.setData(Qt.UserRole,dict(value,kind='folder'));w.edited()
                return
        item=QListWidgetItem(title+'\n'+target);item.setData(Qt.UserRole,dict(kind=kind,target=target,title=title));w.resources.addItem(item);w.edited()
        self.hint.setText(tr('Ausgewählt · mit Speichern übernehmen.'))

    def stage_all(self):
        if self.address.text().strip():
            address=web_url(self.address.text());self.append('url',address,address);self.address.clear()
        if self.note.toPlainText().strip():
            w=self.window;w.notes.setPlainText((w.notes.toPlainText()+'\n\n'+self.note.toPlainText().strip()).strip());self.note.clear()

    def stage(self):
        if self.kind.currentData()=='url':
            address=web_url(self.address.text());self.append('url',address,address);self.address.clear()
        elif self.kind.currentData()=='note':
            text=self.note.toPlainText().strip()
            if not text:raise ValueError(tr('Bitte eine Notiz eingeben.'))
            w=self.window;w.notes.setPlainText((w.notes.toPlainText()+'\n\n'+text).strip());self.note.clear();w.edited();self.hint.setText(tr('Notiz vorgemerkt · mit Speichern übernehmen.'))


def note_sources(store):
    from wissen_data import Notebook
    book=Notebook(store)
    return [dict(app='wissen',kind='note',id=n['path'],title=n['title'],path=str(book.root/n['path']),locator=dict(root=str(book.root),area='user')) for n in book.scan()['notes']]
