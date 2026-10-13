"""Six settings categories, direct setting search and expandable technical details."""
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QStackedWidget, QFormLayout,
    QAbstractButton)
from lumen_i18n import tr
from lumen_qt import is_deleted


def label(value, style=''):
    item = QLabel(value); item.setWordWrap(True); item.setTextFormat(Qt.PlainText)
    if style: item.setObjectName(style)
    return item


class Details(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        self.toggle = QPushButton(title); self.toggle.setAutoDefault(False); self.toggle.setCheckable(True); self.toggle.setObjectName('quiet')
        self.body = QWidget(); self.body.settings_toggle = self.toggle
        self.content = QVBoxLayout(self.body); self.content.setContentsMargins(0, 8, 0, 0)
        self.body.hide(); self.toggle.toggled.connect(self.body.setVisible)
        self.toggle.setAccessibleName(title)
        def caption(opened): self.toggle.setText(('⌄  ' if opened else '›  ') + title.replace('&', '&&'))
        self.toggle.toggled.connect(caption); caption(False)
        root.addWidget(self.toggle, 0, Qt.AlignLeft); root.addWidget(self.body)


class SettingsNavigation(QWidget):
    def __init__(self, stack, pages, categories, parent=None):
        super().__init__(parent)
        self.stack = stack; self.pages = pages; self.categories = categories
        self.view = ('category', 0); self.previous = self.view; self.hits = []
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(20)
        header = QHBoxLayout()
        title = label(tr('Einstellungen'), 'heading'); title.setMinimumWidth(240)
        header.addWidget(title)
        self.search = QLineEdit(); self.search.setPlaceholderText(tr('Eine Einstellung suchen …'))
        self.search.setAccessibleName(tr('Alle Einstellungen durchsuchen')); self.search.setClearButtonEnabled(True)
        header.addWidget(self.search, 1); root.addLayout(header)
        body = QHBoxLayout(); body.setSpacing(20); root.addLayout(body, 1)
        self.nav = QListWidget(); self.nav.setObjectName('settingsNavigation')
        self.nav.setAccessibleName(tr('Einstellungsbereiche')); self.nav.setFixedWidth(240); self.nav.setSpacing(6)
        for category in categories: self.nav.addItem(category['title'])
        body.addWidget(self.nav)
        self.content = QStackedWidget(); body.addWidget(self.content, 1)
        overview = QScrollArea(); overview.setWidgetResizable(True); overview.setFrameShape(QScrollArea.NoFrame)
        self.overview = QWidget(); self.overview_layout = QVBoxLayout(self.overview)
        self.overview_layout.setContentsMargins(8, 4, 8, 4); self.overview_layout.setSpacing(10)
        overview.setWidget(self.overview); self.content.addWidget(overview)
        detail = QWidget(); detail_layout = QVBoxLayout(detail); detail_layout.setContentsMargins(0, 0, 0, 0)
        self.back = QPushButton(); self.back.setAutoDefault(False); self.back.setObjectName('quiet'); self.back.clicked.connect(self.go_back)
        detail_layout.addWidget(self.back, 0, Qt.AlignLeft); detail_layout.addWidget(stack, 1)
        self.content.addWidget(detail)
        results = QWidget(); results_layout = QVBoxLayout(results); results_layout.setContentsMargins(8, 4, 8, 4)
        self.result_title = label(tr('Suchergebnisse'), 'heading'); results_layout.addWidget(self.result_title)
        self.results = QListWidget(); self.results.setObjectName('settingsResults')
        self.results.setAccessibleName(tr('Gefundene Einstellungen')); results_layout.addWidget(self.results)
        self.empty = label(tr('Keine passende Einstellung. Versuche zum Beispiel „Stimme“, „Vorschau“ oder „Tastenkürzel“.'))
        results_layout.addWidget(self.empty); self.content.addWidget(results)
        self.nav.currentRowChanged.connect(self.show_category)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.activate_first)
        self.results.itemClicked.connect(self.activate_result)
        self.results.itemActivated.connect(self.activate_result)
        shortcut = QShortcut(QKeySequence.Find, self); shortcut.activated.connect(self.focus_search)
        self.nav.setCurrentRow(0)

    def focus_search(self):
        self.search.setFocus(); self.search.selectAll()

    def clear_search(self):
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)

    def owner(self, page):
        return next((i for i, group in enumerate(self.categories) if any(row['page'] == page for row in group['sections'])), 0)

    def show_category(self, index):
        if index < 0: return
        self.clear_search(); self.view = ('category', index)
        group = self.categories[index]
        while self.overview_layout.count():
            item = self.overview_layout.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().deleteLater()
        self.overview_layout.addWidget(label(group['title'], 'heading'))
        self.overview_layout.addWidget(label(group['description'], 'settingsDescription'))
        self.overview_layout.addSpacing(8)
        for section in group['sections']:
            entry = QPushButton(); entry.setAutoDefault(False); entry.setObjectName('settingsSection'); entry.setMinimumHeight(72)
            entry.setAccessibleName(section['title'] + '. ' + section['description'])
            row = QHBoxLayout(entry); row.setContentsMargins(16, 12, 16, 12)
            copy = QVBoxLayout(); copy.setSpacing(4)
            heading = label(section['title'], 'settingsSectionTitle')
            description = label(section['description'], 'settingsDescription')
            for child in (heading, description):
                child.setAttribute(Qt.WA_TransparentForMouseEvents); copy.addWidget(child)
            row.addLayout(copy, 1); arrow = label('›'); arrow.setAttribute(Qt.WA_TransparentForMouseEvents); row.addWidget(arrow)
            entry.clicked.connect(lambda _=False, s=section, c=index: self.activate_page(s['page'], s.get('target'), c))
            self.overview_layout.addWidget(entry)
        self.overview_layout.addStretch()
        self.content.setCurrentIndex(0)

    def activate_page(self, page, target=None, category=None):
        """User activation may open an app; restoring a settings page never does."""
        category = self.owner(page) if category is None else category
        self.open_page(page, target, category)
        if target is None:
            section = next((row for row in self.categories[category]['sections']
                            if row['page'] == page and row.get('activate')), None)
            if section: section['activate']()

    def open_page(self, page, target=None, category=None):
        if not 0 <= page < self.stack.count(): return
        self.clear_search(); category = self.owner(page) if category is None else category
        self.nav.blockSignals(True); self.nav.setCurrentRow(category); self.nav.blockSignals(False)
        self.back.setText('‹  ' + self.categories[category]['title'].replace('&', '&&'))
        self.stack.setCurrentIndex(page); self.content.setCurrentIndex(1); self.view = ('page', page)
        if target is not None and is_deleted(target): target = None
        if target is not None:
            ancestor = target
            while ancestor is not None and ancestor is not self.stack:
                toggle = getattr(ancestor, 'settings_toggle', None)
                if toggle is not None: toggle.setChecked(True)
                ancestor = ancestor.parentWidget()
            def focus():
                if is_deleted(target): return
                self.stack.widget(page).ensureWidgetVisible(target, 24, 36)
                target.setFocus(Qt.OtherFocusReason)
            QTimer.singleShot(0, focus)

    def go_back(self):
        self.show_category(self.nav.currentRow())

    def records(self):
        # Index authored labels, not values containing private paths, keys or model names.
        for page, info in enumerate(self.pages):
            category = self.owner(page); crumb = self.categories[category]['title'] + '  ›  ' + info['title']
            yield info['title'], crumb, page, None, category
            widget = self.stack.widget(page).widget(); fields = {}
            for form in widget.findChildren(QFormLayout):
                for row in range(form.rowCount()):
                    caption = form.itemAt(row, QFormLayout.LabelRole); field = form.itemAt(row, QFormLayout.FieldRole)
                    if caption and isinstance(caption.widget(), QLabel) and field:
                        target = field.widget()
                        if target is None and field.layout():
                            target = next((field.layout().itemAt(i).widget() for i in range(field.layout().count()) if field.layout().itemAt(i).widget()), None)
                        fields[caption.widget()] = target
            seen = set()
            for child in widget.findChildren(QWidget):
                if isinstance(child, QLabel) and child not in fields: continue
                name = child.text() if isinstance(child, (QLabel, QAbstractButton)) else child.accessibleName()
                name = ' '.join(name.replace('&', '').split())
                if not name or len(name) > 110 or name in seen: continue
                if isinstance(child, QAbstractButton) and any(word.casefold() in name.casefold() for word in (tr('Übernehmen'), tr('Speichern'))): continue
                seen.add(name)
                yield name, crumb, page, fields.get(child) or child, category
        for category, group in enumerate(self.categories):
            for row in group['sections']:
                yield row['title'], group['title']+'  ›  '+row['description'], row['page'], row.get('target'), category

    def filter(self, query):
        words = query.casefold().split()
        if not words:
            kind, value = self.previous
            if kind == 'page': self.open_page(value)
            else: self.show_category(value)
            return
        if self.content.currentIndex() != 2: self.previous = self.view
        self.results.clear(); self.hits = []; seen = set()
        records = sorted(self.records(), key=lambda row: (not all(word in row[0].casefold() for word in words), row[3] is not None))
        for name, crumb, page, target, category in records:
            if not all(word in (name+' '+crumb).casefold() for word in words): continue
            key = (page, ' '.join(name.replace('&', '').split()).casefold())
            if key in seen: continue
            seen.add(key); self.hits.append((page, target, category))
            item = QListWidgetItem(name+'\n'+crumb); item.setSizeHint(QSize(0, 64))
            item.setData(Qt.UserRole, len(self.hits)-1); self.results.addItem(item)
        self.result_title.setText(tr('Gefundene Einstellungen: {0}', len(self.hits)))
        self.empty.setVisible(not self.hits); self.results.setVisible(bool(self.hits))
        if self.hits: self.results.setCurrentRow(0)
        self.content.setCurrentIndex(2)

    def activate_first(self):
        if self.hits: self.activate_result(self.results.currentItem())

    def activate_result(self, item):
        if item is not None: self.activate_page(*self.hits[item.data(Qt.UserRole)])


