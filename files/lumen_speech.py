"""One recognition configuration for dictation, microphone tests and voice turns."""
import os

LANGUAGES = [('Deutsch', 'de'), ('Automatisch erkennen', 'auto'), ('Englisch', 'en'),
             ('Französisch', 'fr'), ('Italienisch', 'it'), ('Spanisch', 'es')]
VOCABULARY = 'Lumen, Lumen Files, OpenCode, Ollama, NAS, SMB, SFTP, WebDAV'


def transcription_arguments(settings, audio, output, model=None):
    settings.sync()
    language = settings.value('speechLanguage', 'de')
    if language not in [code for _label, code in LANGUAGES]: language = 'de'
    words = ' '.join(str(settings.value('speechVocabulary', VOCABULARY)).split())[:500]
    arguments = ['-m', str(model or settings.value('speechModel', '')), '-f', str(audio),
                 '-l', language, '-t', str(min(8, os.cpu_count() or 1)), '-nt', '-otxt', '-of', str(output)]
    if words: arguments += ['--prompt', words]
    if not settings.value('speechUseGPU', True, type=bool): arguments += ['-ng']
    return arguments


def add_recognition_fields(form, settings):
    """Return an explicit save action; merely opening settings changes nothing."""
    from PyQt5.QtWidgets import QCheckBox, QComboBox, QLineEdit
    language = QComboBox(); language.setAccessibleName('Erkennungssprache')
    for label, code in LANGUAGES: language.addItem(label, code)
    language.setCurrentIndex(max(0, language.findData(settings.value('speechLanguage', 'de'))))
    language.setToolTip('Eine feste Sprache hilft bei kurzen Sätzen. Deutsch gilt auch für Schweizerdeutsch; englische Fachbegriffe bleiben möglich.')
    words = QLineEdit(str(settings.value('speechVocabulary', VOCABULARY))); words.setMaxLength(500)
    words.setAccessibleName('Namen und Fachbegriffe'); words.setPlaceholderText('Eigene Namen und Begriffe, mit Komma getrennt')
    words.setToolTip('Schreibweisen als Erkennungshilfe, keine automatischen Textersetzungen. Bei falschen Ergänzungen die Liste kürzen oder leeren.')
    form.addRow('Erkennungssprache', language); form.addRow('Namen und Fachbegriffe', words)
    gpu = QCheckBox('GPU nutzen, falls verfügbar'); gpu.setChecked(settings.value('speechUseGPU', True, type=bool))
    gpu.setToolTip('Ohne GPU-Unterstützung wird der Prozessor verwendet. Ausschalten erzwingt die CPU.'); form.addRow('', gpu)
    def save():
        settings.setValue('speechLanguage', language.currentData())
        settings.setValue('speechVocabulary', words.text().strip()); settings.setValue('speechUseGPU', gpu.isChecked()); settings.sync()
    return save
