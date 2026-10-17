import json
import tempfile
import unittest
from code_library import Collection
from lumen_store import Store


class AppEditTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.collection=Collection(Store(self.tmp.name));self.item=self.collection.create('app','Vergleich','Zwei Preise',{'html':'<input id="a" value="1">','prompt':'Vergleichen'},project_id='retained')

    def test_draft_commit_discard_and_restart(self):
        from code_app_edit import Drafts
        drafts=Drafts(self.collection);d=drafts.open(self.item['id'])
        d['value']['html']='<input id="a" value="2">';d['request']='Versand ergänzen';d=drafts.write(d)
        self.assertEqual(self.collection.get(self.item['id'])['definition']['html'],'<input id="a" value="1">')
        reopened=Drafts(Collection(self.collection.store)).open(self.item['id']);self.assertEqual(reopened['value'],d['value'])
        saved=drafts.commit(reopened);self.assertEqual(saved['definition']['html'],d['value']['html']);self.assertEqual(saved['project_id'],'retained');self.assertEqual(saved['definition']['prompt'],'Vergleichen')
        fresh=drafts.open(saved['id']);fresh['value']['title']='';fresh=drafts.write(fresh);self.assertEqual(drafts.open(saved['id'])['value']['title'],'');drafts.discard(fresh)
        self.assertEqual(drafts.open(saved['id'])['value']['title'],'Vergleich')

    def test_concurrent_drafts_and_saved_revision_preserve_data(self):
        from code_app_edit import Drafts
        drafts=Drafts(self.collection);a=drafts.open(self.item['id']);b=drafts.open(self.item['id'])
        a['request']='A';a=drafts.write(a)
        b['request']='B'
        with self.assertRaisesRegex(ValueError,'Editor'):drafts.write(b)
        current=self.collection.get(self.item['id']);self.collection.update(current['id'],current['revision'],description='Extern')
        a['value']['html']='<p>Entwurf</p>';a=drafts.write(a)
        with self.assertRaisesRegex(ValueError,'inzwischen'):drafts.commit(a)
        self.assertEqual(drafts.open(self.item['id'])['value']['html'],'<p>Entwurf</p>')
        self.assertEqual(self.collection.get(self.item['id'])['description'],'Extern')

    def test_model_contract_and_data_boundary(self):
        from code_app_edit import proposal,parse_result
        source=self.item['definition']['html'];request=proposal(source,'Versand hinzufügen')
        self.assertIn(source,json.loads(request.split('DATEN:\n',1)[1])['html'])
        result=parse_result(json.dumps(dict(html='<html><body>Neu</body></html>',changes=['Versand ergänzt'])))
        self.assertEqual(result['changes'],['Versand ergänzt'])
        for invalid in [dict(html='',changes=[]),dict(html='x',changes=['x'],path='/tmp/no'),dict(html='x',changes=[{}]),dict(html='x'*262145,changes=['x'])]:
            with self.assertRaises(ValueError):parse_result(json.dumps(invalid))
