"""Memory publication through the service; its interruptions are tested in native/service/src/recall/tests.rs."""
from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class MemoryPublicationTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.dict(os.environ, {
            'HOME': str(self.root), 'XDG_CONFIG_HOME': str(self.root/'config'),
            'XDG_DATA_HOME': str(self.root/'data'), 'LUMEN_DATA': str(self.root/'state'),
            'LUMEN_TOOLS_DATA': str(self.root/'tools'), 'LUMEN_MEMORY_HOME': str(self.root/'no-model'),
        }))
        from lumen_store import Store
        from lumen_memory import Memory
        self.Memory = Memory; self.store = Store(self.root/'state'); self.memory = Memory(self.store)
        self.memory.configure(True, False)
        self.alpha = self.root/'alpha'; self.beta = self.root/'beta'
        self.alpha.mkdir(); self.beta.mkdir()

    def test_success_preserves_private_grant_and_leaves_no_pending_identity(self):
        original = self.memory.remember('Original', 'Old text', scope=str(self.alpha))
        original = self.memory.allow(original['path'], original['hash'], False)
        saved = self.memory.remember('Updated', 'New text', scope=str(self.alpha),
                                     path=original['path'], expected=original['hash'])
        self.assertFalse(saved['memory']['allowed'])
        created = self.memory.remember('New', 'Completed text', scope=str(self.alpha))
        self.assertTrue(created['memory'].get('allowed', True))
        self.assertEqual(set(self.store.setting('memory/records', {})), {saved['path'], created['path']})
