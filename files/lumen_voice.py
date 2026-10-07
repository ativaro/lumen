"""Qt 5 voice controls; the shared session also powers the QML pilot."""
from lumen_i18n import tr
from voice_capture import Utterance, pcm_rms, normalized_level, record
import sys

if __name__ == '__main__':
    try: record(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))
    except Exception as error: print(str(error), file=sys.stderr); sys.exit(1)
else:
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QPushButton, QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QVBoxLayout
    from lumen_voice_ui import VoiceActivity
    from voice_session import VoiceSession

    class VoiceConversation(VoiceSession):
        def __init__(self, panel, row):
            super().__init__(panel.backend, panel.settings, panel); self.panel = panel
            self.indicator = VoiceActivity(panel)
            self.button = QPushButton(tr('Sprechen')); self.button.setIcon(QIcon.fromTheme('audio-input-microphone'))
            self.button.setAccessibleName(tr('Sprachgespräch starten oder beenden')); row.addWidget(self.button)
            self.button.setToolTip(tr('Sprachgespräch: Sprechpausen senden automatisch. Audio bleibt lokal; Text geht an deinen Lumen-Anbieter.'))
            self.button.clicked.connect(self.toggle)
            self.interrupt_button = QPushButton(tr('Unterbrechen')); self.interrupt_button.hide(); row.addWidget(self.interrupt_button)
            self.interrupt_button.clicked.connect(self.interrupt)
            self.changed.connect(self.update_controls); self.levelChanged.connect(self.indicator.set_level)
            self.transcribedText.connect(lambda text: (panel.composer.setPlainText(text), panel.submit(text)))
            self.failed.connect(panel.show_error); self.setupRequested.connect(self.open_setup)
            panel.installEventFilter(self)

        def update_controls(self):
            self.indicator.set_state(self.state); self.panel.status.setText(self.status)
            self.button.setText(tr('Beenden') if self.active else tr('Sprechen')); self.button.setToolTip(self.status)
            self.interrupt_button.setVisible(self.active and self.state in ('thinking', 'preparing', 'speaking'))

        def toggle(self):
            if not self.active and self.panel.context_tools.process: return
            super().toggle()

        def open_setup(self):
            from setup_dialog import open_setup
            open_setup(self.panel, self.panel.settings, page=2)

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Hide and self.active: self.stop()
            return False

        def controls(self):
            dialog = QDialog(self.panel); dialog.setWindowTitle(tr('Sprachgespräch')); layout = QVBoxLayout(dialog); form = QFormLayout(); layout.addLayout(form)
            from lumen_speech import add_recognition_fields
            from lumen_tts import add_voice_fields
            self.panel.settings.sync(); save_recognition = add_recognition_fields(form, self.panel.settings)
            save_voice = add_voice_fields(form, self.panel.settings)
            threshold = QSpinBox(); threshold.setRange(50,15000); threshold.setValue(self.panel.settings.value('voiceThreshold',450,type=int)); form.addRow(tr('Mikrofonschwelle (kleiner = empfindlicher)'), threshold)
            silence = QDoubleSpinBox(); silence.setRange(.3,4); silence.setSingleStep(.1); silence.setValue(self.panel.settings.value('voiceSilence',.9,type=float)); form.addRow(tr('Sprechpause vor dem Senden (Sekunden)'),silence)
            save = QPushButton(tr('Speichern')); layout.addWidget(save)
            def apply():
                self.panel.settings.setValue('voiceThreshold',threshold.value()); self.panel.settings.setValue('voiceSilence',silence.value()); save_recognition(); save_voice(); dialog.accept()
            save.clicked.connect(apply); dialog.exec()