def categories(dialog):
    def section(page, title=None, description=None, target=None, activate=None):
        info = dialog.page_info[page]
        return dict(page=page, title=title or info['title'], description=description or info['subtitle'], target=target, activate=activate)
    from lumen_apps import catalogue
    return [
        dict(title=tr('Darstellung & Desktop'), description=tr('Das Aussehen und die Bedienung deines Desktops.'), sections=[
            section(3, description=tr('Themes, Farben und Fensterdekorationen')),
            section(4, description=tr('Position, Größe und Elemente deiner Panels')),
            section(2, description=tr('Lumen und seine Funktionen per Tastatur öffnen')),
            section(6, tr('Systemintegration'), tr('Standardprogramme, Benachrichtigungen und KDE'))]),
        dict(title=tr('KI & Sprache'), description=tr('Wie Lumen arbeitet, zuhört und spricht.'), sections=[
            section(0, tr('Modell & Arbeitsweise'), tr('KI-Modell, Sprache und Vorgaben für Gespräche')),
            section(dialog.models_page, description=tr('Standard-, Hintergrund- und lokale Modelle, Zeitlimit und GPU')) ,
            section(dialog.persona_page, description=tr('Vorlagen, Nähe, Anrede und Antwortstil')),
            section(dialog.app_pages['wissen'], tr('Gedächtnis'), tr('Was Lumen über dich weiß und aus Gesprächen lernt'), activate=lambda: __import__('lumen_apps').launch('wissen', area='lumen')),
            section(dialog.speech_input_page, description=tr('Diktat, Erkennungssprache und Mikrofon')),
            section(dialog.speech_output_page, description=tr('Aussprache und Stimme in allen Lumen-Apps'))]),
        dict(title=tr('Dateien & Speicher'), description=tr('Deine Dateien, Vorschauen und verbundenen Orte.'), sections=[
            section(1, tr('Navigation & Vorschau'), tr('Startordner, Tabs, versteckte Dateien und PDF-Bearbeitung')),
            section(1, tr('Dateisuche'), tr('Tipp-Pause und Anzahl der Suchtreffer'), dialog.delay),
            section(1, tr('Orte & Server'), tr('Favoriten, Bibliotheken und NAS · SMB, SFTP, WebDAV'), dialog.places),
            section(dialog.accounts_page),
            section(dialog.app_pages['vault'], tr('Sicherungen'), tr('Sicherungspläne in Lumen System')),
            section(dialog.server_page, tr('Server & Synchronisation'), tr('Verbindung und automatischer Datenabgleich'))]),
        dict(title=tr('Apps'), description=tr('Eigene Einstellungen für jede Lumen-App.'), sections=[
            section(dialog.app_pages[key], tr('Sicherungen') if key == 'vault' else title, tr('Sicherungspläne in Lumen System') if key == 'vault' else description, activate=dialog.open_system if key == 'system' else None) for key, title, description, icon in catalogue(include_utilities=True) if key != 'search']),
        dict(title=tr('Datenschutz & Freigaben'), description=tr('Was Lumen lesen, behalten und verändern darf.'), sections=[
            section(0, tr('Werkzeugfreigaben'), tr('Nachfragen und Freigaben für Befehle und Dateiänderungen'), dialog.auto),
            section(9, tr('KI-Zugriff & MCP'), tr('Zugriff auf lokale Nachrichten, Termine und Werkzeuge')),
            section(dialog.app_pages['wissen'], tr('Lumen-Gedächtnis'), tr('Erinnerungen und ihre Freigaben'), activate=lambda: __import__('lumen_apps').launch('wissen', area='lumen'))]),
        dict(title=tr('Wartung'), description=tr('Einrichtung, Hintergrunddienste und Hilfe bei Problemen.'), sections=[
            section(dialog.troubleshooter_page, description=tr('Lumen prüfen und Hilfe zu gefundenen Problemen erhalten')),
            section(dialog.app_pages['updater']),
            section(8, description=tr('Anbieter verbinden und Erweiterungen installieren')),
            section(5, description=tr('Autostart, Zeitpläne und automatische Analysen')),
            section(7, description=tr('Absturzerkennung, Wiederherstellung und Fehlerberichte')),
            section(dialog.hardware_page, description=tr('Leistung, Geräte und Hintergrundarbeit'), activate=dialog.open_system)]),
    ]
