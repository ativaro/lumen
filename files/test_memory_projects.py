import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from lumen_memory import Memory, stamp
from lumen_store import Store
from tools_data import Library


class ProjectMemoryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {'LUMEN_TOOLS_DATA': str(self.root/'tools'),
                                     'LUMEN_MEMORY_HOME': str(self.root/'no-model')})
        env.start(); self.addCleanup(env.stop)
        self.memory = Memory(Store(self.root/'state'))
        self.memory.configure(True, True)
        self.library = Library('workbench')
        self.project = str(UUID(self.library.create('Example project')))
        self.folder = self.root/'project'; self.folder.mkdir()

    def bind(self, directory=None, **values):
        return self.memory.project_configure(project=self.project, directory=str(directory or self.folder),
                    expected=self.memory.store.setting('memory/project-folders', {}), **values)

    def test_identity_folder_move_copy_consent_archive_and_personal_sync_boundary(self):
        original = self.memory.remember('Choice', 'Use SQLite', scope=str(self.folder))
        self.bind()
        self.assertEqual(self.memory.scan()['notes'][0]['memory']['scope'], str(self.folder))
        copy = self.bind(path=original['path'], revision=original['hash'])['copied']
        self.assertNotEqual(original['id'], copy['id'])
        self.assertEqual(original['text'], copy['text'])
        self.assertEqual(copy['memory']['scope'], 'project:'+self.project)
        self.assertFalse(copy['memory']['allowed'])
        self.assertEqual(copy['memory']['copied_from']['id'], original['id'])
        self.assertNotIn(copy['id'], [n['id'] for n in self.memory.eligible(str(self.folder))])
        self.memory.allow(copy['path'], copy['hash'], True)
        renamed = self.root/'moved'; self.folder.rename(renamed)
        self.assertEqual(self.memory.eligible(str(renamed)), [])
        self.bind(renamed)
        self.assertEqual([n['id'] for n in self.memory.eligible(str(renamed))], [copy['id']])
        self.assertEqual(self.memory.eligible(str(self.root)), [])
        from memory_sync import payload
        with self.assertRaises(ValueError):
            payload(copy, 0)
        before = stamp(self.memory.store)
        self.library.archive(UUID(self.project).hex)
        self.assertNotEqual(before, stamp(self.memory.store))
        self.assertEqual(self.memory.eligible(str(renamed)), [])
        item = dict(title='Late result', text='SQLite', evidence='SQLite', kind='decision', scope='project')
        self.assertEqual(self.memory.apply([item], 'SQLite', str(renamed), 'Delayed conversation', [],
            self.memory.store.setting('memory/revision', 0), prepared_stamp=before), 0)

    def test_learning_uses_same_uuid_and_pending_proposal_cannot_change_projects(self):
        self.bind()
        item = dict(title='Storage', text='SQLite', evidence='SQLite', kind='decision', scope='project')
        def learn(items, candidates=[]):
            return self.memory.apply(items, 'SQLite', str(self.folder), 'Conversation', candidates,
                                     self.memory.store.setting('memory/revision', 0))
        self.assertEqual(learn([item]), 1)
        first = self.memory.scan()['notes'][0]
        self.assertEqual(first['memory']['scope'], 'project:'+self.project)
        self.assertEqual(learn([item]), 0)
        self.memory.configure(True, True, automatic=False)
        self.assertEqual(learn([dict(item, title='Other choice', text='Use SQLite')]), 1)
        pending = self.memory.proposals()[0]
        self.assertEqual(pending['directory'], 'project:'+self.project)
        self.memory.project_configure(project=self.project, directory='', expected=self.memory.project_info()['folders'])
        with self.assertRaises(ValueError):
            self.memory.review(pending['id'], True)
        self.assertEqual(len(self.memory.scan()['notes']), 1)

    def test_stale_choice_overlap_and_symlink_escape_are_rejected(self):
        before = self.memory.project_info()['folders']
        self.bind()
        original_is_dir = Path.is_dir
        def no_nas_stat(path):
            self.assertFalse(path.is_relative_to(self.folder), 'NAS I/O on UI stamp')
            return original_is_dir(path)
        with patch.object(Path, 'is_dir', no_nas_stat), \
                patch.object(Path, 'resolve', side_effect=AssertionError('NAS I/O on UI stamp')):
            self.assertTrue(stamp(self.memory.store)[-1])
        with self.assertRaises(ValueError):
            self.memory.project_configure(project=self.project, directory='', expected=before)
        child = self.folder/'child'; child.mkdir()
        other = str(UUID(self.library.create('Another project')))
        with self.assertRaises(ValueError):
            self.memory.project_configure(project=other, directory=str(child), expected=self.memory.project_info()['folders'])
        memory = self.memory.remember('Private', 'Internal detail', scope=str(self.folder))
        outside = self.root/'outside'; outside.mkdir()
        (self.folder/'link').symlink_to(outside)
        self.assertEqual(self.memory.eligible(str(self.folder/'link')), [])
        self.folder.rename(self.root/'original')
        self.folder.symlink_to(outside)
        self.assertEqual(self.memory.eligible(str(self.folder)), [])
        self.assertEqual(self.memory.book.read(memory['path'])['hash'], memory['hash'])

    def test_interrupted_copy_is_never_global_or_approved(self):
        original = self.memory.remember('Personal', 'Private preference')
        save = self.memory.store.set_setting
        def fail(key, value):
            if key == 'memory/project-folders':
                raise OSError('simulated interruption after file creation')
            return save(key, value)
        with patch.object(self.memory.store, 'set_setting', side_effect=fail):
            with self.assertRaises(OSError):
                self.bind(path=original['path'], revision=original['hash'])
        copies = [n for n in self.memory.scan()['notes'] if n['id'] != original['id']]
        self.assertEqual(len(copies), 1)
        self.assertFalse(copies[0]['memory']['allowed'])
        self.assertTrue(copies[0]['memory']['scope'].startswith('project:'))
        self.assertEqual([n['id'] for n in self.memory.eligible(str(self.folder))], [original['id']])

    def test_native_project_choice_copy_and_explicit_consent(self):
        from app import create_app
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit, QPushButton, QMessageBox
        from PySide6.QtTest import QTest
        from lumen_i18n import tr
        from tools_wissen import Wissen
        from wissen_data import activate
        import memory_projects_ui as ui
        self.qt_app = QApplication.instance() or create_app()
        def wait(window):
            for _ in range(400):
                QTest.qWait(20)
                if not window.job and not window.poller:
                    return
            self.fail(window.status.text())
        errors = []
        with patch.dict(os.environ, {'LUMEN_DATA': str(self.root/'state')}), \
                patch.object(QMessageBox, 'warning', side_effect=lambda *args: errors.append(args[-1])):
            activate(self.memory.store)
            original = self.memory.remember('Synthetic choice', 'Use SQLite for this project')
            window = Wissen(self.root/'tools'); window.show(); wait(window)
            try:
                window.switch_area('lumen'); wait(window)
                window.open_profile_note(original['path']); wait(window)
                menu = window.more_button.menu(); menu.aboutToShow.emit()
                action = next(a for a in menu.actions() if a.text() == tr('Als Projektwissen kopieren …'))
                self.assertTrue(action.isVisible()); action.trigger(); wait(window)
                self.assertFalse(errors, errors)
                dialog = window.memory_projects_dialog
                self.assertTrue(dialog.isVisible())
                self.assertFalse(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).isEnabled())
                with patch.object(ui.QFileDialog, 'getExistingDirectory', return_value=str(self.folder)):
                    next(b for b in dialog.findChildren(QPushButton) if b.text() == tr('Wählen …')).click()
                self.assertEqual(dialog.findChild(QLineEdit).text(), str(self.folder))
                dialog.grab().save('/tmp/lumen-memory-projects.png')
                dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click(); wait(window)
                self.assertFalse(errors, errors)
                self.assertNotEqual(window.doc['id'], original['id'])
                self.assertFalse(window.share_note.isChecked())
                self.assertIn('Example project', window.source.text())
                self.assertIn(original['id'], [n['id'] for n in self.memory.scan()['notes']])
                copy = next(n for n in self.memory.scan()['notes'] if n['id'] != original['id'])
                self.assertEqual(window.doc['note_id'], copy['id'])
                self.assertNotIn(copy['id'], [n['id'] for n in self.memory.eligible(str(self.folder))])
                window.share_note.setChecked(True); wait(window)
                self.assertIn(copy['id'], [n['id'] for n in self.memory.eligible(str(self.folder))])
            finally:
                window.close(); window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
