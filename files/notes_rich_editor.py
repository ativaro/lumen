"""Rendered authoring over the existing draft, history and conflict-safe source editor."""
from PySide6.QtCore import Qt, QUrl, QEvent
from PySide6.QtGui import (QFont, QTextCursor, QTextCharFormat, QTextBlockFormat,
    QTextListFormat, QTextDocument, QTextImageFormat, QImage, QPainter, QKeySequence, QTextFormat,
    QTextTable, QTextLength, QTextFrameFormat, QColor, QBrush)
from PySide6.QtWidgets import QTextEdit, QDialog, QVBoxLayout, QDialogButtonBox, QLabel, QMenu
from lumen_i18n import tr
from notes_editor import qt_length
from notes_rich_codec import Codec, SafeDocument


class RichEditor(QTextEdit):
    def __init__(self, window):
        super().__init__(); self.window = window; self.source = window.editor
        self.syncing = False; self.codec = Codec(''); self.setDocument(SafeDocument(self))
        self.setObjectName('wissenRichEditor'); self.setAccessibleName(tr('Notiztext direkt bearbeiten'))
        self.setAcceptRichText(False)
        self.setPlaceholderText(tr('Hier schreiben. Text markieren und oben formatieren.'))
        self.textChanged.connect(self.changed)
        self.source.textChanged.connect(self.load_source)
        self.cursorPositionChanged.connect(self.cursor_changed)
        self.source.installEventFilter(self)
        self.table_menu = QMenu(self)
        for key, title in [('insert', 'Tabelle einfügen'), ('add_row', 'Zeile hinzufügen'),
                           ('remove_row', 'Zeile entfernen'), ('add_column', 'Spalte hinzufügen'),
                           ('remove_column', 'Spalte entfernen'), ('remove_table', 'Tabelle entfernen')]:
            action = self.table_menu.addAction(tr(title), lambda checked=False, key=key: self.change_table(key))
            action.setData(key)
        self.table_menu.aboutToShow.connect(self.update_table_menu)
        self.load_source()

    def eventFilter(self, obj, event):
        if obj is self.source and event.type()==QEvent.EnabledChange:
            self.setEnabled(self.source.isEnabled())
            if hasattr(self.window,'save_note_button'): self.window.save_note_button.setEnabled(self.source.isEnabled())
        return super().eventFilter(obj,event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type()==QEvent.PaletteChange and hasattr(self,'codec'):
            for key,raw in self.codec.opaque.items(): self.card(key,raw)
            self.viewport().update()

    def load_source(self):
        if self.syncing: return
        self.syncing = True
        try:
            self.codec = Codec(self.source.toPlainText())
            self.setMarkdown(self.codec.rendered)
            if self.window.book and self.window.doc:
                from pathlib import Path
                self.document().setBaseUrl(QUrl.fromLocalFile(str(self.window.book.root/Path(self.window.doc['path']).parent)+'/'))
            self.document().setDefaultFont(self.font())
            block=self.document().begin()
            while block.isValid():
                cursor=QTextCursor(block);fmt=block.blockFormat()
                fmt.setTopMargin(18 if fmt.headingLevel() else 0)
                fmt.setBottomMargin(4 if block.textList() else 12)
                fmt.setLineHeight(170,QTextBlockFormat.ProportionalHeight.value)
                cursor.setBlockFormat(fmt);block=block.next()
            for frame in self.document().rootFrame().childFrames():
                if isinstance(frame,QTextTable):self.style_table(frame)
            for key, raw in self.codec.opaque.items(): self.card(key, raw)
            self.document().clearUndoRedoStacks()
        finally: self.syncing = False

    def card(self, key, raw):
        import re
        from notes_render import prepare
        if self.window.doc:
            raw=prepare(raw,self.window.doc['path'],self.window.notes)
        raw=re.sub(r'\s+\^[\w-]+(?=\s|$)','',raw)
        raw=re.sub(r'(?m)^(\s*>\s*)\[![^\]]+\]',r'\1',raw)
        doc = SafeDocument(); doc.setDefaultFont(self.font())
        doc.setMarkdown('**'+tr('Geschützter Abschnitt · Doppelklick zum Bearbeiten')+'**\n\n'+raw[:240])
        doc.setTextWidth(480)
        image = QImage(500, int(doc.size().height())+20, QImage.Format_ARGB32_Premultiplied)
        image.fill(self.palette().alternateBase().color())
        painter = QPainter(image); painter.setPen(self.palette().text().color()); painter.translate(10,10)
        from PySide6.QtGui import QAbstractTextDocumentLayout
        context = QAbstractTextDocumentLayout.PaintContext(); context.palette = self.palette()
        doc.documentLayout().draw(painter,context); painter.end()
        self.document().addResource(QTextDocument.ImageResource,QUrl(key),image)

    def changed(self):
        if self.syncing: return
        value = self.codec.encode(self.document())
        before = self.source.toPlainText()
        if value == before: return
        self.syncing = True
        try:
            start = 0
            while start < min(len(before),len(value)) and before[start] == value[start]: start += 1
            end = 0
            while end < min(len(before)-start,len(value)-start) and before[-end-1] == value[-end-1]: end += 1
            cursor = self.source.textCursor(); cursor.beginEditBlock()
            cursor.setPosition(qt_length(before[:start]))
            cursor.setPosition(qt_length(before[:len(before)-end]),QTextCursor.KeepAnchor)
            cursor.insertText(value[start:len(value)-end]); cursor.endEditBlock()
        finally: self.syncing = False

    def cursor_changed(self):
        w = self.window
        self.update_table_menu()
        if hasattr(w,'table_tools'):
            w.table_tools.setVisible(bool(self.textCursor().currentTable()) and not w.source_mode.isChecked() and w.views.currentIndex()==0)
        if not hasattr(w,'paragraph'): return
        fmt = self.textCursor().blockFormat(); level = fmt.headingLevel()
        prefix = '#'*level+' ' if level else '> ' if fmt.intProperty(QTextFormat.BlockQuoteLevel) else ''
        w.paragraph.setCurrentIndex(max(0,w.paragraph.findData(prefix)))
        for key, active in [('bold',self.fontWeight()>=QFont.Bold),('italic',self.fontItalic()),('underline',self.fontUnderline())]:
            if key in w.format_actions:
                w.format_actions[key].setChecked(active)

    def wrap(self, marker):
        if not self.isEnabled() or self.isReadOnly(): return
        fmt = QTextCharFormat()
        if marker == '**': fmt.setFontWeight(QFont.Normal if self.fontWeight()>=QFont.Bold else QFont.Bold)
        elif marker == '*': fmt.setFontItalic(not self.fontItalic())
        elif marker == 'u': fmt.setFontUnderline(not self.fontUnderline())
        elif marker == '`':
            fmt.setFontFixedPitch(not self.currentCharFormat().fontFixedPitch())
            fmt.setFontFamilies(['monospace'] if fmt.fontFixedPitch() else self.font().families())
        self.mergeCurrentCharFormat(fmt); self.setFocus(); self.cursor_changed()

    def paragraph_style(self, prefix):
        if not self.isEnabled() or self.isReadOnly(): return
        cursor = self.textCursor(); cursor.beginEditBlock()
        if prefix in ('- ','1. '):
            fmt = QTextListFormat(); fmt.setStyle(QTextListFormat.ListDisc if prefix=='- ' else QTextListFormat.ListDecimal)
            cursor.createList(fmt)
        else:
            first,last = cursor.selectionStart(),cursor.selectionEnd()
            block = self.document().findBlock(first)
            while block.isValid() and block.position() <= last:
                if block.position()==last and last>first: break
                bc = QTextCursor(block)
                if bc.currentList(): bc.currentList().remove(block)
                fmt = bc.blockFormat(); fmt.setHeadingLevel(prefix.count('#'))
                fmt.setProperty(QTextFormat.BlockQuoteLevel,1 if prefix=='> ' else 0)
                fmt.setIndent(0); bc.setBlockFormat(fmt)
                style = QTextCharFormat(); style.setFontWeight(QFont.Bold if prefix.startswith('#') else QFont.Normal)
                style.setFontPointSize(max(12,30-prefix.count('#')*3) if prefix.startswith('#') else max(10.5,self.font().pointSizeF()))
                bc.select(QTextCursor.BlockUnderCursor); bc.mergeCharFormat(style)
                block = block.next()
        cursor.endEditBlock(); self.setTextCursor(cursor); self.setFocus(); self.cursor_changed()

    def toggle_checkbox(self):
        cursor = self.textCursor(); cursor.beginEditBlock()
        if not cursor.currentList():
            fmt = QTextListFormat(); fmt.setStyle(QTextListFormat.ListDisc); cursor.createList(fmt)
        fmt = cursor.blockFormat()
        fmt.setMarker(QTextBlockFormat.MarkerType.Unchecked if fmt.marker()!=QTextBlockFormat.MarkerType.Unchecked else QTextBlockFormat.MarkerType.Checked)
        cursor.setBlockFormat(fmt); cursor.endEditBlock(); self.setFocus()

    def insert_table(self):
        if not self.isEnabled() or self.isReadOnly(): return
        cursor = self.textCursor()
        if cursor.currentTable():
            cursor.currentTable().appendRows(1)
        else:
            cursor.beginEditBlock(); table = cursor.insertTable(3,2)
            fmt = table.format(); fmt.setHeaderRowCount(1); fmt.setCellPadding(8); table.setFormat(fmt)
            self.style_table(table)
            table.cellAt(0,0).firstCursorPosition().insertText(tr('Spalte 1'))
            table.cellAt(0,1).firstCursorPosition().insertText(tr('Spalte 2'))
            cursor.endEditBlock()
        self.setFocus()

    def style_table(self, table):
        fmt=table.format();fmt.setCellPadding(8);fmt.setCellSpacing(0)
        # A translucent neutral rule blends with every theme without editing undo history.
        border=QBrush(QColor(128,128,128,100))
        fmt.setBorder(1);fmt.setBorderBrush(border);fmt.setBorderStyle(QTextFrameFormat.BorderStyle_Solid);fmt.setBorderCollapse(True)
        fmt.setWidth(QTextLength(QTextLength.PercentageLength,100));table.setFormat(fmt)
        for row in range(table.rows()):
            for column in range(table.columns()):
                cell=table.cellAt(row,column);cell_format=cell.format().toTableCellFormat()
                cell_format.setBorder(1);cell_format.setBorderBrush(border);cell_format.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
                cell.setFormat(cell_format)

    def update_table_menu(self):
        table = self.textCursor().currentTable()
        cell = table.cellAt(self.textCursor()) if table else None
        editable = self.isEnabled() and not self.isReadOnly()
        allowed = {'insert': table is None,
                   'add_row': table is not None and table.rows() < 200,
                   'remove_row': table is not None and cell.row() > 0 and table.rows() > 2,
                   'add_column': table is not None and table.columns() < 30,
                   'remove_column': table is not None and table.columns() > 1,
                   'remove_table': table is not None}
        for action in self.table_menu.actions(): action.setEnabled(editable and allowed[action.data()])

    def change_table(self, operation):
        self.update_table_menu()
        if not any(a.data() == operation and a.isEnabled() for a in self.table_menu.actions()): return
        if operation == 'insert': self.insert_table(); return
        cursor = self.textCursor(); table = cursor.currentTable(); cell = table.cellAt(cursor)
        cursor.beginEditBlock()
        if operation == 'add_row': table.insertRows(cell.row()+1, 1)
        elif operation == 'remove_row': table.removeRows(cell.row(), 1)
        elif operation == 'add_column': table.insertColumns(cell.column()+1, 1)
        elif operation == 'remove_column': table.removeColumns(cell.column(), 1)
        elif operation == 'remove_table': table.removeRows(0, table.rows())
        cursor.endEditBlock(); self.setFocus(); self.cursor_changed()

    def insert_image(self, path):
        self.textCursor().insertImage(path)
        self.window.live_preview.image_key=None;self.window.live_preview.schedule()

    def set_images(self, images):
        import base64
        from pathlib import Path
        if not self.window.book:return
        for path, raw in images.items():
            image=QImage.fromData(base64.b64decode(raw))
            if not image.isNull():
                image=image.scaled(600,600,Qt.KeepAspectRatio,Qt.SmoothTransformation)
                self.document().addResource(QTextDocument.ImageResource,QUrl.fromLocalFile(str(self.window.book.root/Path(path))),image)
        self.document().markContentsDirty(0,self.document().characterCount());self.viewport().update()

    def focus_source(self, line):
        doc=SafeDocument();doc.setMarkdown(line)
        cursor=self.document().find(doc.toPlainText().strip())
        if not cursor.isNull():self.setTextCursor(cursor);self.ensureCursorVisible()
        self.setFocus()

    def insert_link(self, target, label):
        cursor = self.textCursor(); fmt = QTextCharFormat(); fmt.setAnchor(True)
        fmt.setAnchorHref(target); fmt.setForeground(self.palette().link())
        cursor.insertText(label,fmt); cursor.setCharFormat(QTextCharFormat()); self.setTextCursor(cursor); self.setFocus()

    def keyPressEvent(self,event):
        if event.matches(QKeySequence.Bold): self.wrap('**'); return
        if event.matches(QKeySequence.Italic): self.wrap('*'); return
        if event.matches(QKeySequence.Underline): self.wrap('u'); return
        if event.modifiers()==Qt.ControlModifier and event.key() in (Qt.Key_Return,Qt.Key_Enter):
            href=self.textCursor().charFormat().anchorHref()
            if href: self.follow(href); return
        cursor=self.textCursor()
        if event.text() and not cursor.hasSelection() and cursor.charFormat().isAnchor():
            after=QTextCursor(cursor);after.movePosition(QTextCursor.NextCharacter)
            if cursor.atBlockEnd() or after.charFormat().anchorHref()!=cursor.charFormat().anchorHref():
                self.setCurrentCharFormat(QTextCharFormat())
        super().keyPressEvent(event)

    def follow(self, href):
        if href in self.codec.wiki: href=self.codec.wiki[href][1]
        if not QUrl(href).scheme(): self.window.safe(self.window.follow_editor_link,href)

    def mouseDoubleClickEvent(self,event):
        cursor=self.cursorForPosition(event.position().toPoint()); fmt=cursor.charFormat()
        key=fmt.toImageFormat().name() if fmt.isImageFormat() else ''
        if key in self.codec.opaque:
            self.edit_protected(key); return
        super().mouseDoubleClickEvent(event)

    def edit_protected(self,key):
        from notes_editor import NotesEditor
        dialog=QDialog(self);dialog.setWindowTitle(tr('Lumen Notes · Geschützter Abschnitt'));dialog.resize(650,440)
        layout=QVBoxLayout(dialog);layout.addWidget(QLabel(tr('Dieser importierte Abschnitt bleibt im Originalformat erhalten.')))
        editor=NotesEditor();editor.setPlainText(self.codec.opaque[key]);layout.addWidget(editor)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        original=self.source.toPlainText()
        if dialog.exec()==QDialog.Accepted and self.source.toPlainText()==original:
            import uuid
            new='lumen-preserved:'+uuid.uuid4().hex
            self.codec.opaque[new]=editor.toPlainText();self.card(new,editor.toPlainText())
            block=self.document().begin()
            while block.isValid():
                iterator=block.begin()
                while not iterator.atEnd():
                    fragment=iterator.fragment()
                    if fragment.charFormat().isImageFormat() and fragment.charFormat().toImageFormat().name()==key:
                        cursor=QTextCursor(self.document());cursor.setPosition(fragment.position())
                        cursor.setPosition(fragment.position()+fragment.length(),QTextCursor.KeepAnchor)
                        cursor.insertImage(new);return
                    iterator+=1
                block=block.next()
