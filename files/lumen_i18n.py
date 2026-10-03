"""Explicit product translations; documents and machine identifiers never pass here."""
from functools import lru_cache
import configparser
import json
import os
from pathlib import Path


def saved_language():
    # CalDAV runs in an isolated Python environment without Qt. The preference is
    # a plain string in QSettings' Linux INI file, shared with the native apps.
    try:
        from PyQt5.QtCore import QSettings
    except ImportError:
        config = configparser.ConfigParser(interpolation=None)
        root = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
        try:
            config.read(root / 'Lumen' / 'Assistant.conf', encoding='utf-8')
            return config.get('General', 'uiLanguage', fallback='system')
        except (OSError, configparser.Error):
            return 'system'
    return QSettings('Lumen', 'Assistant').value('uiLanguage', 'system')


def system_language():
    try:
        from PyQt5.QtCore import QLocale
    except ImportError:
        locale = next((os.environ[key] for key in ('LC_ALL', 'LC_MESSAGES', 'LANG')
                       if os.environ.get(key)), '')
        return 'de' if locale.lower().split('_')[0].split('.')[0] == 'de' else 'en'
    return 'de' if QLocale.system().language() == QLocale.German else 'en'


@lru_cache(maxsize=1)
def language():
    """Choose once per process; preferences apply on the next application launch."""
    selected = os.environ.get('LUMEN_LANGUAGE')
    if selected not in ('de', 'en'):
        selected = saved_language()
    if selected in ('de', 'en'):
        return selected
    return system_language()


@lru_cache(maxsize=1)
def catalog():
    result = {}
    for path in sorted(Path(__file__).with_name('translations').joinpath('en').glob('*.json')):
        try:
            values = json.loads(path.read_text(encoding='utf-8'))
            result.update({key: value for key, value in values.items()
                           if isinstance(key, str) and isinstance(value, str) and value})
        except (OSError, ValueError, AttributeError):
            # An incomplete installation must still show the original readable text.
            continue
    return result


def tr(source, *args, **values):
    """Translate an authored template, then insert untouched runtime values."""
    translated = catalog().get(source, source) if language() == 'en' else source
    if not args and not values:
        return translated
    try:
        return translated.format(*args, **values)
    except (ValueError, IndexError, KeyError):
        return source.format(*args, **values)


def worker_environment(**values):
    """Keep job output in its window's language without changing the global env."""
    return dict(os.environ, LUMEN_LANGUAGE=language(), **values)


def worker_process(parent):
    from PyQt5.QtCore import QProcess, QProcessEnvironment
    process = QProcess(parent)
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert('LUMEN_LANGUAGE', language())
    process.setProcessEnvironment(environment)
    return process


def install(app):
    """Use the same language for Qt's standard buttons and dialogs."""
    from PyQt5.QtCore import QLibraryInfo, QLocale, QTranslator
    selected = language()
    app.setProperty('lumenLanguage', selected)
    locale = QLocale.system()
    if (locale.language() == QLocale.German) != (selected == 'de'):
        locale = QLocale('de_DE' if selected == 'de' else 'en_US')
    QLocale.setDefault(locale)
    translator = QTranslator(app)
    if selected == 'de':
        translator.load('qtbase_de', QLibraryInfo.location(QLibraryInfo.TranslationsPath))
        app.installTranslator(translator)
    app.translator = translator
