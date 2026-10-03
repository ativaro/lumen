"""Locale resolution, catalogs and user-content preservation."""
import ast
import collections
import json
import os
from pathlib import Path
import string
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import lumen_i18n as i18n

ROOT = Path(__file__).resolve().parents[1]


def placeholders(text):
    fields = collections.Counter()
    for literal, field, spec, conversion in string.Formatter().parse(text):
        if field is not None:
            fields[(field, conversion, spec)] += 1
    return fields


class LocalizationTest(unittest.TestCase):
    def tearDown(self):
        i18n.language.cache_clear(); i18n.catalog.cache_clear()

    def test_language_override_settings_and_system_fallback(self):
        for override, saved, system, expected in [
            ('en', 'de', 'de_CH', 'en'), ('de', 'en', 'en_GB', 'de'),
            ('', 'en', 'de_CH', 'en'), ('', 'de', 'en_GB', 'de'),
            ('', 'system', 'de_CH', 'de'), ('', 'system', 'en_GB', 'en'),
            ('', 'system', 'fr_CH', 'en'), ('invalid', 'en', 'de_CH', 'en')]:
            with self.subTest(override=override, saved=saved, system=system):
                i18n.language.cache_clear()
                with patch.dict(os.environ, {'LUMEN_LANGUAGE': override}), patch.object(i18n, 'saved_language', return_value=saved), patch.object(i18n, 'system_language', return_value=system[:2] if system[:2] == 'de' else 'en'):
                    self.assertEqual(i18n.language(), expected)

    def test_worker_without_qt_reads_shared_preference_and_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'Lumen' / 'Assistant.conf'
            config.parent.mkdir()
            script = '''
import importlib.abc, sys
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'PyQt5' or fullname.startswith('PyQt5.'):
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, NoQt())
from lumen_i18n import language, tr
print(language())
print(tr('Bilder'))
'''
            for saved, override, locale, expected in [
                ('en', '', 'de_CH.UTF-8', 'en\nPictures\n'),
                ('de', '', 'en_US.UTF-8', 'de\nBilder\n'),
                ('en', 'de', 'en_US.UTF-8', 'de\nBilder\n'),
                ('system', '', 'de_CH.UTF-8', 'de\nBilder\n'),
                ('system', '', 'fr_CH.UTF-8', 'en\nPictures\n')]:
                with self.subTest(saved=saved, override=override, locale=locale):
                    config.write_text('[General]\nuiLanguage=' + saved + '\n')
                    env = dict(os.environ, PYTHONPATH=str(ROOT / 'files'),
                               XDG_CONFIG_HOME=tmp, LUMEN_LANGUAGE=override, LC_ALL=locale)
                    result = subprocess.run([sys.executable, '-c', script], env=env,
                                            text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected)

    def test_workers_keep_window_language_without_changing_new_app_environment(self):
        with patch.dict(os.environ, {'LUMEN_LANGUAGE': ''}), patch.object(i18n, 'saved_language', return_value='de') as preference:
            self.assertEqual(i18n.language(), 'de')
            preference.return_value = 'en'
            self.assertEqual(i18n.worker_environment(LUMEN_DATA='/example')['LUMEN_LANGUAGE'], 'de')
            process = i18n.worker_process(None)
            self.assertEqual(process.processEnvironment().value('LUMEN_LANGUAGE'), 'de')
            self.assertEqual(os.environ['LUMEN_LANGUAGE'], '')
            i18n.language.cache_clear()  # A newly launched app sees the changed preference.
            self.assertEqual(i18n.language(), 'en')

    def test_templates_preserve_user_text_and_fall_back_safely(self):
        with patch.object(i18n, 'language', return_value='en'), patch.object(i18n, 'catalog', return_value={
            'Öffne {0}': 'Open {0}', 'Wert {0:.1f}': 'Value {0:.1f}',
            'Hallo {name}': 'Hello {name}', 'Fehler {0}': 'Error {missing}'}):
            self.assertEqual(i18n.tr('Öffne {0}', 'Neue Notiz {private}.md'), 'Open Neue Notiz {private}.md')
            self.assertEqual(i18n.tr('Wert {0:.1f}', 1.25), 'Value 1.2')
            self.assertEqual(i18n.tr('Hallo {name}', name='Änne'), 'Hello Änne')
            self.assertEqual(i18n.tr('Fehler {0}', 'Original'), 'Fehler Original')
            self.assertEqual(i18n.tr('Not yet translated'), 'Not yet translated')
        with patch.object(i18n, 'language', return_value='de'):
            self.assertEqual(i18n.tr('Öffne {0}', 'Datei'), 'Öffne Datei')

    def test_catalogs_have_valid_templates_and_no_conflicts(self):
        templates = set()
        for folder in ('files', 'agent-app'):
            for path in (ROOT/folder).glob('*.py'):
                if path.name.startswith('test_'): continue
                for node in ast.walk(ast.parse(path.read_text())):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == 'tr' and node.args
                            and (len(node.args) > 1 or node.keywords)
                            and isinstance(node.args[0], ast.Constant)):
                        templates.add(node.args[0].value)
        values = {}
        for path in sorted((ROOT/'files/translations/en').glob('*.json')):
            for source, target in json.loads(path.read_text()).items():
                with self.subTest(catalog=path.name, source=source):
                    self.assertIsInstance(target, str); self.assertTrue(target)
                    if source in values: self.assertEqual(values[source], target, 'Conflicting catalog entry')
                    values[source] = target
                    # No-argument messages may contain literal JSON/shell braces.
                    if source in templates:
                        self.assertEqual(placeholders(source), placeholders(target))

    def test_marked_source_messages_have_english_catalog_entries(self):
        values = i18n.catalog(); missing = []; assembled = []
        for folder in ('files', 'agent-app'):
            for path in (ROOT/folder).glob('*.py'):
                if path.name.startswith('test_') or path.name == 'lumen_i18n.py': continue
                for node in ast.walk(ast.parse(path.read_text())):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'tr' or not node.args: continue
                    source = node.args[0]
                    if isinstance(source, ast.JoinedStr): assembled.append(f'{path.name}:{node.lineno}')
                    if isinstance(source, ast.Constant) and isinstance(source.value, str) and source.value not in values:
                        missing.append(f'{path.name}:{node.lineno}: {source.value}')
        self.assertEqual(assembled, [], 'Format translated templates before inserting user text')
        self.assertEqual(missing, [])


if __name__ == '__main__': unittest.main()
