import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from tools_ui import ToolWindow
from tools_data import Library
from interop_data import Registry
from context_translate import open_translation, TranslationDialog


class ContextTranslationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_preparation_keeps_source_and_needs_explicit_provider_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = ToolWindow('reader', 'Test', '', '', root)
            identity = source.library.create('Document', notes=['Keep me'])
            original = source.library.get(identity)
            ref = dict(app='reader', kind='record', id=identity, title='Document', position=dict(page=3))
            payload = dict(title='Passage', text='Grüezi 🌍', paths=[], source=ref,
                           source_url=Registry(root).register(ref))
            inspected = []
            def inspect(dialog):
                view = dialog.view; inspected.append(view.current)
                self.assertEqual(view.input.toPlainText(), payload['text']); self.assertIsNone(view.engine)
                self.assertEqual(view.library.get(view.current)['interop_sources'], [payload['source_url']])
                backend = Mock(); backend.busy = False; view.engine = backend
                view.run_translation(); self.assertEqual(backend.send.call_count, 1)
                view.batch_done(True, json.dumps(dict(segments=[dict(id='0',parts=['Hello 🌍'])])))
                self.assertEqual(view.output.toPlainText(), 'Hello 🌍')
                self.assertEqual(source.library.get(identity), original)
                dialog.reject(); backend.shutdown.assert_called_once()
                return 0
            with patch.object(TranslationDialog,'exec',inspect):
                open_translation(source,payload)
                deadline = time.monotonic()+5
                while source.job and time.monotonic()<deadline: QTest.qWait(25)
            self.assertIsNone(source.job); self.assertEqual(len(inspected),1)
            self.assertEqual(Library('translate',root).get(inspected[0])['result'],'Hello 🌍')
            source.close()

    def test_empty_or_oversized_text_does_not_create_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = ToolWindow('reader','Test','','',Path(tmp))
            for text in ('', 'x'*12001):
                with self.assertRaises(ValueError): open_translation(source,dict(text=text))
            self.assertIsNone(source.job); source.close()
