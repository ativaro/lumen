"""Native personality editor with local, illustrative preview."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QPushButton
from lumen_i18n import tr
from lumen_persona import PRESETS, FIELDS, load, normalize, preview
from settings_navigation import Details, label


class PersonaEditor(QWidget):
    saved = Signal()

    def __init__(self, settings, voice_callback, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.initial = load(settings)
        self.original = settings.value('personaProfile', '')
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(14)
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
        self.apply.clicked.connect(self.commit); root.addWidget(self.apply, 0, Qt.AlignLeft)
        self.set_values(self.initial)
        self.preset.activated.connect(self.choose_preset)

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
            save_preferences(self.settings,
                {'personaProfile': json.dumps(self.value(), ensure_ascii=False)},
                {'personaProfile': self.original})
        except (ValueError, OSError) as exc:
            self.description.setText(str(exc)); return
        self.original = self.settings.value('personaProfile', '')
        self.saved.emit()
