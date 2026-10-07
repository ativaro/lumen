import tempfile
import unittest
from pathlib import Path
from interop_data import Registry, validate_payload


class ReferencesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = Registry(self.tmp.name)

    def test_stable_identity_positions_and_backlinks(self):
        ref = dict(app='reader', kind='record', id='book', title='Book', position={'page': 3})
        url = self.registry.register(ref)
        moved = self.registry.register(dict(ref, title='New title', position={'page': 9}))
        self.assertEqual(url.split('?')[0], moved.split('?')[0])
        self.assertEqual(self.registry.resolve(url)['position'], {'page': 3})
        self.assertEqual(self.registry.resolve(moved)['title'], 'New title')
        note = self.registry.register(dict(app='wissen', kind='note', id='note.md', title='Note', locator={'root':self.tmp.name}))
        self.registry.link(url,note,'import')
        self.assertEqual(self.registry.related(note)[0]['url'],url)
        self.registry.link(url,note,'import')
        self.assertEqual(len(self.registry.related(note)),1)

    def test_atomic_handoff_claim_replay_and_history(self):
        source = self.registry.register(dict(app='files',kind='file',id='/tmp/report.pdf',path='/tmp/report.pdf',title='Report'))
        token = self.registry.enqueue('reader','reader.import',dict(title='Report',text='',paths=['/tmp/report.pdf'],source_url=source,source=self.registry.resolve(source)))
        request = self.registry.claim(token,'reader')
        self.assertEqual(request['state'],'applying')
        with self.assertRaises(ValueError):self.registry.claim(token,'reader')
        self.registry.release(token,'cancelled')
        self.assertEqual(self.registry.request(token)['state'],'pending')
        self.registry.claim(token,'reader')
        result = self.registry.register(dict(app='reader',kind='record',id='r1',title='Report'))
        self.registry.finish(token, result)
        self.assertEqual(self.registry.request(token)['result'],result)
        with self.assertRaises(ValueError):self.registry.claim(token,'reader')
        self.assertEqual(len(self.registry.history()),1)
        self.assertEqual(self.registry.related(result)[0]['url'],source)

    def test_view_locator_and_interrupted_choice_do_not_change_identity(self):
        ref=dict(app='wissen',kind='note',id='x.md',title='Note',locator=dict(root=self.tmp.name))
        first=self.registry.register(ref)
        self.assertEqual(first,self.registry.register(dict(ref,locator=dict(root=self.tmp.name,area='user'))))
        task=dict(app='inbox',kind='task',id='t',title='Task')
        self.assertEqual(self.registry.register(task),self.registry.register(dict(task,locator={})))
        token=self.registry.enqueue('workbench','workbench.add',dict(title='Text',text='Text'))
        self.registry.save_choice(token,dict(id='existing',mode='link'))
        self.registry.claim(token,'workbench');self.assertEqual(self.registry.recover('workbench'),1)
        self.assertEqual(self.registry.request(token)['choice'],dict(id='existing',mode='link'))

    def test_bad_links_wrong_destination_and_payload_are_rejected(self):
        for url in ['https://evil.invalid', 'lumen://object/../x', 'lumen://object/'+'a'*32+'?page=-1', 'lumen://object/'+'a'*32+'?run=sh']:
            with self.subTest(url=url), self.assertRaises(ValueError):self.registry.resolve(url)
        for payload in [dict(title='x',paths=['relative']),dict(title='x',text='a'*120001),dict(title='x',password='secret')]:
            with self.assertRaises(ValueError):validate_payload(payload)
        token=self.registry.enqueue('reader','reader.import',dict(title='x',text='x'))
        with self.assertRaises(ValueError):self.registry.claim(token,'radio')

    def test_tags_search_and_file_relocation_keep_links(self):
        path=Path(self.tmp.name)/'old.md';path.write_text('Text')
        url=self.registry.register(dict(app='files',kind='file',id=str(path),path=str(path),title='Original'))
        self.registry.set_tags(url,['Wohnung','Wohnung','Projekt'])
        self.assertEqual(self.registry.search('#Wohnung')[0]['url'],url)
        target=path.with_name('new.md');path.rename(target)
        self.registry.relocate(str(path),str(target))
        self.assertEqual(self.registry.resolve(url)['path'],str(target))
        self.assertEqual(self.registry.register(dict(app='files',kind='file',id=str(target),path=str(target),title='Renamed')),url)

if __name__=='__main__':unittest.main()
