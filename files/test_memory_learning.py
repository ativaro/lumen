import os
import tempfile
import unittest
from unittest.mock import patch
from memory_learning import previous_answer, extraction_prompt
from lumen_store import Store
from lumen_memory import Memory, options

class LearningContextTest(unittest.TestCase):
    def test_only_complete_preceding_answer(self):
        message = dict(info=dict(id='answer-1',role='assistant',time=dict(completed=1)), parts=[dict(type='text',text='再接続しました。')])
        self.assertEqual(previous_answer([message]),dict(id='answer-1',answer='再接続しました。'))
        self.assertFalse(previous_answer([message,dict(message,info=dict(role='assistant',error={'name':'failed'}))]))
        self.assertFalse(previous_answer([dict(message,info=dict(role='assistant'))]))
        self.assertNotIn('秘密',str(previous_answer([dict(message,parts=message['parts']+[dict(type='tool',state=dict(output='秘密'))])])))

    def test_prompt_preserves_any_language_and_delegates_semantics(self):
        for text in ('今後は短く。','من الآن فصاعداً باختصار','以后简短回答','Bitte künftig ohne Tabellen','En adelante, sé breve'):
            prompt=extraction_prompt(text,[],{})
            self.assertIn(text,prompt);self.assertIn('ANY language',prompt)
            self.assertIn('not rely on keywords',prompt)


class LearningStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory())
        self.store=Store(self.tmp);self.memory=Memory(self.store);self.memory.configure(True,True)

    def apply(self,items,text,context=None):
        prepared=self.memory.prepare(text,self.tmp)
        return self.memory.apply(items,text,self.tmp,'Conversation',prepared['candidates'],prepared['revision'],context)

    def test_short_unicode_evidence_and_correction_replaces_automatic_preference(self):
        initial=dict(title='长度',text='详细',evidence='详细',kind='preference',scope='global')
        self.assertEqual(self.apply([initial],'详细'),1)
        note=self.memory.scan()['notes'][0]
        corrected=dict(initial,path=note['path'],text='简短',evidence='简短',correction=True)
        self.assertEqual(self.apply([corrected],'简短'),1)
        current=self.memory.scan()['notes']
        self.assertEqual(len(current),1);self.assertTrue(current[0]['memory']['correction'])
        recall=self.memory.prepare('无关问题',self.tmp)['context']
        self.assertIn('简短',recall);self.assertNotIn('详细',recall)
        edited=self.memory.write(current[0]['path'],'# 长度\n手动',current[0]['hash'])
        self.assertEqual(self.apply([corrected],'简短'),0)
        self.memory.forget(edited['path'],edited['hash'])
        self.assertEqual(self.apply([corrected],'简短'),0)

    def test_solution_requires_llm_confirmation_evidence_and_matching_answer(self):
        item=dict(title='连接',text='重新连接共享。',evidence='好了',kind='solution',scope='project',confirmed=True,source_answer='answer-1')
        context=dict(id='answer-1',answer='重新连接共享。')
        self.assertEqual(self.apply([item],'好了'),0)
        self.assertEqual(self.apply([dict(item,confirmed=False)],'好了',context),0)
        self.assertEqual(self.apply([dict(item,source_answer='other')],'好了',context),0)
        self.assertEqual(self.apply([item],'还没有',context),0)
        self.assertEqual(self.apply([item],'好了',context),1)
        note=self.memory.scan()['notes'][0];self.assertEqual(note['memory']['verification'],'user')
        self.assertIn('重新连接',self.memory.prepare('连接',self.tmp)['context'])
        self.assertNotIn('重新连接',self.memory.prepare('连接','/unrelated')['context'])
        changed=self.memory.write(note['path'],'# 连接\n新步骤',note['hash'])
        self.assertEqual(changed['memory']['verification'],'')

class LearningBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def test_every_language_reaches_model_without_keyword_gate(self):
        from assistant_backend import OpenCodeBackend
        from memory_bridge import MemoryBridge
        from lumen_memory import stamp
        from PySide6.QtCore import QCoreApplication,QEvent
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp}):
            store=Store();memory=Memory(store);memory.configure(True,True)
            backend=OpenCodeBackend(tmp);bridge=MemoryBridge(backend)
            prepared=dict(revision=store.setting('memory/revision',0),stamp=stamp(store),candidates=[])
            try:
                with patch.object(bridge,'next'):
                    for text in ('好','نعم','угу','今後は短く。'):
                        bridge.learn(text,tmp,'Conversation',prepared)
                    self.assertEqual([item['text'] for item in bridge.queue],['好','نعم','угу','今後は短く。'])
                    bridge.queue.clear();memory.configure(True,False)
                    bridge.learn('Anything',tmp,'Conversation',prepared)
                    self.assertFalse(bridge.queue)
            finally:
                bridge.shutdown();backend.shutdown();backend.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_native_profile_links_to_same_editable_memory_and_filters(self):
        from tools_wissen import Wissen
        from wissen_data import activate
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QCoreApplication,QEvent,Qt
        from PySide6.QtWidgets import QPushButton
        from pathlib import Path
        def wait(window):
            for _ in range(300):
                QTest.qWait(20)
                if not window.job and not window.poller:return
            self.fail(window.status.text())
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            store=Store();activate(store);memory=Memory(store);memory.configure(True,True)
            preference=memory.remember('Antwortstil','Kurze Antworten.',kind='preference')
            private=memory.remember('Projektintern','Nur im Projekt.',kind='fact',scope=tmp+'/project')
            window=Wissen(Path(tmp)/'tools');window.show();wait(window)
            try:
                window.switch_area('lumen');wait(window)
                self.assertEqual(window.tabs.currentIndex(),3)
                buttons=window.profile.findChildren(QPushButton,'memoryProfileEntry')
                self.assertEqual([b.accessibleName() for b in buttons],['Antwortstil'])
                self.assertTrue(window.use_memory.isVisible())
                window.learn_memory.setChecked(False);wait(window)
                self.assertFalse(store.setting('memory/options')['learn'])
                buttons[0].click();wait(window)
                self.assertEqual(window.doc['path'],preference['path'])
                self.assertEqual(window.tabs.currentIndex(),0)
                self.assertEqual(window.doc['memory']['kind'],'preference')
                window.editor.appendPlainText('Manuell ergänzt.');window.save_note();wait(window)
                self.assertIn('Manuell ergänzt',memory.book.read(preference['path'])['text'])
                window.set_collection('corrections:all');wait(window);self.assertEqual(window.entries.count(),0)
                window.set_collection('profile:global');wait(window);self.assertEqual(window.entries.count(),1)
            finally:
                window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_clearing_a_conversation_clears_answer_context(self):
        from assistant_backend import OpenCodeBackend
        from PySide6.QtCore import QCoreApplication,QEvent
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp}):
            backend=OpenCodeBackend(tmp)
            try:
                backend.memory_previous_answer=dict(id='old',answer='Old answer')
                self.assertTrue(backend.new_conversation())
                self.assertEqual(backend.memory_previous_answer,{})
            finally:
                backend.shutdown();backend.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

class MemoryReviewTest(unittest.TestCase):
    def test_review_mode_manual_edits_and_solution_optout(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);memory=Memory(store);memory.configure(True,True,automatic=False,solutions=False)
            item=dict(title='回答',text='短く答える。',evidence='短く',kind='preference',scope='global')
            revision=store.setting('memory/revision',0)
            self.assertEqual(memory.apply([item],'短く',temp,'Conversation',[],revision),1)
            self.assertEqual(memory.scan()['notes'],[])
            pending=memory.proposals();self.assertEqual(len(pending),1)
            memory.review(pending[0]['id'],True)
            note=memory.scan()['notes'][0];self.assertTrue(note['memory']['automatic'])
            self.assertEqual(memory.proposals(),[])
            solution=memory.remember('Solution','Do something',kind='solution')
            self.assertNotIn(solution['id'],[n['id'] for n in memory.eligible(temp)])
            memory.configure(True,True)
            self.assertFalse(options(store)['automatic']);self.assertFalse(options(store)['solutions'])

    def test_review_window_has_exact_evidence_and_native_approval(self):
        from app import create_app
        from PySide6.QtWidgets import QApplication,QPushButton,QPlainTextEdit
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtTest import QTest
        from tools_wissen import Wissen
        from wissen_data import activate
        from lumen_i18n import tr
        import memory_review_ui
        from pathlib import Path
        app=QApplication.instance() or create_app()
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'LUMEN_DATA':temp+'/state'}):
            store=Store();activate(store);memory=Memory(store);memory.configure(True,True,automatic=False)
            item=dict(title='Antwortstil',text='Kurze Antworten.',evidence='Bitte kurz',kind='preference',scope='global')
            memory.apply([item],'Bitte kurz',temp,'Synthetic conversation',[],store.setting('memory/revision',0))
            window=Wissen(Path(temp)/'tools');window.show()
            def wait():
                for _ in range(400):
                    QTest.qWait(20)
                    if not window.job and not window.poller:return
                self.fail('Native memory review timed out')
            try:
                wait();window.switch_area('lumen');wait()
                self.assertFalse(window.auto_memory.isChecked());self.assertTrue(window.reuse_solutions.isChecked())
                memory_review_ui.review(window);wait();dialog=window.memory_review_dialog
                text=dialog.findChild(QPlainTextEdit).toPlainText()
                self.assertIn('Kurze Antworten.',text);self.assertIn('Bitte kurz',text)
                dialog.grab().save('/tmp/lumen-memory-review.png')
                next(b for b in dialog.findChildren(QPushButton) if b.text()==tr('Genau so übernehmen')).click();wait()
                self.assertEqual(len(memory.scan()['notes']),1);self.assertEqual(memory.proposals(),[])
            finally:
                window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

if __name__=='__main__':unittest.main()
