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



if __name__ == '__main__':
    unittest.main()
