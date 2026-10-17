import json
import tempfile
import unittest
from pathlib import Path
from code_library import Collection
from code_library_contract import app_document, export_template, import_template
from lumen_store import Store


class CollectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.collection = Collection(self.store)

    def test_durable_filter_archive_and_revision(self):
        app = self.collection.create('app', 'Vergleich', 'Preise bewerten', {'html': '<p>Hallo</p>'}, 'project-a')
        other = self.collection.create('tool', 'Bericht', value={'prompt': 'Erstelle einen Bericht'})
        self.assertEqual(len(Collection(self.store).items()), 2)
        self.assertEqual(self.collection.items(query='PREISE')[0]['id'], app['id'])
        self.assertEqual(self.collection.items(kind='app', project_id='project-a')[0]['id'], app['id'])
        self.assertEqual(self.collection.items(project_id='')[0]['id'], other['id'])
        updated = self.collection.update(app['id'], 1, favorite=True)
        self.assertEqual(len(self.collection.items(favorite=True)), 1)
        with self.assertRaisesRegex(ValueError, 'inzwischen'):
            self.collection.update(app['id'], 1, title='Lost edit')
        self.collection.update(app['id'], updated['revision'], archived=True)
        self.assertEqual(len(self.collection.items()), 1)
        self.assertEqual(self.collection.items(archived=True)[0]['id'], app['id'])
        self.assertEqual(self.collection.get(app['id'])['definition']['html'], '<p>Hallo</p>')

    def test_archiving_pauses_schedule_and_restore_does_not_enable(self):
        flow = self.store.save_workflow('Flow', [], [self.temp.name], prompt='Do the task', approved=True, enabled=True)
        item = self.collection.create('automation', 'Ablauf', value={'workflow_id': flow})
        archived = self.collection.update(item['id'], 1, archived=True)
        self.assertFalse(self.store.workflows()[0]['enabled'])
        self.collection.update(item['id'], archived['revision'], archived=False)
        self.assertFalse(self.store.workflows()[0]['enabled'])

    def test_portable_template_drops_grants_and_bound_identities(self):
        entry = self.collection.create('automation', 'Prüfen', value={'prompt': 'Prüfe Werte', 'directory': '/private', 'workflow_id': 'private-flow'}, project_id='private-project')
        template = export_template(entry)
        self.assertEqual(template['definition'], {'prompt': 'Prüfe Werte'})
        imported = self.collection.import_entry(json.dumps(template))
        self.assertFalse(imported['archived'])
        self.assertFalse(imported['favorite'])
        self.assertEqual(imported['project_id'], '')
        self.assertNotIn('workflow_id', imported['definition'])
        template['definition']['directory'] = '/private'
        with self.assertRaises(ValueError):
            import_template(template)

    def test_validation_and_opaque_app(self):
        for kind, title, value in [('bad', 'Name', {}), ('tool', '\x00', {}), ('tool', ' ', {}), ('tool', 'Name', {'html': 'bad'}), ('app', 'Name', {'secret': 'bad'})]:
            with self.assertRaises(ValueError):
                self.collection.create(kind, title, value=value)
        doc = app_document('<script>document.body.textContent="app"</script>')
        self.assertIn('sandbox="allow-scripts allow-forms"', doc)
        self.assertNotIn('allow-same-origin', doc)
        self.assertIn("connect-src &#x27;none&#x27;", doc)
        self.assertIn('&lt;script&gt;', doc)
        self.assertEqual(Path(self.store.path).stat().st_mode & 0o777, 0o600)

    def test_native_workflow_executes_real_file_step(self):
        from code_library_execution import prepare_run
        from lumen_tasks import run_steps
        target=Path(self.temp.name)/'report.txt'
        flow=self.store.save_workflow('Write', [{'action':'write','path':str(target),'text':'Actual output'}], [self.temp.name], approved=True)
        item=self.collection.create('automation','Write report',value={'workflow_id':flow})
        task=prepare_run(self.collection,item['id'])
        run_steps(self.store,task)
        self.assertEqual(target.read_text(),'Actual output')
        self.assertEqual(self.store.task(task)['status'],'completed')

    def test_real_tasks_new_input_and_completed_app_adoption(self):
        from code_library_execution import prepare_run, generated_html, preview_file
        tool = self.collection.create('tool', 'Bericht', value={'prompt': 'Erstelle einen Bericht'})
        first = prepare_run(self.collection, tool['id'], 'Input A')
        second = prepare_run(self.collection, tool['id'], 'Input B')
        self.assertNotEqual(first, second)
        self.assertIn('Input B', self.store.task(second)['prompt'])
        self.assertEqual(self.store.task(second)['roots'], [self.store.task(second)['directory']])
        app = self.collection.create('app', 'App', value={'prompt': 'Baue eine Checkliste'})
        task = prepare_run(self.collection, app['id'])
        output = Path(self.store.task(task)['directory']) / 'index.html'
        output.write_text('<button>Hallo</button>')
        with self.assertRaisesRegex(ValueError, 'abgeschlossen'):
            generated_html(self.collection, app['id'])
        self.store.update_task(task, status='completed')
        html = generated_html(self.collection, app['id'])
        self.collection.update(app['id'], 1, definition={'prompt': 'Baue eine Checkliste', 'html': html})
        self.assertIn('sandbox=', preview_file(self.collection, app['id']).read_text())
        next_task=prepare_run(self.collection, app['id'])
        self.store.update_task(next_task,status='completed')
        with self.assertRaises(FileNotFoundError):generated_html(self.collection, app['id'])
        self.collection.used(app['id'],task)
        output.unlink(); output.symlink_to(self.store.path)
        with self.assertRaises(OSError):
            generated_html(self.collection, app['id'])


if __name__ == '__main__':
    unittest.main()
