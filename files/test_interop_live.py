import tempfile
from pathlib import Path
import unittest
from lumen_store import Store
from wissen_data import Notebook,activate
from tools_data import Library
from tools_ui import Job
from interop_data import Registry
from interop_targets import apply
from interop_live import live_notes

class LiveTest(unittest.TestCase):
    def test_collection_stays_live_and_includes_later_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'state');activate(store);book=Notebook(store)
            book.create_collection('Repairs');first=book.create('First',text='v1',folder='Repairs')
            registry=Registry(root);source=dict(app='wissen',kind='collection',id='collection:folder:Repairs',title='Repairs',locator=dict(root=str(book.root)))
            payload=dict(title='Repairs',text='Old snapshot',paths=[],source=source,source_url=registry.register(source))
            job=Job(lambda _:None);target=apply('workbench.add',payload,dict(token='live',mode='live'),job,root,store)
            library=Library('workbench',root);self.assertEqual(len(live_notes(library,target['id'],job,store)),1)
            book.write(first['path'],'# First\n\nv2',first['hash']);book.create('Second',text='new',folder='Repairs')
            rows=live_notes(library,target['id'],job,store)
            self.assertEqual(len(rows),2);self.assertTrue(any('v2' in row['text'] for row in rows))
            self.assertNotIn('Old snapshot',library.get(target['id'])['notes'])
    def test_household_folder_link_does_not_copy_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'docs';folder.mkdir();(folder/'receipt.txt').write_text('receipt')
            source=dict(app='files',kind='file',id=str(folder),path=str(folder),title='Docs')
            payload=dict(title='Docs',paths=[str(folder)],source=source,source_url=Registry(tmp).register(source))
            result=apply('household.add',payload,dict(token='folder',mode='link'),Job(lambda _:None),tmp)
            library=Library('household',tmp);record=library.get(result['id'])
            self.assertEqual(record['linked_paths'][0]['path'],str(folder));self.assertEqual(record['attachments'],[])
if __name__=='__main__':unittest.main()
