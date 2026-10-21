import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidget
from note_tags import add_tag, tags, rename_tag
from lumen_i18n import tr


class DirectTagsTest(unittest.TestCase):
    def test_add_preserves_metadata_body_and_nested_tags(self):
        for text in ['---\ntags:\ncustom: yes\n---\n# Title', '# Title\n\nBody 🌍', '---\ncustom: {keep: true} # yes\ntags: [old/child]\n---\n# Title\nBody', '---\ncustom: yes\n---\n# Title']:
            result = add_tag(text, ' Neu/Idee ')
            self.assertIn('neu/idee', tags(result))
            self.assertTrue(result.endswith(text.split('---\n')[-1]))
            if 'custom:' in text: self.assertIn(next(line for line in text.splitlines() if line.startswith('custom:')), result)
            self.assertEqual(add_tag(result, 'NEU/IDEE'),result)
        self.assertEqual(tags(rename_tag('#parent #parent/child','parent','',descendants=False)),['parent/child'])

    def test_invalid_metadata_is_not_rewritten(self):
        for text in ['---\ntags: [broken\n---\n', '---\nother: &list [old]\ntags: *list\n---\n', '---\ntags: [old]\ntags: [other]\n---\n', '---\nunterminated', '---\n{custom: keep}\n---\n']:
            with self.subTest(text=text), self.assertRaises(ValueError): add_tag(text,'new')


class DirectNotesNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def wait(self, check):
        for _ in range(600):
            QTest.qWait(20)
            if check(): return
        self.fail('Notes operation timed out')
