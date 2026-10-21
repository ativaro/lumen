import unittest
from notes_properties import change,values,filters,matches


class PropertiesTest(unittest.TestCase):
    def test_add_edit_delete_preserves_unknown_yaml_and_body(self):
        text='---\nstatus: offen # comment\nforeign: {items: [a, b]}\n---\n# Note\nBody 🌍\n'
        new=change(text,'status',value='done: yes')
        self.assertIn('status: "done: yes" # comment',new);self.assertIn('foreign: {items: [a, b]}',new)
        new=change(new,'due','date','2026-10-14');self.assertEqual(values(new)['due'],{'kind':'date','value':'2026-10-14'})
        self.assertTrue(new.endswith('# Note\nBody 🌍\n'));self.assertNotIn('status:',change(new,'status',remove=True))
        self.assertEqual(values(change('# Note','status',value='open'))['status']['value'],'open')
    def test_invalid_ambiguous_and_anchored_metadata_are_rejected(self):
        for text in ('---\nstatus: [x\n---\n','---\nstatus: a\nstatus: b\n---\n','---\nbase: &a open\nstatus: *a\n---\n','---\nstatus: {a: b}\n---\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):change(text,'status',value='new')
        for value in ('2026-02-30','20261014','tomorrow'):
            with self.assertRaises(ValueError):change('# Note','due','date',value)
        with self.assertRaises(ValueError):change('# Note','tags',value='x')
    def test_block_scalar_and_filters(self):
        text='---\nsummary: |\n  First\n  Second\nstatus: open\n---\nBody'
        changed=change(text,'summary',value='Short');self.assertEqual(values(changed)['status']['value'],'open')
        self.assertIn('status: open',change(text,'summary',remove=True))
        query,selected=filters('Report #project [status=OPEN] [due=2026-10-14]')
        self.assertEqual(query.strip(),'Report #project');self.assertTrue(matches(change(text,'due','date','2026-10-14'),selected))
        self.assertFalse(matches(text,selected))

    def test_property_and_tag_text_search_are_combined(self):
        from wissen_data import parse,search
        notes=[parse('a.md',b'---\nstatus: open\ntags: [project]\n---\n# Report'),parse('b.md',b'---\nstatus: done\ntags: [project]\n---\n# Report')]
        self.assertEqual([n['path'] for n in search(notes,'Report #project [status=open]')],['a.md'])

class NativePropertiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def wait(self,check):
        from PySide6.QtTest import QTest
        for _ in range(600):
            QTest.qWait(20)
            if check():return
        self.fail('Properties timed out')


    def test_default_order_does_not_replace_search_ranking(self):
        from notes_views import ordered
        notes=[dict(title='Z',path='z',text='',modified=1),dict(title='A',path='a',text='',modified=2)]
        self.assertEqual(ordered(notes,''),notes);self.assertEqual(ordered(notes,'title')[0]['path'],'a')
