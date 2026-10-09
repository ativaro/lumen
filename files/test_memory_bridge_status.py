import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from lumen_store import Store
from lumen_memory import Memory, stamp
from memory_bridge import MemoryBridge


class Backend(QObject):
    memoryStatus = Signal(str)
    url = "http://unused.test"
    password = ""
    selected_model = "synthetic"


class Engine(QObject):
    completed = Signal(bool, str)
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.deadline = SimpleNamespace(start=lambda _: None)
    def send(self, *args, **kwargs): pass
    def shutdown(self): pass


class LearningStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_empty_failed_and_saved_learning_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            Memory(store).configure(True, True)
            with patch('memory_bridge.Store', return_value=store), patch.dict('sys.modules', {'assistant_backend': SimpleNamespace(OpenCodeBackend=Engine)}), patch('memory_bridge.tr', side_effect=lambda text,*args: text.format(*args)):
                backend = Backend()
                bridge = MemoryBridge(backend)
                messages = []
                backend.memoryStatus.connect(messages.append)
                prepared = dict(stamp=stamp(store), revision=store.setting('memory/revision',0), candidates=[])
                for success, result, expected in (
                    (True, '{"memories":[]}', 'Geprüft · keine neue Erinnerung übernommen'),
                    (True, '{}', 'Lernen zuletzt nicht möglich'),
                    (False, '', 'Lernen zuletzt nicht möglich'),
                    (True, json.dumps({'memories':[{}]}), '1 Erinnerungen gespeichert'),
                ):
                    bridge.job = lambda action, done, failed, **kwargs: done(1)
                    bridge.learn('Synthetic',tmp,'Test',prepared)
                    self.assertEqual(messages[-1],'Lumen prüft deine Aussage …')
                    bridge.learner.completed.emit(success,result)
                    self.assertIn(expected,messages[-1])
                bridge.shutdown()


if __name__ == '__main__': unittest.main()
