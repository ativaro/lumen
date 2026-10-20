"""Compact Files menus; the palette invokes the very same native QActions."""
from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QAction, QFont, QFontMetrics, QIcon, QKeySequence, QPalette
from PySide6.QtWidgets import (QAbstractButton, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QStyle, QStyledItemDelegate, QToolButton,
    QVBoxLayout, QWidget, QWidgetAction)
from lumen_i18n import tr


def navigation_event(event):
    kind = event.type()
    if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
        return event.button() in (Qt.BackButton, Qt.ForwardButton)
    if kind == QEvent.MouseMove:
        return bool(event.buttons() & (Qt.BackButton | Qt.ForwardButton))
    return kind in (QEvent.KeyPress, QEvent.KeyRelease) and event.key() in (Qt.Key_Back, Qt.Key_Forward)


def entries(menu, prefix=''):
    """Flatten visible commands, retaining category, shortcut and enabled state."""
    result = []
    for action in getattr(menu, 'quick_actions', []) + menu.actions():
        if not action.isVisible() or action.isSeparator() or isinstance(action, QWidgetAction):
            continue
        title = action.text().split('\t')[0].replace('&&', '&')
        if action.menu():
            if action.isEnabled():
                result.extend(entries(action.menu(), f'{prefix}{title} / '))
        elif not action.property('actionSearch'):
            result.append((action, prefix))
    return result


class ActionResultDelegate(QStyledItemDelegate):
    """One command per row, with its category visually secondary."""
    def sizeHint(self, option, index):
        return QSize(0, 58)

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect.adjusted(0, 2, -1, -2)
        selected = bool(option.state & QStyle.State_Selected)
        enabled = bool(option.state & QStyle.State_Enabled)
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(option.palette.midlight())
            painter.drawRoundedRect(rect, 8, 8)
        title, _, category = str(index.data() or '').partition('\n')
        icon = index.data(Qt.DecorationRole)
        if icon and not icon.isNull():
            icon.paint(painter, QRect(rect.left() + 12, rect.center().y() - 9, 18, 18),
                       Qt.AlignCenter, QIcon.Normal if enabled else QIcon.Disabled)
        text_rect = rect.adjusted(42, 7, -12, -6)
        font = QFont(option.font)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(option.palette.color(QPalette.Text if enabled else QPalette.PlaceholderText))
        painter.drawText(text_rect, Qt.AlignTop | Qt.AlignLeft,
                         QFontMetrics(font).elidedText(title, Qt.ElideRight, text_rect.width()))
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(option.palette.color(QPalette.PlaceholderText))
        painter.drawText(text_rect, Qt.AlignBottom | Qt.AlignLeft,
                         QFontMetrics(font).elidedText(category, Qt.ElideRight, text_rect.width()))
        painter.restore()


