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


if __name__=='__main__':unittest.main()
