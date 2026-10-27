import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

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
    def request(self,method,path,callback,**kwargs):callback({})


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
            with patch('memory_bridge.Store', return_value=store), patch.dict('sys.modules', {'assistant_backend': SimpleNamespace(OpenCodeBackend=Engine)}), patch('memory_bridge.prepare_engine',return_value={}), patch('memory_bridge.tr', side_effect=lambda text,*args: text.format(*args)):
                backend = Backend()
                bridge = MemoryBridge(backend)
                messages = []
                backend.memoryStatus.connect(messages.append)
                prepared = dict(stamp=stamp(store), revision=store.setting('memory/revision',0), candidates=[])
                for success, result, expected in (
                    (True, '[]', 'Geprüft · keine neue Erinnerung übernommen'),
                    (True, '{}', 'Lernen zuletzt nicht möglich'),
                    (False, '', 'Lernen zuletzt nicht möglich'),
                    (True, '[{}]', '1 Erinnerungen gespeichert'),
                ):
                    bridge.job = lambda action, done, failed, **kwargs: done(1)
                    bridge.learn('Synthetic',tmp,'Test',prepared)
                    self.assertEqual(messages[-1],'Lumen prüft deine Aussage …')
                    (Path(bridge.learner.learning_temporary.name)/'result.json').write_text(result)
                    bridge.learner.completed.emit(success,result)
                    self.assertIn(expected,messages[-1])
                bridge.shutdown()

    def test_paired_learning_reports_receipt_not_local_success_or_retries(self):
        from uuid import uuid4
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);Memory(store).configure(True,True)
            with patch('memory_bridge.Store',return_value=store),patch('memory_bridge.tr',side_effect=lambda text,*args:text.format(*args)),patch('memory_bridge.QTimer.singleShot') as timer:
                backend=Backend();bridge=MemoryBridge(backend);messages=[];calls=[]
                backend.memoryStatus.connect(messages.append)
                task_id=str(uuid4());event_id='msg_'+uuid4().hex
                prepared=dict(stamp=stamp(store),revision=-1,candidates=[],remote=dict(connection='synthetic'))
                results=[dict(task_id=task_id,state='queued',saved=0,pending=0),dict(task_id=task_id,state='completed',saved=0,pending=1)]
                def job(action,done,failed,**values):calls.append((action,values));done(results.pop(0))
                bridge.job=job
                bridge.learn('New statement',tmp,'Test',prepared,event_id=event_id)
                self.assertEqual(calls[0][0],'learn_account');self.assertIsNone(bridge.learner)
                self.assertIn('prüft',messages[-1]);self.assertIn(event_id,bridge.account_events)
                timer.call_args.args[1]()
                self.assertEqual(calls[1][0],'account_learning_status');self.assertIn('1 Gedächtnisvorschläge warten',messages[-1])
                self.assertNotIn(event_id,bridge.account_events)
                bridge.job=lambda action,done,failed,**values:failed('Disconnected')
                bridge.learn('New statement',tmp,'Test',prepared,event_id=event_id)
                self.assertIn('nichts automatisch wiederholt',messages[-1]);self.assertEqual(timer.call_count,1)
                bridge.shutdown()


if __name__ == '__main__': unittest.main()
