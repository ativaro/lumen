"""Visible tags on the current draft; persistence uses the notebook's normal save."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QMenu, QWidgetAction, QLineEdit, QListWidget, QListWidgetItem
from lumen_i18n import tr
from tools_ui import button, label
from note_tags import tags, identity, add_tag, rename_tag
from notes_editor import qt_length


class NoteTagsBar(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.values = None
        self.path = None
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.chips = QWidget(); self.chip_layout = QHBoxLayout(self.chips)
        self.chip_layout.setContentsMargins(0, 0, 0, 0); self.chip_layout.setSpacing(6)
        scroll = QScrollArea(); scroll.setObjectName('noteTagsScroll'); self.chips.setObjectName('noteTagsChips'); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setMaximumHeight(54)
        scroll.setWidget(self.chips);self.scroll=scroll;layout.addWidget(scroll, 1)
        self.input = QLineEdit();self.input.setPlaceholderText(tr('Tag hinzufügen'));self.input.setAccessibleName(tr('Tag hinzufügen'));self.input.setMaxLength(200);self.input.setMaximumWidth(220);layout.addWidget(self.input)
        self.add_button = button(tr('Hinzufügen'), self.add);self.add_button.setMaximumWidth(110);layout.addWidget(self.add_button);layout.addStretch()
        self.input.returnPressed.connect(self.add)
        from notes_properties_ui import show as show_properties
        self.properties_button=button(tr('Eigenschaften'),lambda:window.safe(show_properties,window),'document-properties');self.properties_button.hide()
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(120)
        self.timer.timeout.connect(self.refresh)
        window.editor.textChanged.connect(lambda:self.timer.start())
        window.title.textChanged.connect(lambda:self.timer.start())
        self.refresh()

    def refresh(self):
        w = self.window
        path = w.doc['path'] if w.doc else None
        if path != self.path: self.input.clear()
        if path != self.path and hasattr(self, 'picker'): self.picker.close()
        self.path = path
        enabled = bool(w.doc and w.editor.isEnabled() and not w.editor.isReadOnly() and w.area == 'user')
        self.setEnabled(enabled); self.setVisible(w.area == 'user')
        values = tags(w.document_text()) if w.doc else []
        if values == self.values: return
        self.values = values
        while self.chip_layout.count():
            item = self.chip_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.scroll.setVisible(bool(values))
        for tag in values:
            chip = button('#'+tag+'  ×', lambda checked=False,t=tag:self.window.safe(self.change,t,False))
            chip.setObjectName('noteTagChip'); chip.setAccessibleName(tr('Tag {0} entfernen', tag))
            chip.setToolTip(tr('Tag {0} nur aus dieser Notiz entfernen', tag)); self.chip_layout.addWidget(chip,0,Qt.AlignVCenter)
        self.chip_layout.addStretch()
        self.scroll.setMaximumWidth(min(320,self.chips.sizeHint().width()+8))

    def add(self):
        if not self.input.text().strip(): self.open_picker(); return
        def commit():
            self.change(self.input.text(),True);self.input.clear();self.input.setFocus()
        self.window.safe(commit)

    def change(self, tag, checked):
        w = self.window
        if not w.doc or w.area != 'user' or not w.editor.isEnabled() or w.editor.isReadOnly(): return
        tag = identity(tag)
        current = tags(w.document_text())
        if checked and tag in current: return
        if checked and len(current) >= 100: raise ValueError(tr('Maximal 100 Tags pro Notiz.'))
        # Validate every part first so invalid YAML leaves the whole draft intact.
        prefix = add_tag(w.heading_prefix, tag) if checked else rename_tag(w.heading_prefix,tag,'',descendants=False)
        body = w.editor.toPlainText()
        changed = body if checked else rename_tag(body,tag,'',descendants=False)
        title = w.title.text() if checked else rename_tag(w.title.text(),tag,'',descendants=False)
        w.heading_prefix = prefix
        if changed != body:
            # A cursor edit retains the user's existing text undo history.
            start = 0
            while start < min(len(body),len(changed)) and body[start] == changed[start]: start += 1
            end = 0
            while end < min(len(body)-start,len(changed)-start) and body[-end-1] == changed[-end-1]: end += 1
            cursor = w.editor.textCursor(); cursor.beginEditBlock()
            cursor.setPosition(qt_length(body[:start]))
            cursor.setPosition(qt_length(body[:len(body)-end]),QTextCursor.KeepAnchor)
            cursor.insertText(changed[start:len(changed)-end]); cursor.endEditBlock()
        w.title.setText(title); w.edited(); self.refresh()

    def open_picker(self):
        self.refresh()
        if not self.isEnabled(): return
        if hasattr(self,'picker'): self.picker.close(); self.picker.deleteLater()
        menu = QMenu(self); self.picker = menu
        panel = QWidget(); panel.setMinimumWidth(290); box = QVBoxLayout(panel)
        box.addWidget(label(tr('Tags dieser Notiz'), 'heading'))
        search = QLineEdit(); search.setPlaceholderText(tr('Tag suchen oder neu eingeben …')); search.setAccessibleName(tr('Tag suchen oder anlegen')); box.addWidget(search)
        choices = QListWidget(); choices.setMaximumHeight(210); choices.setAccessibleName(tr('Vorhandene Tags')); box.addWidget(choices)
        message = label('', 'muted'); message.hide(); box.addWidget(message)
        available = sorted(set(self.values) | {t for note in self.window.notes.values() for t in note['tags']})
        def populate():
            choices.blockSignals(True); choices.clear()
            for tag in available:
                if search.text().strip().lstrip('#').casefold() not in tag.casefold(): continue
                item = QListWidgetItem(tag); item.setData(Qt.UserRole,tag); item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if tag in self.values else Qt.Unchecked); choices.addItem(item)
            choices.blockSignals(False)
        def change(tag, checked):
            try:
                self.change(tag,checked); message.hide()
                if identity(tag) not in available: available.append(identity(tag)); available.sort()
                populate()
                return True
            except ValueError as error:
                message.setText(str(error)); message.show(); populate()
                return False
        choices.itemChanged.connect(lambda item:change(item.data(Qt.UserRole),item.checkState()==Qt.Checked))
        def add():
            if change(search.text(),True): search.clear(); search.setFocus()
        search.textChanged.connect(populate); search.returnPressed.connect(add)
        box.addWidget(button(tr('Tag hinzufügen'),add,'list-add'))
        box.addWidget(button(tr('Fertig'),menu.close))
        action = QWidgetAction(menu); action.setDefaultWidget(panel); menu.addAction(action)
        populate(); menu.popup(self.add_button.mapToGlobal(self.add_button.rect().bottomLeft())); search.setFocus()
