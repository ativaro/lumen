"""Inspect the local OpenCode profile without changing configuration or conversations."""
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTabBar, QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter
from lumen_i18n import tr


STATUS = {'connected':'Verbunden', 'disabled':'Ausgeschaltet', 'needs_auth':'Anmeldung nötig',
          'needs_client_registration':'Anmeldung einrichten', 'failed':'Verbindung fehlgeschlagen', 'configured':'Eingerichtet'}
KINDS = (('mcp', 'MCP'), ('plugins', 'Plugins'), ('skills', 'Skills'))


def plugin_name(value):
    spec = value[0] if isinstance(value, list) and value else value
    if not isinstance(spec, str):
        return None
    if re.fullmatch(r'(?:@[\w.-]+/)?[\w.-]+(?:@[\w.^~+*-]+)?', spec):
        return spec[:200]
    if spec.startswith('file:'):
        return Path(unquote(urlsplit(spec).path)).name[:200] or tr('Lokales Plugin')
    if spec.startswith(('/', './', '../')):
        return Path(spec).name[:200] or tr('Lokales Plugin')
    return tr('Externes Plugin') if '://' in spec and not spec.startswith('file:') else tr('Lokales Plugin')


def inventory(config, mcp, skills):
    """Only display metadata; never expose full config, endpoints, headers or plugin options."""
    if not isinstance(config, dict) or not isinstance(mcp, dict) or not isinstance(skills, list):
        raise ValueError('Invalid inventory')
    configured = config.get('mcp', {})
    if not isinstance(configured, dict) or not isinstance(config.get('plugin', []), list):
        raise ValueError('Invalid configuration')
    rows = {'mcp': [], 'plugins': [], 'skills': []}
    for name in sorted(set(configured) | set(mcp)):
        value, status = configured.get(name, {}), mcp.get(name, {})
        if not isinstance(value, dict) or not isinstance(status, dict):
            continue
        state = 'disabled' if value.get('enabled') is False else status.get('status', 'configured')
        rows['mcp'].append(dict(name=name[:200], source=tr('Desktop'), status=tr(STATUS.get(state, 'Unbekannt')),
            description=tr('Werkzeuge dieser Verbindung verwenden weiterhin die Freigaben des jeweiligen Gesprächs.')))
    for value in config.get('plugin', []):
        name = plugin_name(value)
        if name:
            rows['plugins'].append(dict(name=name, source='OpenCode', status=tr('Eingerichtet'), description=tr('Zusätzlich konfiguriertes Plugin.')))
    for row in skills:
        if isinstance(row, dict) and isinstance(row.get('name'), str):
            rows['skills'].append(dict(name=row['name'][:200], source='OpenCode' if row.get('location')=='<built-in>' else tr('Desktop'),
                status=tr('Gefunden'), description=str(row.get('description', ''))[:4000], content=str(row.get('content', ''))[:64000]))
    return rows


