"""Small setup summary backed by the same personality and memory preferences."""
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QFormLayout, QCheckBox
from lumen_i18n import tr
from lumen_memory import Memory, options
from lumen_store import Store
from lumen_persona import PRESETS
from lumen_preferences import save_preferences
from persona_settings import PersonaEditor
from settings_navigation import Details, label


class SetupPreferences(QWidget):
    def __init__(self, settings, voice_callback, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.store = Store()
        self.original_memory = options(self.store)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(16)
        root.addWidget(label(tr('So wird Lumen dich begleiten.'), 'settingsSectionTitle'))
        self.summary = label(''); root.addWidget(self.summary)
        self.details = Details(tr('Persönlichkeit und Gedächtnis anpassen')); root.addWidget(self.details)
        self.persona = PersonaEditor(settings, voice_callback, self)
        self.persona.apply.hide()
        self.memory = QComboBox(); self.memory.setAccessibleName(tr('Gedächtnis'))
        self.memory.addItem(tr('Aus · nichts dauerhaft merken'), (False, False))
        self.memory.addItem(tr('Vorhandene Erinnerungen verwenden'), (True, False))
        self.memory.addItem(tr('Mich kennenlernen und daraus lernen'), (True, True))
        before = self.original_memory
        self.memory.setCurrentIndex(2 if before['enabled'] and before['learn'] else 1 if before['enabled'] else 0)
        self.initial_memory_index = self.memory.currentIndex()
        form = QFormLayout(); form.addRow(tr('Gedächtnis'), self.memory); self.details.content.addLayout(form)
        self.solutions = QCheckBox(tr('Bestätigte Lösungen wiederverwenden'))
        self.automatic = QCheckBox(tr('Gelernte Erinnerungen automatisch übernehmen'))
        for control, key in ((self.solutions, 'solutions'), (self.automatic, 'automatic')):
            control.setChecked(before[key]); self.details.content.addWidget(control)
        self.details.content.addWidget(label(tr('Lokale Bedeutungssuche: zusätzlich ca. 500 MiB RAM während der Nutzung. Einmalig ca. 128 MB Modelldaten plus Laufzeitpakete. Ohne Modell bleibt die Textsuche verfügbar.')))
        self.details.content.addWidget(label(tr('Erinnerungen liegen lokal in Lumen Wissen. Bei aktivem Gedächtnis '
            'gehen passende Erinnerungen an deinen KI-Anbieter. Beim Lernen wertet dieser auch deine Nachricht '
            'und die vorherige Antwort aus. Du kannst Erinnerungen jederzeit ansehen, ändern und löschen.')))
        self.details.content.addWidget(self.persona)
        self.details.content.addWidget(label(tr('Deine Auswahl wird beim Beenden der Einrichtung übernommen.')))
        self.persona.preset.currentIndexChanged.connect(self.refresh)
        self.memory.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.summary.setText(tr('Persönlichkeit: {0}\nGedächtnis: {1}',
            tr(PRESETS[self.persona.preset.currentData()][0]), self.memory.currentText()))

    def commit(self):
        changed_memory = (self.memory.currentIndex() != self.initial_memory_index
                          or self.solutions.isChecked() != self.original_memory['solutions']
                          or self.automatic.isChecked() != self.original_memory['automatic'])
        # Do not overwrite privacy decisions made in another open Lumen window.
        if changed_memory and options(self.store) != self.original_memory:
            raise ValueError(tr('Das Gedächtnis wurde in einem anderen Fenster geändert. Bitte den Assistenten erneut öffnen.'))
        if self.persona.value() != self.persona.initial:
            save_preferences(self.settings,
                {'personaProfile': json.dumps(self.persona.value(), ensure_ascii=False)},
                {'personaProfile': self.persona.original})
            self.persona.original = self.settings.value('personaProfile', '')
            self.persona.initial = self.persona.value()
        if changed_memory:
            Memory(self.store).configure(*self.memory.currentData(), expected=self.original_memory,
                                        solutions=self.solutions.isChecked(), automatic=self.automatic.isChecked())
            self.original_memory = options(self.store)
            self.initial_memory_index = self.memory.currentIndex()
