"""Native personality editor with local, illustrative preview."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QPushButton, QCheckBox, QMessageBox
from lumen_i18n import tr
from lumen_persona import PRESETS, FIELDS, load, normalize, preview
from settings_navigation import Details, label
from desktop_design import PAGE_SPACING


class PersonaEditor(QWidget):
    saved = Signal()

    def __init__(self, settings, voice_callback, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.initial = load(settings)
        self.original = settings.value('personaProfile', '')
        self.original_override=settings.value('personaLocalOverride',False,type=bool)
        from lumen_connect import read_config
        connection_error=''
        try:self.connection=read_config()
        except FileNotFoundError:self.connection=None
        except (OSError,ValueError):self.connection=None;connection_error=tr('Persona- oder Serverbindung nicht lesbar. Bitte Einstellungen prüfen.')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(PAGE_SPACING);outer.setAlignment(Qt.AlignTop)
        self.source=label(tr('Mit Serververbindung gilt dieselbe Konto-Persona wie im Web und auf Mobile. Deine lokale Persona bleibt erhalten.') if self.connection else tr('Lokale Desktop-Persona · keine Serververbindung'),'settingsDescription');outer.addWidget(self.source)
        if connection_error:self.source.setText(connection_error)
        self.account=QPushButton(tr('Konto-Persona auf dem Server bearbeiten'));self.account.setAutoDefault(False)
        self.account.clicked.connect(self.open_account);self.account.setVisible(bool(self.connection));outer.addWidget(self.account,0,Qt.AlignLeft)
        self.override=QCheckBox(tr('Auf diesem Desktop eine eigene Persona verwenden'));self.override.setChecked(self.original_override)
        self.override.setVisible(bool(self.connection));outer.addWidget(self.override)
        self.local_panel=QWidget();outer.addWidget(self.local_panel)
        root=QVBoxLayout(self.local_panel);root.setContentsMargins(0,0,0,0);root.setSpacing(PAGE_SPACING);root.setAlignment(Qt.AlignTop)
        self.preset = QComboBox(); self.preset.setAccessibleName(tr('Persönlichkeitsvorlage'))
        for identity, (title, _, _) in PRESETS.items(): self.preset.addItem(tr(title), identity)
        form = QFormLayout(); form.addRow(tr('Vorlage'), self.preset); root.addLayout(form)
        self.description = label('', 'settingsDescription'); root.addWidget(self.description)
        self.example_title = label(tr('Beispiel · „Mein NAS ist nicht erreichbar.“'), 'settingsSectionTitle')
        root.addWidget(self.example_title)
        self.example = label(''); self.example.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.example)
        self.summary = label('', 'settingsDescription'); root.addWidget(self.summary)
        root.addWidget(label(tr('Illustrative Vorschau ohne Modellanfrage. Echte Antworten hängen vom Auftrag und Modell ab.'), 'settingsDescription'))
        self.details = Details(tr('Persönlich anpassen')); root.addWidget(self.details)
        fields = QFormLayout(); fields.setRowWrapPolicy(QFormLayout.WrapLongRows); self.details.content.addLayout(fields)
        self.fields = {}
        for key, title in [('name', 'Name der Persona'), ('user_name', 'Dein bevorzugter Name')]:
            item = QLineEdit(); item.setMaxLength(60); item.setAccessibleName(tr(title))
            self.fields[key] = item; fields.addRow(tr(title), item)
            item.textChanged.connect(self.refresh)
        for key, (title, options) in FIELDS.items():
            item = QComboBox(); item.setAccessibleName(tr(title))
            for identity, caption in options: item.addItem(tr(caption), identity)
            fields.addRow(tr(title), item); self.fields[key] = item
            item.currentIndexChanged.connect(self.refresh)
        root.addWidget(label(tr('Gilt für Lumen, Suche und Files. Gedächtnis und Werkzeugfreigaben bleiben unabhängig. Die Stimme wählst du separat.'), 'settingsDescription'))
        voice = QPushButton(tr('Stimme & Vorlesen').replace('&', '&&')); voice.setAutoDefault(False); voice.setObjectName('quiet')
        voice.clicked.connect(voice_callback); root.addWidget(voice, 0, Qt.AlignLeft)
        self.apply = QPushButton(tr('Persönlichkeit übernehmen')); self.apply.setAutoDefault(False)
        self.apply.clicked.connect(self.commit); outer.addWidget(self.apply, 0, Qt.AlignLeft)
        self.set_values(self.initial)
        self.preset.activated.connect(self.choose_preset)
        self.override.toggled.connect(self.scope_changed);self.scope_changed()

    def scope_changed(self):
        local=not self.connection or self.override.isChecked()
        self.local_panel.setVisible(local)
        self.apply.setText(tr('Lokale Persönlichkeit übernehmen') if self.connection and local else tr('Kontovorgabe verwenden') if self.connection else tr('Persönlichkeit übernehmen'))

    def open_account(self):
        from lumen_connect import read_config
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        try:
            if read_config()!=self.connection:raise ValueError(tr('Die Serververbindung wurde geändert. Bitte erneut öffnen.'))
            if not QDesktopServices.openUrl(QUrl(self.connection['server']+'/?app=settings&section=persona')):
                raise ValueError(tr('Die Konto-Persona konnte nicht geöffnet werden.'))
        except (OSError,ValueError) as error:QMessageBox.warning(self,tr('Persona'),str(error))

    def value(self):
        result = dict(preset=self.preset.currentData())
        for key, item in self.fields.items():
            result[key] = item.text() if isinstance(item, QLineEdit) else item.currentData()
        return normalize(result)

    def set_values(self, value):
        self.preset.setCurrentIndex(self.preset.findData(value['preset']))
        for key, item in self.fields.items():
            item.blockSignals(True)
            if isinstance(item, QLineEdit): item.setText(value[key])
            else: item.setCurrentIndex(item.findData(value[key]))
            item.blockSignals(False)
        self.refresh()

    def choose_preset(self, _index):
        value = self.value(); value.update(PRESETS[value['preset']][2])
        self.set_values(value)

    def refresh(self):
        value = self.value()
        self.description.setText(tr(PRESETS[value['preset']][1]))
        self.example.setText(preview(value))
        parts = [value['name']]
        for key, (title, options) in FIELDS.items():
            caption = next(caption for identity, caption in options if identity == value[key])
            parts.append(tr(title) + ': ' + tr(caption))
        self.summary.setText(' · '.join(parts))

    def commit(self):
        from lumen_preferences import save_preferences
        import json
        try:
            from lumen_connect import read_config
            try:current=read_config()
            except FileNotFoundError:current=None
            if current!=self.connection:raise ValueError(tr('Die Serververbindung wurde geändert. Bitte erneut öffnen.'))
            values={'personaLocalOverride':self.override.isChecked()}
            expected={'personaLocalOverride':self.original_override}
            if not self.connection or self.override.isChecked():
                values['personaProfile']=json.dumps(self.value(),ensure_ascii=False);expected['personaProfile']=self.original
            save_preferences(self.settings,
                values,expected)
        except (ValueError, OSError) as exc:
            self.description.setText(str(exc));self.source.setText(str(exc));return
        self.original = self.settings.value('personaProfile', '')
        self.original_override=self.settings.value('personaLocalOverride',False,type=bool)
        self.saved.emit()
