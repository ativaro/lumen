"""Project files, web references, notes and open questions in a native workspace."""
from pathlib import Path
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QLineEdit, QPlainTextEdit, QListWidget, QListWidgetItem,
    QInputDialog, QFileDialog, QTabWidget, QWidget, QVBoxLayout)
from tools_data import web_url
from tools_ui import ToolWindow, button, label, row, open_path


class Workbench(ToolWindow):
    def __init__(self,root=None):
        super().__init__('workbench','Projekt-Werkbank','Alles, was zu deinem Vorhaben gehört.','folder-development',root)
        self.add_button.setText('Projekt anlegen')
        self.title=QLineEdit(); self.title.setPlaceholderText('Lege dein erstes Projekt an'); self.title.setAccessibleName('Projektname'); self.title.textEdited.connect(self.edited)
        self.content.addWidget(self.title)
        self.tabs=QTabWidget(); self.content.addWidget(self.tabs,1)
        notes_page=QWidget(); notes_layout=QVBoxLayout(notes_page); notes_layout.setContentsMargins(0,12,0,0)
        notes_layout.addWidget(label('Gedanken & Notizen','heading'))
        self.notes=QPlainTextEdit(); self.notes.setAccessibleName('Projektnotizen'); self.notes.setPlaceholderText('Worum geht es? Was ist der nächste Schritt?\n\nDeine Notizen werden automatisch gespeichert.'); self.notes.textChanged.connect(self.edited); notes_layout.addWidget(self.notes,2)
        notes_layout.addWidget(label('Offene Fragen','heading'))
        self.questions=QListWidget(); self.questions.setObjectName('searchResults'); self.questions.setAccessibleName('Offene Fragen'); self.questions.itemChanged.connect(self.edited); notes_layout.addWidget(self.questions,1)
        self.question=QLineEdit(); self.question.setPlaceholderText('Neue Frage …'); self.question.setAccessibleName('Neue Frage'); self.question.textEdited.connect(self.edited); self.question.returnPressed.connect(lambda:self.safe(self.add_question))
        notes_layout.addWidget(row(self.question,button('Hinzufügen',lambda:self.safe(self.add_question),'list-add'),button('Entfernen',lambda:self.safe(self.remove_question),'list-remove')))
        self.tabs.addTab(notes_page,'Notizen & Fragen')
        resources=QWidget(); resources_layout=QVBoxLayout(resources); resources_layout.setContentsMargins(0,12,0,0)
        resources_layout.addWidget(label('Dateien & Webseiten','heading'))
        resources_layout.addWidget(label('Dateien bleiben an ihrem Ort – auch auf eingebundenen Netzlaufwerken. Ein Doppelklick öffnet sie in ihrer Anwendung.', 'muted'))
        self.resources=QListWidget(); self.resources.setObjectName('searchResults'); self.resources.setAccessibleName('Projektmaterial'); self.resources.itemDoubleClicked.connect(lambda _:self.safe(self.open_resource)); resources_layout.addWidget(self.resources,1)
        resources_layout.addWidget(row(button('Dateien',lambda:self.safe(self.add_files),'document-open',True),button('Ordner',lambda:self.safe(self.add_folder),'folder'),
            button('Webseite',lambda:self.safe(self.add_link),'internet-web-browser'),button('Öffnen',lambda:self.safe(self.open_resource),'document-open'),button('Entfernen',lambda:self.safe(self.remove_resource),'list-remove')))
        self.tabs.addTab(resources,'Material')
        self.content.addWidget(button('Projektübersicht exportieren',lambda:self.safe(self.export),'document-export'))
        self.body.setEnabled(False); self.refresh()

    def create(self):
        title,ok=QInputDialog.getText(self,'Neues Projekt','Projektname')
        if ok and title.strip(): self.save(); self.focus_record(self.library.create(title,notes='',questions=[],resources=[]))

    def load(self,r):
        self.title.setText(r['title']); self.notes.setPlainText(r.get('notes','')); self.questions.clear(); self.resources.clear()
        for q in r.get('questions',[]):
            item=QListWidgetItem(q['text']); item.setFlags(item.flags()|Qt.ItemIsEditable|Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if q.get('done') else Qt.Unchecked); self.questions.addItem(item)
        for resource in r.get('resources',[]):
            item=QListWidgetItem(resource['title']+'\n'+resource['target']); item.setData(Qt.UserRole,resource); self.resources.addItem(item)
        self.question.setText(r.get('question_draft','')); self.status.setText('Änderungen werden automatisch gespeichert · Dateien bleiben an ihrem Ort')

    def save(self):
        super().save()
        if not self.current or self.loading: return
        questions=[dict(text=self.questions.item(i).text(),done=self.questions.item(i).checkState()==Qt.Checked) for i in range(self.questions.count())]
        resources=[self.resources.item(i).data(Qt.UserRole) for i in range(self.resources.count())]
        self.library.update(self.current,title=self.title.text(),notes=self.notes.toPlainText(),questions=questions,resources=resources,question_draft=self.question.text())
        self.status.setText('Lokal gespeichert'); self.refresh()

    def add_question(self):
        text=self.question.text().strip()
        if not text: return
        item=QListWidgetItem(text); item.setFlags(item.flags()|Qt.ItemIsEditable|Qt.ItemIsUserCheckable); item.setCheckState(Qt.Unchecked)
        self.questions.addItem(item); self.question.clear(); self.save()

    def remove_question(self):
        i=self.questions.currentRow()
        if i>=0: self.questions.takeItem(i); self.save()

    def add_resource(self,kind,target,title):
        if any(self.resources.item(i).data(Qt.UserRole)['target']==target for i in range(self.resources.count())): return
        item=QListWidgetItem(title+'\n'+target); item.setData(Qt.UserRole,dict(kind=kind,target=target,title=title)); self.resources.addItem(item); self.save()

    def add_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Dateien verknüpfen',str(Path.home()))
        for path in paths: self.add_resource('file',path,Path(path).name)

    def add_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Ordner verknüpfen',str(Path.home()))
        if path: self.add_resource('file',path,Path(path).name)

    def add_link(self):
        value,ok=QInputDialog.getText(self,'Webseite verknüpfen','Webadresse')
        if ok and value.strip():
            address=web_url(value); self.add_resource('url',address,QUrl(address).host())

    def open_resource(self):
        item=self.resources.currentItem()
        if not item: return
        value=item.data(Qt.UserRole)
        if value['kind']=='file': open_path(value['target'])
        elif not QDesktopServices.openUrl(QUrl(web_url(value['target']))): raise ValueError('Browser konnte nicht geöffnet werden.')

    def remove_resource(self):
        i=self.resources.currentRow()
        if i>=0: self.resources.takeItem(i); self.save(); self.status.setText('Verknüpfung entfernt. Die Datei bleibt erhalten.')

    def export(self):
        self.save(); r=self.library.get(self.current)
        text='# '+r['title']+'\n\n'+r.get('notes','')+'\n\n## Fragen\n\n'
        text+='\n'.join(('- [x] ' if q['done'] else '- [ ] ')+q['text'] for q in r.get('questions',[]))
        text+='\n\n## Material\n\n'+'\n'.join('- '+v['title']+': '+v['target'] for v in r.get('resources',[]))
        self.export_text(text,'projekt.md')
