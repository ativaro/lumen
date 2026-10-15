"""Virtual notebook table; edits reuse the guarded property/draft workflow."""
from pathlib import Path
from PySide6.QtCore import Qt,QAbstractTableModel,QModelIndex
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import QDialog,QVBoxLayout,QTableView,QHeaderView
from lumen_i18n import tr
from tools_ui import button,row,label
from notes_properties import for_note
from notes_properties_ui import PropertiesDialog
import notes_views
import wissen_data as data


class Model(QAbstractTableModel):
    def __init__(self,parent=None):
        super().__init__(parent);self.notes=[];self.fields=[]
    def replace(self,notes):
        self.beginResetModel();self.notes=notes
        self.fields=sorted({name for note in notes for name in for_note(note)})
        self.endResetModel()
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.notes)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else 3+len(self.fields)
    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if role==Qt.DisplayRole and orientation==Qt.Horizontal:return [tr('Notiz'),tr('Sammlung'),tr('Tags'),*self.fields][section]
        return None
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.notes):return None
        note=self.notes[index.row()];column=index.column()
        if role==Qt.UserRole:return note['path']
        if role==Qt.ToolTipRole:return note['path']
        if role not in (Qt.DisplayRole,Qt.AccessibleTextRole):return None
        if column==0:return note['title']
        if column==1:return tr('Meine Notizen') if str(Path(note['path']).parent)=='.' else str(Path(note['path']).parent)
        if column==2:return '  '.join('#'+tag for tag in note['tags'])
        return for_note(note).get(self.fields[column-3],{}).get('value','')


class Table(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.root=str(window.book.root);self.identity=window.book.identity;self.stamp=None;self.stopped=False
        self.setWindowTitle(tr('Lumen Notes · Notiztabelle'));self.resize(1000,600)
        layout=QVBoxLayout(self);self.info=label('');layout.addWidget(self.info)
        self.model=Model(self);self.grid=QTableView();self.grid.setModel(self.model);self.grid.setAccessibleName(tr('Notizen und Eigenschaften'))
        self.grid.setSelectionBehavior(QTableView.SelectRows);self.grid.setSelectionMode(QTableView.SingleSelection)
        self.grid.setAlternatingRowColors(True);self.grid.setWordWrap(False)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive);self.grid.horizontalHeader().setDefaultSectionSize(160)
        self.grid.verticalHeader().setDefaultSectionSize(32);self.grid.setColumnWidth(0,260)
        self.grid.activated.connect(lambda index:self.edit() if index.column()>=3 else self.open_note())
        for key in (Qt.Key_Return,Qt.Key_Enter):
            shortcut=QShortcut(QKeySequence(key),self.grid);shortcut.setContext(Qt.WidgetShortcut)
            shortcut.activated.connect(lambda:self.grid.activated.emit(self.grid.currentIndex()))
        layout.addWidget(self.grid,1)
        layout.addWidget(row(button(tr('Notiz öffnen'),self.open_note),button(tr('Eigenschaften bearbeiten …'),self.edit),button(tr('Aktuelle Ansicht speichern …'),lambda:window.safe(notes_views.save,window,True)),button(tr('Schließen'),self.close)))
        self.message=label(tr('Eigenschaft doppelklicken zum Bearbeiten. Filter und Sortierung entsprechen der Notizliste.'));layout.addWidget(self.message)
        self.reload()
    def selected(self):
        index=self.grid.currentIndex()
        return self.model.notes[index.row()] if index.isValid() and index.row()<len(self.model.notes) else None
    def reload(self):
        if self.stopped:return
        w=self.window
        if w.area!='user' or not w.book or str(w.book.root)!=self.root or w.book.identity!=self.identity:self.close();return
        stamp=(w.collection,w.search.text(),getattr(w,'view_sort',''),tuple((p,n['hash'],n.get('modified',0)) for p,n in w.notes.items()))
        if stamp==self.stamp:return
        selected=self.selected();path=selected['path'] if selected else None
        notes=[n for n in w.notes.values() if w.in_collection(n)]
        notes.sort(key=lambda n:n.get('modified',0),reverse=True)
        if w.search.text().strip():notes=data.search(notes,w.search.text(),data.MAX_SCAN_NOTES)
        notes=notes_views.ordered(notes,getattr(w,'view_sort',''));self.model.replace(notes);self.stamp=stamp
        self.info.setText(tr('{0} Notizen · {1}',len(notes),w.search.text().strip() or tr('Alle Notizen')))
        if notes:self.grid.selectRow(next((i for i,n in enumerate(notes) if n['path']==path),0))
    def open_note(self):
        note=self.selected()
        if note:self.close();self.window.safe(self.window.open_note,note['path'])
    def edit(self):
        w=self.window;note=self.selected()
        if not note or w.job or w.closing:return
        path=note['path'];column=self.grid.currentIndex().column()
        field=self.model.fields[column-3] if column>=3 else ''
        self.edit_note(path,field)
    def edit_note(self,path,field):
        if self.stopped:return
        w=self.window
        if not self.isVisible() or not w.book or str(w.book.root)!=self.root or w.book.identity!=self.identity or w.area!='user':return
        if w.dirty:w.save_note(lambda:self.edit_note(path,field));return
        kinds={for_note(n).get(field,{}).get('kind') for n in self.model.notes};kind='date' if kinds-{None}=={'date'} else 'text'
        def properties():
            if self.stopped:return
            if not self.isVisible() or not w.doc or w.doc['path']!=path or not w.book or str(w.book.root)!=self.root or w.book.identity!=self.identity:return
            try:
                dialog=PropertiesDialog(w)
                if field:
                    found=next((i for i in range(dialog.grid.rowCount()) if dialog.grid.item(i,0).text()==field),None)
                    if found is None:dialog.add(field,kind)
                    else:dialog.grid.setCurrentCell(found,2)
                if dialog.exec()==QDialog.Accepted:w.save_note(self.reload)
            except ValueError as error:self.message.setText(str(error))
        def opened(value):
            w.show_note(value,preserve_filter=True);w.after_job=properties
        w.action('read',opened,path=path)


def show(window):
    if window.closing or window.area!='user' or not window.book:return
    if window.dirty:window.save_note(lambda:show(window));return
    if window.job:window.after_job=lambda:show(window);return
    existing=getattr(window,'notes_table',None)
    if existing and existing.isVisible():existing.reload();existing.raise_();return
    table=Table(window);window.notes_table=table
    def closed():
        table.stopped=True
        if getattr(window,'notes_table',None) is table:window.notes_table=None
        table.deleteLater()
    table.finished.connect(closed);table.show()
