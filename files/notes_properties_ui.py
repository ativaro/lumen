"""Property edits remain a normal private draft until the existing autosave writes it."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QComboBox,QLabel,QDialogButtonBox,QTableWidget,QTableWidgetItem,QHeaderView
from lumen_i18n import tr
from tools_ui import button,row
from notes_properties import values,change


class PropertiesDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setWindowTitle(tr('Lumen Notes · Eigenschaften'));self.resize(640,350)
        self.original=window.document_text();self.path=window.doc['path'];self.root=str(window.book.root);self.prefix=window.heading_prefix;self.initial=values(self.prefix)
        layout=QVBoxLayout(self);self.grid=QTableWidget(0,3);self.grid.setHorizontalHeaderLabels([tr('Eigenschaft'),tr('Typ'),tr('Wert')]);self.grid.setAccessibleName(tr('Notizeigenschaften'))
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(self.grid,1)
        for name,item in self.initial.items():self.add(name,item['kind'],item['value'])
        layout.addWidget(row(button(tr('Eigenschaft hinzufügen'),lambda:self.add()),button(tr('Eigenschaft entfernen'),self.remove)))
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        hint=QLabel(tr('Zum Beispiel status oder due. Tags stehen unter dem Titel; komplexe Fremdfelder bleiben unverändert.'));hint.setWordWrap(True);layout.addWidget(hint)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def add(self,name='',kind='text',value=''):
        row=self.grid.rowCount();self.grid.insertRow(row);self.grid.setItem(row,0,QTableWidgetItem(name));self.grid.setItem(row,2,QTableWidgetItem(value))
        choices=QComboBox();choices.addItem(tr('Text'),'text');choices.addItem(tr('Datum'),'date');choices.setCurrentIndex(choices.findData(kind));choices.setAccessibleName(tr('Eigenschaftstyp'));self.grid.setCellWidget(row,1,choices);self.grid.setCurrentCell(row,0)
    def remove(self):
        if self.grid.currentRow()>=0:self.grid.removeRow(self.grid.currentRow())
    def accept(self):
        w=self.window
        if not w.doc or w.doc['path']!=self.path or str(w.book.root)!=self.root or w.document_text()!=self.original or not w.editor.isEnabled() or w.editor.isReadOnly():
            self.message.setText(tr('Die Notiz wurde inzwischen geändert. Eigenschaften erneut öffnen.'));return
        try:
            current={}
            for row in range(self.grid.rowCount()):
                name=self.grid.item(row,0).text().strip();value=self.grid.item(row,2).text();kind=self.grid.cellWidget(row,1).currentData()
                if not name and not value:continue
                if name in current:raise ValueError(tr('Eine Eigenschaft ist mehrfach vorhanden.'))
                current[name]=dict(kind=kind,value=value)
            text=self.prefix
            for name in self.initial.keys()-current.keys():text=change(text,name,remove=True)
            for name,item in current.items():
                if self.initial.get(name)!=item:text=change(text,name,**item)
        except ValueError as error:self.message.setText(str(error));return
        if text!=w.heading_prefix:w.heading_prefix=text;w.edited();w.note_tags.refresh();w.live_preview.schedule()
        super().accept()


def show(window):
    if window.area=='user' and window.doc and window.editor.isEnabled() and not window.editor.isReadOnly():PropertiesDialog(window).exec()
