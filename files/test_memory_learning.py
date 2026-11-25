import os
import tempfile
import unittest
from unittest.mock import patch
from lumen_store import Store
from lumen_memory import Memory, options

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
