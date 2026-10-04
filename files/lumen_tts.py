"""Shared choice of local speech output for conversations, Reader and Radio."""
from pathlib import Path
import re

from lumen_i18n import tr
import lumen_setup as setup

SPEAKERS = ('Ryan', 'Aiden', 'Serena', 'Vivian', 'Uncle_Fu', 'Dylan', 'Eric', 'Ono_Anna', 'Sohee')


def preferences(settings=None):
    if settings is None:
        from lumen_qt import QSettings
        settings = QSettings('Lumen', 'Assistant')
    settings.sync()
    return settings


def engine(settings=None):
    return 'qwen' if preferences(settings).value('speechEngine', 'piper') == 'qwen' else 'piper'


def speaker(settings=None):
    value = preferences(settings).value('speechSpeaker', 'Ryan')
    return value if value in SPEAKERS else 'Ryan'


def available(settings=None):
    root = setup.speech_root()
    if engine(settings) == 'qwen':
        return (root/'qwen-env/bin/python').is_file() and (root/'qwen-0.6b/.ready').is_file()
    return bool(setup.executable('piper-tts') and (root/'de_DE-thorsten-medium.onnx').is_file())


def command(output, directory=False, settings=None):
    if engine(settings) == 'qwen':
        return [str(setup.speech_root()/'qwen-env/bin/python'), str(Path(__file__).with_name('speech_worker.py')),
                '--speaker', speaker(settings), '--output-dir' if directory else '--output', str(output)]
    return [setup.executable('piper-tts'), '-m', str(setup.speech_root()/'de_DE-thorsten-medium.onnx'),
            '--output-dir' if directory else '-f', str(output)]


def prepare_text(text):
    # Only spoken text changes; preserve line boundaries used by Radio's timeline.
    text = re.sub(r'(?<![\w~])~(?=/)', 'Benutzerordner', text)
    return re.sub(r'(?<![\w~])~(?![\w~])', 'Tilde', text)


def add_voice_fields(form, settings):
    from PySide6.QtWidgets import QComboBox
    voices = QComboBox(); voices.setAccessibleName(tr('Sprachausgabe'))
    voices.addItem(tr('Deutsch · Thorsten · sparsam'), 'piper')
    voices.addItem(tr('Mehrsprachig · Deutsch und Englisch gemischt'), 'qwen')
    voices.setCurrentIndex(max(0, voices.findData(engine(settings))))
    voices.setToolTip(tr('Die mehrsprachige Stimme verarbeitet auch neue englische Wörter im Satz. '
        'Benötigt die zusätzliche Einrichtung und mehr Rechenleistung; die Stimme klingt anders.'))
    timbre = QComboBox(); timbre.setAccessibleName(tr('Mehrsprachige Stimme'))
    timbre.addItems(SPEAKERS); timbre.setCurrentText(speaker(settings))
    timbre.setEnabled(voices.currentData() == 'qwen')
    voices.currentIndexChanged.connect(lambda: timbre.setEnabled(voices.currentData() == 'qwen'))
    form.addRow(tr('Sprachausgabe'), voices); form.addRow(tr('Mehrsprachige Stimme'), timbre)
    def save():
        settings.setValue('speechEngine', voices.currentData())
        settings.setValue('speechSpeaker', timbre.currentText()); settings.sync()
    return save