class ActionSearch(QDialog):
    def __init__(self, menu):
        super().__init__(menu.parentWidget())
        self.setWindowTitle(tr('Lumen Files — Alle Aktionen'))
        self.setFixedWidth(480)
        self.commands = entries(menu)
        self.chosen = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(12)
        title = QLabel(menu.selection_title, self)
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        title.setObjectName('actionSearchTitle')
        layout.addWidget(title)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr('Aktion suchen …'))
        self.search.setAccessibleName(tr('Alle Dateiaktionen durchsuchen'))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(QIcon.fromTheme('edit-find'), QLineEdit.LeadingPosition)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)
        self.results = QListWidget(self)
        self.results.setObjectName('fileActionResults')
        self.results.setAccessibleName(tr('Verfügbare Dateiaktionen'))
        self.results.setItemDelegate(ActionResultDelegate(self.results))
        self.results.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.results.itemActivated.connect(self.choose)
        self.results.installEventFilter(self)
        layout.addWidget(self.results)
        self.message = QLabel(self)
        self.message.setObjectName('muted')
        layout.addWidget(self.message)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(lambda: self.choose(self.results.currentItem()))
        self.setStyleSheet('''
            QLabel#actionSearchTitle { font-size: 14px; font-weight: 600; }
            QLineEdit { font-size: 14px; padding: 10px 12px; border-radius: 9px; }
            QListWidget#fileActionResults { border: none; background: transparent; }
        ''')
        title.ensurePolished()
        title.setWordWrap(False)
        title.setToolTip(menu.selection_title)
        title.setText(title.fontMetrics().elidedText(menu.selection_title, Qt.ElideMiddle, 448))
        self.filter('')
        self.search.setFocus()

    def filter(self, query):
        self.results.clear()
        words = query.casefold().split()
        first = None
        for action, category in self.commands:
            if not action.isVisible() or not all(w in (category + action.text()).casefold() for w in words):
                continue
            title, _, shortcut = action.text().partition('\t')
            detail = category.rstrip(' / ')
            if shortcut:
                detail = ' · '.join(filter(None, (detail, shortcut)))
            item = QListWidgetItem(action.icon(), title + ('\n' + detail if detail else ''))
            item.setData(Qt.UserRole, action)
            item.setToolTip(title + ('\n' + detail if detail else ''))
            if item.icon().isNull():
                item.setIcon(QIcon.fromTheme('view-list-details'))
            if not action.isEnabled():
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
            elif first is None:
                first = item
            self.results.addItem(item)
        if first is not None:
            self.results.setCurrentItem(first)
        self.message.setText(tr('Keine passende Aktion.') if not self.results.count()
                             else tr('↑ ↓ auswählen · Enter ausführen · Esc schließen'))
        self.results.setFixedHeight(max(1, min(7, self.results.count())) * 58)
        self.layout().activate()
        self.setFixedHeight(self.layout().sizeHint().height())

    def choose(self, item):
        if item is None:
            return
        action = item.data(Qt.UserRole)
        if action.isEnabled() and action.isVisible():
            self.chosen = action
            self.accept()

    def eventFilter(self, watched, event):
        if navigation_event(event):
            return True
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.reject()
                return True
            if watched is self.search and event.key() in (Qt.Key_Down, Qt.Key_Up):
                self.results.setFocus()
                return True
        return super().eventFilter(watched, event)


