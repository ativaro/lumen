from pathlib import Path
import tempfile
import unittest
from lumen_store import Store
from lumen_tasks import run_steps
from file_actions import expand, template


class FileActionsTest(unittest.TestCase):
    def test_template_selection_preview_and_native_workflow_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); first = root / 'one.txt'; second = root / 'two.txt'
            first.write_text('one'); second.write_text('two'); store = Store(root / 'state')
            task = dict(directory=tmp, prompt='', steps=[dict(action='copy', source=str(first), path=str(root / '{{stamm}}-copy.txt'))])
            flow = dict(template(task), name='Kopie')
            value = expand(flow, [str(first), str(second)])
            self.assertEqual(value['steps'][1]['path'], str(root / 'two-copy.txt'))
            identity = store.create_task(value['title'], directory=tmp, roots=value['roots'], steps=value['steps'], approved=True)
            run_steps(store, identity)
            self.assertEqual((root / 'one-copy.txt').read_text(), 'one')
            self.assertEqual((root / 'two-copy.txt').read_text(), 'two')
            flow['steps'][0]['path'] = str(root / 'same.txt')
            with self.assertRaises(ValueError): expand(flow, [str(first), str(second)])
            prompt = template(dict(directory=tmp, prompt='Bilder verkleinern\n\nAusgewählte Pfade (Kontext):\n/old/file.jpg', steps=[]))
            value = expand(dict(prompt, name='Webbilder'), [str(first), str(second)])
            self.assertNotIn('/old/', value['prompt']); self.assertIn(str(second), value['prompt'])
