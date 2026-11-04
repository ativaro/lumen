import unittest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from engine_extensions import ExtensionsView, inventory, plugin_name


CONFIG={'mcp':{'fixture':{'enabled':True,'url':'https://secret@private.test/token','headers':{'Authorization':'private-header'}},'off':{'enabled':False}},
        'plugin':['@example/plugin@1.2.3',['https://user:private-password@plugin.test/?secret=private-query',{'key':'private-options'}]]}
SKILLS=[dict(name='fixture-skill',description='Synthetic search description',content='# Fixture\nUse the available tools.',location='/private/location')]


class Backend(QObject):
    failed=Signal(str)
    def ensure_server(self, callback): callback()
    def request(self, method, path, callback=None, error=None):
        assert method=='GET'
        callback({'/config':CONFIG,'/mcp':{'fixture':{'status':'connected','error':'private-error'}},'/skill':SKILLS}[path])
    def shutdown(self): self.stopped=True


class ExtensionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_metadata_never_displays_credentials_options_paths_or_raw_errors(self):
        rows=inventory(CONFIG,{'fixture':{'status':'failed','error':'private-error'}},SKILLS)
        text=str(rows)
        for secret in ('private-header','private-password','private-query','private-options','private/location','private-error','private.test'): self.assertNotIn(secret,text)
        self.assertEqual(rows['mcp'][1]['status'],'Ausgeschaltet')
        self.assertEqual(rows['plugins'][0]['name'],'@example/plugin@1.2.3')

    def test_lazy_load_tabs_search_and_skill_details(self):
        calls=[]
        def factory(parent): calls.append(True); return Backend(parent)
        view=ExtensionsView(factory); self.addCleanup(view.deleteLater)
        self.assertEqual(calls,[]); view.refresh(); self.assertEqual(len(calls),1)
        self.assertEqual(view.list.count(),2)
        view.tabs.setCurrentIndex(2); self.assertIn('Use the available tools.',view.detail.toPlainText())
        view.search.setText('missing'); self.assertEqual(view.list.count(),0)
        view.search.clear(); self.assertEqual(view.list.count(),1)
        backend=view.backend; view.stop(); self.assertTrue(backend.stopped)

    def test_invalid_shapes_are_an_error_not_a_false_empty_inventory(self):
        with self.assertRaises(ValueError): inventory([],{},[])
        with self.assertRaises(ValueError): inventory({'plugin':'bad'}, {}, [])

    def test_local_plugins_keep_their_filename_without_exposing_private_directories(self):
        self.assertEqual(plugin_name('file:///private/directory/lumen-tools.js'), 'lumen-tools.js')
        self.assertEqual(plugin_name('/private/directory/lumen-tools.js'), 'lumen-tools.js')
