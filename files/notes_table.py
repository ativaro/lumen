"""Edit a bounded Markdown table without rewriting the rest of the document."""
import re
from PySide6.QtWidgets import QDialog,QVBoxLayout,QTableWidget,QTableWidgetItem,QDialogButtonBox,QMessageBox
from PySide6.QtGui import QTextCursor
from lumen_i18n import tr
from tools_ui import row,button,label
from note_tags import body_mask
from notes_editor import qt_length


def cells(line):
    line=line.strip();result=[];cell='';slashes=0
    for char in line:
        if char=='|' and slashes%2==0:result.append(cell.strip());cell=''
        elif char=='|' and slashes%2:cell=cell[:-slashes]+'\\'*(slashes//2)+'|'
        else:cell+=char
        slashes=slashes+1 if char=='\\' else 0
    result.append(cell.strip())
    if line.startswith('|'):result.pop(0)
    if line.endswith('|') and not re.search(r'(?<!\\)(?:\\\\)*\\\|$',line):result.pop()
    return result


def table_at(text, line_number):
    lines=text.splitlines(keepends=True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    masked=body_mask(text)
    def tabular(index):return 0<=index<len(lines) and '|' in masked[offsets[index]:offsets[index+1]]
    if not tabular(line_number):return None
    start=end=line_number
    while tabular(start-1):start-=1
    while tabular(end+1):end+=1
    if end<=start:return None
    headings=cells(lines[start]);alignment=cells(lines[start+1])
    if len(headings)!=len(alignment) or not all(re.fullmatch(r':?-{3,}:?',value) for value in alignment):return None
    values=[headings]+[cells(line) for line in lines[start+2:end+1]]
    if len(values)>200 or len(headings)>30:raise ValueError(tr('Tabelleneditor: maximal 200 Zeilen und 30 Spalten.'))
    if any(len(value)>len(headings) for value in values):raise ValueError(tr('Die Tabelle hat unterschiedlich viele Spalten. Bitte zuerst im Text korrigieren.'))
    values=[value+['']*(len(headings)-len(value)) for value in values]
    return offsets[start],offsets[end+1],values,alignment


def markdown(values,alignment):
    def escaped(value):
        return re.sub(r'(\\*)\|',lambda match:'\\'*(len(match[1])*2+1)+'|',value.replace('\r','').replace('\n','<br>'))
    def line(values):return '| '+' | '.join(escaped(value) for value in values)+' |'
    return '\n'.join([line(values[0]),line(alignment)]+[line(value) for value in values[1:]])


class TableEditor(QDialog):
    def __init__(self,editor):
        super().__init__(editor.window());self.setWindowTitle(tr('Lumen Notes · Tabelle'));self.resize(700,460)
        self.editor=editor;self.original=editor.toPlainText();self.revision=editor.document().revision()
        selected=table_at(self.original,editor.textCursor().blockNumber())
        if selected:self.start,self.end,values,self.alignment=selected
        else:
            cursor=editor.textCursor()
            self.start=len(self.original.encode('utf-16-le')[:cursor.selectionStart()*2].decode('utf-16-le'))
            self.end=len(self.original.encode('utf-16-le')[:cursor.selectionEnd()*2].decode('utf-16-le'))
            values=[[tr('Spalte 1'),tr('Spalte 2')],['','']];self.alignment=['---','---']
        self.existing=bool(selected)
        layout=QVBoxLayout(self);layout.addWidget(label(tr('Die erste Zeile enthält die Spaltenüberschriften.')))
        self.grid=QTableWidget(len(values),len(values[0]));self.grid.setAccessibleName(tr('Tabellenzellen'))
        for r,values_row in enumerate(values):
            for c,value in enumerate(values_row):self.grid.setItem(r,c,QTableWidgetItem(value))
        layout.addWidget(self.grid,1)
        layout.addWidget(row(button(tr('Zeile hinzufügen'),self.add_row),button(tr('Zeile entfernen'),self.remove_row),button(tr('Spalte hinzufügen'),self.add_column),button(tr('Spalte entfernen'),self.remove_column)))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.grid.setCurrentCell(0,0)

    def add_row(self):
        if self.grid.rowCount()<200:self.grid.insertRow(max(1,self.grid.currentRow()+1))
    def remove_row(self):
        if self.grid.currentRow()>0:self.grid.removeRow(self.grid.currentRow())
    def add_column(self):
        if self.grid.columnCount()<30:
            index=max(0,self.grid.currentColumn()+1);self.grid.insertColumn(index);self.alignment.insert(index,'---')
    def remove_column(self):
        if self.grid.columnCount()>1 and self.grid.currentColumn()>=0:
            index=self.grid.currentColumn();self.grid.removeColumn(index);self.alignment.pop(index)
    def accept(self):
        editor=self.editor
        if editor.toPlainText()!=self.original or editor.document().revision()!=self.revision or editor.isReadOnly() or not editor.isEnabled():
            QMessageBox.warning(self,tr('Lumen Notes · Tabelle'),tr('Die Notiz wurde inzwischen geändert. Tabelle erneut öffnen.'));return
        values=[[self.grid.item(r,c).text() if self.grid.item(r,c) else '' for c in range(self.grid.columnCount())] for r in range(self.grid.rowCount())]
        text=markdown(values,self.alignment)
        if self.existing:
            if self.original[self.start:self.end].endswith('\n'):text+='\n'
        else:
            if self.start and self.original[self.start-1]!='\n':text='\n'+text
            text+='\n'
        cursor=editor.textCursor();cursor.setPosition(qt_length(self.original[:self.start]));cursor.setPosition(qt_length(self.original[:self.end]),QTextCursor.KeepAnchor)
        if text!=self.original[self.start:self.end]:
            cursor.beginEditBlock();cursor.insertText(text);cursor.endEditBlock();editor.setTextCursor(cursor)
        super().accept();editor.setFocus()


def edit_table(editor):
    if not editor.isEnabled() or editor.isReadOnly():return
    try:dialog=TableEditor(editor)
    except ValueError as error:QMessageBox.warning(editor,tr('Lumen Notes · Tabelle'),str(error));return
    dialog.exec()
