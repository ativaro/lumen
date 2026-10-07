import tempfile
from pathlib import Path
import unittest
from tools_data import Library
from tools_ui import Job
from lumen_store import Store
from wissen_data import Notebook,activate
from interop_targets import apply
from interop_undo import undo

class UndoTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root/'state');activate(self.store)
        self.job=Job(lambda _:None)
        self.payload=dict(title='Incoming',text='Copied text',source_url='lumen://object/'+'a'*32)

    def transfer(self,action,**values):
        choice=dict(token='one',title='Incoming',mode='copy',**values)
        return apply(action,self.payload,choice,self.job,self.root,self.store)

    def test_existing_record_restored_only_without_subsequent_edits(self):
        library=Library('workbench',self.root)
        key=library.create('Project',notes='Original',questions=[],resources=[])
        self.transfer('workbench.add',id=key)
        undo('workbench.add','one',self.job,self.root,self.store)
        self.assertEqual(library.get(key)['notes'],'Original')
        undo('workbench.add','one',self.job,self.root,self.store)
        self.assertEqual(library.get(key)['notes'],'Original')

    def test_new_record_archived_and_copied_assets_preserved(self):
        source=self.root/'source.txt';source.write_text('source stays')
        self.payload['paths']=[str(source)]
        result=self.transfer('household.add')
        undo('household.add','one',self.job,self.root,self.store)
        record=Library('household',self.root).get(result['id'])
        self.assertTrue(record['_archived']);self.assertEqual(source.read_text(),'source stays')
        self.assertTrue(Library('household',self.root).asset(record['attachments'][0]['asset']).exists())

    def test_modified_result_cannot_be_undone(self):
        result=self.transfer('workbench.add')
        library=Library('workbench',self.root);library.update(result['id'],notes='User changes')
        with self.assertRaises(ValueError):undo('workbench.add','one',self.job,self.root,self.store)
        self.assertEqual(library.get(result['id'])['notes'],'User changes')

    def test_saving_default_widget_fields_does_not_block_undo(self):
        result=self.transfer('household.add')
        library=Library('household',self.root)
        library.update(result['id'],provider='',model='',serial='',since='',until='',remind='')
        undo('household.add','one',self.job,self.root,self.store)
        self.assertTrue(library.get(result['id'])['_archived'])

    def test_wissen_undo_preserves_recoverable_history(self):
        result=self.transfer('wissen.import')
        undo('wissen.import','one',self.job,self.root,self.store)
        book=Notebook(self.store)
        self.assertFalse((book.root/result['id']).exists());self.assertEqual(len(book.versions(result['id'])),1)

    def test_local_task_removed_without_affecting_other_tasks(self):
        result=self.transfer('inbox.task')
        undo('inbox.task','one',self.job,self.root,self.store)
        with Library('inbox',self.root).connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0],0)

if __name__=='__main__':unittest.main()