class ActionMenu(QMenu):
    def __init__(self, parent, title, subtitle='', icon='folder'):
        super().__init__(parent)
        self.selection_title = title
        self.quick_actions = []
        self.setObjectName('fileActionCard')
        self.setMinimumWidth(376)
        self.setStyleSheet('''
            QMenu { background: palette(window); color: palette(text); border: 1px solid palette(mid); border-radius: 12px; padding: 10px; font-size: 13px; }
            QMenu::item { padding: 11px 18px 11px 12px; border-radius: 6px; }
            QMenu::item:selected { background: palette(highlight); color: palette(highlighted-text); }
            QMenu::separator { height: 1px; background: palette(mid); margin: 7px 8px; }
            QToolButton { background: palette(button); color: palette(button-text); border: 1px solid palette(mid); border-radius: 8px; padding: 7px 2px; font-size: 10px; }
            QToolButton:hover, QToolButton:focus { background: palette(midlight); border-color: palette(highlight); }
            QToolButton:disabled { color: palette(dark); }
            QLabel#actionTitle { font-weight: 600; font-size: 14px; }
            QLabel#actionLocation { color: palette(placeholder-text); font-size: 11px; }
            QPushButton#actionSearchButton { text-align: left; background: palette(base); color: palette(placeholder-text); border: 1px solid palette(mid); border-radius: 8px; padding: 11px 12px; font-size: 13px; }
            QPushButton#actionSearchButton:hover, QPushButton#actionSearchButton:focus { color: palette(text); background: palette(midlight); border-color: palette(highlight); }
        ''')
        header = QWidget(self)
        box = QHBoxLayout(header)
        box.setContentsMargins(12, 10, 12, 14)
        box.setSpacing(14)
        symbol = QLabel(header)
        symbol.setPixmap(QIcon.fromTheme(icon).pixmap(26, 26))
        box.addWidget(symbol)
        labels = QVBoxLayout()
        labels.setSpacing(4)
        for text, name in ((title, 'actionTitle'), (subtitle, 'actionLocation')):
            label = QLabel(header)
            label.setObjectName(name)
            label.setTextFormat(Qt.PlainText)
            label.setText(label.fontMetrics().elidedText(text, Qt.ElideMiddle, 255))
            label.setToolTip(text)
            labels.addWidget(label)
        box.addLayout(labels, 1)
        self.add_widget(header)
        quick = QWidget(self)
        self.quick_layout = QHBoxLayout(quick)
        self.quick_layout.setContentsMargins(4, 4, 4, 14)
        self.quick_layout.setSpacing(6)
        self.add_widget(quick)

    def add_widget(self, widget):
        action = QWidgetAction(self)
        action.setDefaultWidget(widget)
        self.addAction(action)
        return action

    def quick(self, text, icon, callback, shortcut='', enabled=True):
        action = QAction(QIcon.fromTheme(icon), text + ('\t' + shortcut if shortcut else ''), self)
        action.setEnabled(enabled)
        action.triggered.connect(callback)
        self.quick_actions.append(action)
        button = QToolButton(self)
        button.setText(text)
        button.setIcon(action.icon())
        button.setIconSize(QSize(20, 20))
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setFixedSize(80, 62)
        button.setAccessibleName(text)
        button.setToolTip(action.text().replace('\t', ' · '))
        button.setEnabled(enabled)
        button.setFocusPolicy(Qt.StrongFocus)
        button.clicked.connect(lambda: self.invoke(action))
        self.quick_layout.addWidget(button, 1)
        return action

    def invoke(self, action):
        if action.isEnabled():
            self.close()
            action.trigger()

    def finish(self):
        self.addSeparator()
        footer = QWidget(self)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(4, 5, 4, 4)
        button = QPushButton(QIcon.fromTheme('edit-find'), tr('Alle Aktionen durchsuchen …'), footer)
        button.setObjectName('actionSearchButton')
        button.setAccessibleName(tr('Alle Dateiaktionen durchsuchen'))
        button.setToolTip(QKeySequence(QKeySequence.Find).toString(QKeySequence.NativeText))
        layout.addWidget(button)
        action = self.add_widget(footer)
        action.triggered.connect(self.search_actions)
        button.clicked.connect(action.trigger)
        action.setProperty('actionSearch', True)
        # Qt menus can activate a hovered command on a side-button release.
        # Cover submenus as well as the card, including Files embedded in Lumen.
        for widget in [self, *self.findChildren(QMenu), *self.findChildren(QAbstractButton)]:
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if navigation_event(event):
            return True
        if event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                buttons = [b for b in self.findChildren(QAbstractButton) if b.isEnabled()]
                if buttons:
                    current = self.focusWidget()
                    index = buttons.index(current) if current in buttons else -1
                    direction = -1 if event.key() == Qt.Key_Backtab or event.modifiers() & Qt.ShiftModifier else 1
                    buttons[(index + direction) % len(buttons)].setFocus()
                return True
            if isinstance(watched, QAbstractButton) and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                watched.click()
                return True
        return super().eventFilter(watched, event)

    def search_actions(self):
        self.close()
        dialog = ActionSearch(self)
        if dialog.exec() == QDialog.Accepted and dialog.chosen is not None:
            dialog.chosen.trigger()
        dialog.deleteLater()

    def keyPressEvent(self, event):
        # Quick actions have no duplicate window-wide shortcuts: Files already owns them.
        keys = [(QKeySequence.Copy, 0), (QKeySequence.Cut, 1), (QKeySequence.Delete, 3)]
        selected = next((i for key, i in keys if event.matches(key)), None)
        if event.key() == Qt.Key_F2:
            selected = 2
        if selected is not None and selected < len(self.quick_actions):
            self.invoke(self.quick_actions[selected])
            return
        if event.matches(QKeySequence.Find):
            self.search_actions()
            return
        super().keyPressEvent(event)


