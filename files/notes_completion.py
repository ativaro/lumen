"""Suggestions from the currently open notebook only."""
import os
import re
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QCompleter


class NoteCompletion:
    def __init__(self, editor):
        self.editor = editor
        self.notes = lambda: []
        self.origin = lambda: ''
        self.items = {}
        self.context = None
        self.popup = QCompleter(editor)
        self.model = QStringListModel(self.popup)
        self.popup.setModel(self.model)
        self.popup.setWidget(editor)
        self.popup.setCaseSensitivity(Qt.CaseInsensitive)
        self.popup.setFilterMode(Qt.MatchContains)
        self.popup.activated[str].connect(self.choose)
        editor.textChanged.connect(self.invalidate)

    def invalidate(self):
        self.context = None
        self.popup.popup().hide()

    def token(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection(): return None
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        before = cursor.selectedText()
        link = re.search(r'\[\[([^\]\n]*)$', before)
        tag = re.search(r'(?:^|\s)#([\w/-]*)$', before)
        match = link or tag
        if not match: return None
        kind = 'link' if link else 'tag'
        typed = ('[[' if link else '#') + match[1]
        return kind, match[1], self.editor.textCursor().position()-len(typed.encode('utf-16-le'))//2

    def refresh(self):
        editor = self.editor
        self.context = self.token()
        if not self.context or not editor.isEnabled() or editor.isReadOnly():
            self.popup.popup().hide(); return
        kind, query, _ = self.context
        notes = list(self.notes())
        if kind == 'link':
            from notes_structure import split_target, targets
            from wissen_data import resolve_link
            if '#' in query:
                path, anchor = split_target(query)
                current = {note['path']:note for note in notes}
                target = resolve_link(self.origin(),path,current)
                self.items = {value['title']: '[['+path+'#'+quote(value['anchor'],safe='^')+']]'
                              for value in targets(current[target]['text']) if anchor.casefold() in value['anchor'].casefold()} if target else {}
            else:
                self.items = {note['title']+' · '+note['path']: '[['+quote(os.path.relpath(note['path'], str(Path(self.origin()).parent)), safe='/')+']]'
                              for note in notes if query.casefold() in (note['title']+' '+note['path']).casefold()}
        else:
            self.items = {'#'+tag: '#'+tag for note in notes for tag in note['tags'] if query.casefold() in tag.casefold()}
        labels = sorted(self.items, key=str.casefold)[:100]
        self.model.setStringList(labels)
        self.popup.setCompletionPrefix('')
        if labels:
            self.popup.complete(editor.cursorRect())
        else: self.popup.popup().hide()

    def choose(self, label):
        if not self.context or label not in self.items or self.token() != self.context: return
        if not self.editor.isEnabled() or self.editor.isReadOnly(): return
        kind, _, start = self.context
        cursor = self.editor.textCursor()
        if kind == 'link':
            following = QTextCursor(cursor)
            following.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor, 2)
            if following.selectedText() == ']]': cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.MoveAnchor, 2)
        cursor.setPosition(start, QTextCursor.KeepAnchor)
        cursor.insertText(self.items[label])
        self.editor.setTextCursor(cursor)
        self.popup.popup().hide()
