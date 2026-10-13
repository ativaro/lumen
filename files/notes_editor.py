"""Markdown editing without converting the user's source or replacing undo history."""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


def qt_length(text):
    return len(text.encode('utf-16-le')) // 2


class MarkdownHighlight(QSyntaxHighlighter):
    source_mode = False

    def highlightBlock(self, text):
        fence = re.match(r'^ {0,3}(`{3,}|~{3,})', text)
        previous = self.previousBlockState()
        if previous > 0:
            character = '`' if previous % 2 == 0 else '~'
            width = previous // 2
            closes = re.fullmatch(r' {0,3}'+re.escape(character)+'{'+str(width)+r',}\s*', text)
            self.setCurrentBlockState(0 if closes else previous)
            if self.source_mode: return
            code = QTextCharFormat(); code.setFontFamilies(['monospace'])
            self.setFormat(0, qt_length(text), code)
            return
        self.setCurrentBlockState(len(fence[1])*2+(fence[1][0]=='~') if fence else 0)
        if fence or self.source_mode:
            return
        heading = re.match(r'^(#{1,6})\s', text)
        if heading:
            style = QTextCharFormat(); style.setFontWeight(QFont.Bold)
            style.setFontPointSize(19-len(heading[1]))
            self.setFormat(0, qt_length(text), style)
        for pattern, kind in [(r'\*\*[^*\n]+\*\*', 'bold'),
                              (r'(?<!\*)\*[^*\n]+\*(?!\*)', 'italic'),
                              (r'\[\[[^\]\n]+\]\]', 'link'),
                              (r'`[^`\n]+`', 'code')]:
            for match in re.finditer(pattern, text):
                style = QTextCharFormat()
                if kind == 'bold': style.setFontWeight(QFont.Bold)
                elif kind == 'italic': style.setFontItalic(True)
                elif kind == 'link': style.setFontUnderline(True)
                else: style.setFontFamilies(['monospace'])
                self.setFormat(qt_length(text[:match.start()]), qt_length(match[0]), style)


class NotesEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlight = MarkdownHighlight(self.document())

    def set_source_mode(self, enabled):
        self.highlight.source_mode = enabled
        self.highlight.rehighlight()

    def wrap(self, marker):
        if not self.isEnabled() or self.isReadOnly(): return
        cursor = self.textCursor()
        start = cursor.selectionStart()
        text = cursor.selectedText().replace('\u2029', '\n')
        cursor.beginEditBlock()
        cursor.insertText(marker+text+marker)
        cursor.endEditBlock()
        cursor.setPosition(start+qt_length(marker))
        if text: cursor.setPosition(start+qt_length(marker+text), QTextCursor.KeepAnchor)
        self.setTextCursor(cursor); self.setFocus()

    def prefix_lines(self, prefix):
        if not self.isEnabled() or self.isReadOnly(): return
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start); cursor.movePosition(QTextCursor.StartOfBlock)
        first = cursor.position()
        cursor.setPosition(end)
        if end > start and cursor.atBlockStart(): cursor.movePosition(QTextCursor.PreviousCharacter)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.setPosition(first, QTextCursor.KeepAnchor)
        text = cursor.selectedText().split('\u2029')
        cursor.beginEditBlock()
        cursor.insertText('\n'.join(prefix+line for line in text))
        cursor.endEditBlock()
        self.setTextCursor(cursor); self.setFocus()

    def toggle_checkbox(self):
        if not self.isEnabled() or self.isReadOnly(): return
        cursor = self.textCursor()
        match = re.match(r'^(\s*[-+*] \[)([ xX])(\] )', cursor.block().text())
        if not match:
            self.prefix_lines('- [ ] '); return
        position = cursor.position()
        cursor.setPosition(cursor.block().position()+qt_length(match[1]))
        cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
        cursor.insertText('x' if match[2]==' ' else ' ')
        cursor.setPosition(position); self.setTextCursor(cursor); self.setFocus()

    def insert_table(self):
        if not self.isEnabled() or self.isReadOnly(): return
        from lumen_i18n import tr
        cursor = self.textCursor(); cursor.beginEditBlock()
        cursor.insertText('\n| '+tr('Spalte 1')+' | '+tr('Spalte 2')+' |\n| --- | --- |\n|  |  |\n')
        cursor.endEditBlock(); self.setTextCursor(cursor); self.setFocus()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Bold): self.wrap('**'); return
        if event.matches(QKeySequence.Italic): self.wrap('*'); return
        cursor = self.textCursor()
        if (event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers()
                and self.isEnabled() and not self.isReadOnly()
                and not cursor.hasSelection() and cursor.atBlockEnd()):
            self.highlight.rehighlightBlock(cursor.block())
            if cursor.block().userState() <= 0:
                match = re.match(r'^(\s*)([-+*]|\d+[.)]) (\[[ xX]\] )?(.*)$', cursor.block().text())
                if match:
                    cursor.beginEditBlock()
                    if not match[4].strip():
                        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                        cursor.removeSelectedText()
                    else:
                        marker = match[2]
                        if marker[:-1].isdigit(): marker = str(int(marker[:-1])+1)+marker[-1]
                        cursor.insertText('\n'+match[1]+marker+' '+('[ ] ' if match[3] else ''))
                    cursor.endEditBlock(); self.setTextCursor(cursor); return
        super().keyPressEvent(event)