def build_file_menu(self, paths):
    from pathlib import Path
    from PySide6.QtWidgets import QApplication, QFileDialog
    from drive_browser import is_drive
    from file_spaces import SHELF, virtual
    drive=bool(paths and is_drive(paths[0])) or is_drive(self.current_location)
    if not paths:
        menu = QMenu(self)
        menu.addAction(tr('Hier einfügen\tStrg+V'), self.paste)
        menu.addAction(tr('Neuer Ordner'), self.mkdir)
        menu.addSeparator()
        if drive:
            menu.addAction(tr('Aktualisieren'),self.refresh)
            menu.addAction(tr('Synchronisation und Offline-Verfügbarkeit …'),lambda:self.drive.settings(False))
        else:menu.addAction(tr('Letzte Lumen-Dateiaktion rückgängig …'), lambda: self.organize_files('undo'))
        if not drive and not virtual(self.current_location):
            menu.addAction(tr('Eigenschaften …'), lambda: self.show_properties([self.current_path]))
        return menu
    title = (self.drive.entries[paths[0]][1]['name'] if drive else Path(paths[0]).name) if len(paths) == 1 else tr('{0} Einträge ausgewählt', len(paths))
    directory = len(paths) == 1 and (self.drive.entries[paths[0]][0]=='folder' if drive else Path(paths[0]).is_dir())
    writable = not drive or all(self.drive.entries[p][1].get('can_write') is True for p in paths)
    menu = ActionMenu(self, title, 'Lumen Drive' if drive else str(Path(paths[0]).parent) if len(paths) == 1 else tr('Mehrfachauswahl'),
                      'folder' if directory or len(paths) > 1 else 'text-x-generic')
    menu.quick(tr('Kopieren'), 'edit-copy', lambda: self.copy(False), tr('Strg+C'))
    menu.quick(tr('Ausschneiden'), 'edit-cut', lambda: self.copy(True), tr('Strg+X'), enabled=writable)
    menu.quick(tr('Umbenennen'), 'edit-rename', self.rename, 'F2', enabled=writable and (not drive or len(paths)==1))
    menu.quick(tr('Papierkorb'), 'user-trash', self.trash, tr('Entf'), enabled=writable)
    menu.addAction(QIcon.fromTheme('document-open'), tr('Öffnen'), self.open_selected)
    if len(paths) == 1:
        preview_action = menu.addAction(QIcon.fromTheme('view-preview'), tr('Große Vorschau'), self.quicklook)
        preview_action.setToolTip(tr('Große Vorschau\tLeertaste').replace('\t', ' · '))
    menu.addSeparator()
    organize = menu.addMenu(QIcon.fromTheme('folder'), tr('Organisieren'))
    safety = menu.addMenu(QIcon.fromTheme('document-save'), tr('Sichern & synchronisieren').replace('&', '&&'))
    from interop_ui import files_menu
    files_menu(self, menu, paths, safety=safety)
    if drive:
        if directory:organize.addAction(tr('In neuem Tab öffnen'),lambda:self.new_tab(paths[0]))
        def download():
            target=QFileDialog.getExistingDirectory(self,tr('Downloadordner'))
            if target:self.drive.download(paths,target)
        organize.addAction(tr('Herunterladen …'),download)
        organize.addAction(tr('Hier einfügen'),self.paste)
        organize.addAction(tr('Neuer Ordner'),self.mkdir)
        organize.addAction(tr('Aktualisieren'),self.refresh)
        def upload():
            chosen,_=QFileDialog.getOpenFileNames(self,tr('Dateien hochladen …'))
            if chosen:self.drive.upload(chosen)
        safety.addAction(tr('Dateien hochladen …'),upload)
        safety.addAction(tr('Offline verfügbar …'),lambda:self.drive.settings(True))
        safety.addAction(tr('Synchronisation und Offline-Verfügbarkeit …'),lambda:self.drive.settings(False))
    else:
        if all(Path(p).suffix.lower() == '.pdf' for p in paths):
            self.add_workshop_action(organize, paths)
        organize.addAction(tr('Zur Sammelfläche hinzufügen'), lambda: self.spaces.collect(paths))
        organize.addAction(tr('In Ordner kopieren …'), self.spaces.copy_to)
        if self.current_location == SHELF:
            organize.addAction(tr('Aus Sammelfläche entfernen (Dateien behalten)'), lambda: self.spaces.remove_shelf(paths))
        if len(paths) == 1:
            safety.addAction(tr('Dateiversionen …'), lambda: self.show_versions(paths[0]))
            organize.addAction(tr('Enthaltenden Ordner öffnen'), lambda: self.navigate(Path(paths[0]).parent))
            if directory:
                organize.addAction(tr('In neuem Tab öffnen'), lambda: self.new_tab(paths[0]))
                from drive_ui import show as show_drive
                safety.addAction(tr('Mit Lumen Drive synchronisieren …'), lambda: show_drive(self, paths[0]))
                remote = self.network.remote(paths[0])
                if remote: safety.addAction(tr('Offline verfügbar machen …'), lambda: self.offline.add(remote))
                organize.addAction(tr('Ordnergröße berechnen'), lambda: self.open_analysis(paths[0], apparent=True))
                organize.addAction(tr('Speicher analysieren'), lambda: self.open_analysis(paths[0]))
        organize.addAction(tr('Pfad kopieren'), lambda: QApplication.clipboard().setText('\n'.join(self.network.remote(p) or p for p in paths)))
        from file_actions import menu as personal_actions_menu
        personal_actions_menu(self, organize, paths)
        organize.addSeparator()
        organize.addAction(tr('Hier einfügen\tStrg+V'), self.paste)
        organize.addAction(tr('Neuer Ordner'), self.mkdir)
        organize.addAction(tr('Letzte Lumen-Dateiaktion rückgängig …'), lambda: self.organize_files('undo'))
    self.lumen_menu(menu, paths)
    menu.finish()
    menu.addAction(QIcon.fromTheme('document-properties'), tr('Eigenschaften …'), lambda: self.show_properties(paths))
    return menu


