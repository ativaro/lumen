"""Lumen System entry point and retained background-work preferences."""
from lumen_i18n import tr
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit
from lumen_store import Store


class HardwareView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        from lumen_apps import launch
        self.status = QLabel(tr('Messwerte, Verläufe und Geräte findest du in Lumen System.')); self.status.setWordWrap(True); layout.addWidget(self.status)
        open_system = QPushButton(tr('Lumen System öffnen')); open_system.setObjectName('openSystem')
        def open_app():
            try: launch('system')
            except (OSError, ValueError) as error: self.status.setText(str(error))
        open_system.clicked.connect(open_app); layout.addWidget(open_system)
        self.games = QCheckBox(tr('Bei Spielen und geöffneten Aufnahmeprogrammen Hintergrundarbeit pausieren'))
        self.games.setChecked(Store().setting('modelPolicy', {}).get('pause_on_activity', True)); layout.addWidget(self.games)
        self.games.toggled.connect(self.save)
        self.apps = QLineEdit(', '.join(Store().setting('modelPolicy', {}).get('activity_apps', [])))
        self.apps.setPlaceholderText(tr('Weitere Prozessnamen, z. B. minecraft, supertuxkart'))
        self.apps.setAccessibleName(tr('Weitere Spiele oder Aufnahmeprogramme')); self.apps.setMaxLength(500)
        layout.addWidget(self.apps)
        save_apps = QPushButton(tr('Weitere Programme übernehmen')); save_apps.clicked.connect(self.save_apps); layout.addWidget(save_apps)

    def save(self, value):
        store = Store(); policy = store.setting('modelPolicy', {}); policy['pause_on_activity'] = value
        store.set_setting('modelPolicy', policy)

    def save_apps(self):
        import re
        names = sorted(set(v.strip().lower() for v in self.apps.text().split(',') if v.strip()))
        if any(not re.fullmatch(r'[a-z0-9_.-]{1,15}', v) for v in names):
            self.status.setText(tr('Prozessnamen: maximal 15 Zeichen, Buchstaben, Zahlen, Punkt, Bindestrich oder Unterstrich.')); return
        store = Store(); policy = store.setting('modelPolicy', {}); policy['activity_apps'] = names
        store.set_setting('modelPolicy', policy); self.status.setText(tr('Zusätzliche Programme gespeichert.'))