class ExtensionsView(QWidget):
    def __init__(self, backend_factory, parent=None):
        super().__init__(parent)
        self.backend_factory = backend_factory
        self.backend = None
        self.rows = None
        self.loading = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(16)
        top = QHBoxLayout(); self.status = QLabel(tr('Desktop · Noch nicht ausgelesen')); self.status.setWordWrap(True)
        self.refresh_button = QPushButton(tr('Fähigkeiten laden')); self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.status, 1); top.addWidget(self.refresh_button); layout.addLayout(top)
        self.search = QLineEdit(); self.search.setPlaceholderText(tr('Name oder Beschreibung suchen …')); self.search.setAccessibleName(tr('Fähigkeiten durchsuchen'))
        self.search.textChanged.connect(self.render); layout.addWidget(self.search)
        self.tabs = QTabBar(); self.tabs.setExpanding(False)
        for _, title in KINDS: self.tabs.addTab(tr(title))
        self.tabs.currentChanged.connect(self.render); layout.addWidget(self.tabs)
        split = QSplitter(Qt.Horizontal); self.list = QListWidget(); self.list.setWordWrap(True); self.list.setAccessibleName(tr('Erweiterungen'))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setStyleSheet('QListWidget { padding:8px; } QListWidget::item { padding:8px; margin:4px; border-radius:8px; } QListWidget::item:selected { background:palette(midlight); color:palette(text); }')
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True); self.detail.setAccessibleName(tr('Details der Erweiterung')); self.detail.setPlaceholderText(tr('Wähle einen Eintrag, um mehr zu erfahren.'))
        split.addWidget(self.list); split.addWidget(self.detail); split.setSizes([230,440]); layout.addWidget(split, 1)
        self.list.currentItemChanged.connect(self.selected)
        self.status.setToolTip(tr('Zum Auslesen startet die vorhandene OpenCode-Laufzeit mit dem eingestellten Arbeitsordner. Bestehende Gespräche bleiben unverändert; ihre Freigaben können abweichen.'))
        self.setAccessibleDescription(tr('Die Freigaben gelten weiterhin je Gespräch.'))

    def refresh(self):
        if self.loading: return
        self.stop(); self.loading = True; self.refresh_button.setEnabled(False); self.status.setText(tr('Fähigkeiten werden ausgelesen …'))
        self.backend = self.backend_factory(self)
        backend = self.backend
        backend.failed.connect(self.failed)
        values = {}
        def loaded(key, value):
            if backend is not self.backend: return
            values[key] = value
            if len(values)!=3: return
            try: self.rows = inventory(values['config'], values['mcp'], values['skills'])
            except (ValueError, TypeError): self.failed(); return
            self.loading = False; self.refresh_button.setEnabled(True); self.refresh_button.setText(tr('Aktualisieren')); self.status.setText(tr('Desktop · Einrichtung ausgelesen'))
            self.render()
        def query():
            for key, route in [('config','/config'), ('mcp','/mcp'), ('skills','/skill')]:
                backend.request('GET', route, callback=lambda value, key=key:loaded(key,value), error=self.failed)
        backend.ensure_server(query)

    def failed(self, _error=None):
        self.loading = False; self.refresh_button.setEnabled(True)
        self.status.setText(tr('OpenCode konnte nicht ausgelesen werden. Prüfe die Engine-Einrichtung und versuche es erneut.'))

    def render(self, *_):
        name = self.list.currentItem().data(Qt.UserRole)['name'] if self.list.currentItem() else ''
        self.list.clear(); self.detail.clear()
        if self.rows is None: return
        key = KINDS[self.tabs.currentIndex()][0]; needle = self.search.text().casefold()
        for index, (kind, title) in enumerate(KINDS): self.tabs.setTabText(index, tr(title)+' · '+str(len(self.rows[kind])))
        for row in self.rows[key]:
            if needle not in (row['name']+' '+row['description']+' '+row['source']).casefold(): continue
            item = QListWidgetItem(row['name']+'\n'+row['source']+' · '+row['status']); item.setToolTip(row['name']+' · '+row['status']); item.setData(Qt.UserRole,row); self.list.addItem(item)
            if row['name']==name:self.list.setCurrentItem(item)
        if not self.list.count():
            self.detail.setPlainText(tr('Keine passenden Einträge.' if needle else 'Keine zusätzlichen Plugins eingerichtet.' if key=='plugins' else 'Keine Einträge gefunden.'))
        elif not self.list.currentItem():self.list.setCurrentRow(0)

    def selected(self, item, _previous=None):
        if item:
            row=item.data(Qt.UserRole)
            self.detail.setPlainText(row['name']+'\n'+row['source']+' · '+row['status']+'\n\n'+row['description']+ ('\n\n'+row['content'] if row.get('content') else ''))

    def stop(self):
        if self.backend:
            self.backend.shutdown(); self.backend.deleteLater(); self.backend = None