def add_lumen_actions(window, menu, paths):
    if not paths:return
    from pathlib import Path
    from drive_browser import is_drive
    from drive_references import readable,TEXT_SUFFIXES
    drive=all(is_drive(path) for path in paths)
    panel=getattr(getattr(window,'lumen_host',None),'chat',getattr(window,'assistant',None))
    server=getattr(getattr(panel,'backend',None),'execution','local')=='server'
    # Server formats are checked asynchronously after the explicit action, not by a second MIME list.
    supported=all(window.drive.entries[p][0]=='file' and (server or readable(window.drive.entries[p][1])) for p in paths) if drive else all(Path(p).suffix.lower() in TEXT_SUFFIXES+('.pdf','.png','.jpg','.jpeg','.webp','.tif','.tiff') for p in paths)
    submenu=menu.addMenu(QIcon.fromTheme('lumen'),tr('Mit Lumen …'))
    commands=[(tr('Besprechen'),'open')]
    if supported:commands += [(tr('Zusammenfassen'),'summarize'),(tr('Analysieren'),'analyze')]
    if not drive:commands += [(tr('Erklären'),'explain'),(tr('Fehler beheben'),'fix'),(tr('Git-Diff prüfen'),'review')]
    from interop_ui import safe_action
    for title,action in commands:
        submenu.addAction(title,lambda _=False,a=action:safe_action(window,lambda:window.ask_lumen(a,paths)))
    if not drive:
        submenu.addSeparator()
        submenu.addAction(tr('Intelligent umbenennen …'),lambda:window.organize_files('rename',paths))
        submenu.addAction(tr('Dateien sortieren …'),lambda:window.organize_files('sort',paths))
