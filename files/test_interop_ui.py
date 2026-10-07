import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMenu
from tools_data import Library
from tools_workbench import Workbench
from interop_data import Registry
import interop_ui


class InteropUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'LUMEN_TOOLS_DATA':self.tmp.name,'LUMEN_DATA':self.tmp.name+'/state'})
        self.env.start();self.addCleanup(self.env.stop)
        self.root=Path(self.tmp.name)
        self.registry=Registry(self.root)
        self.windows=[]
        self.addCleanup(self.close)

    def close(self):
        for w in self.windows:
            if w.job:w.job.cancelled.set();w.job.wait(5000)
            w.close();w.deleteLater()
        self.app.processEvents()

    def pump(self,predicate):
        until=time.monotonic()+4
        while time.monotonic()<until:
            self.app.processEvents()
            if predicate():return
            time.sleep(.01)
        self.fail('UI operation did not finish')

    def window(self):
        w=Workbench(self.root);self.windows.append(w);w.error=lambda text:self.fail(text);return w

    def test_transfer_updates_existing_project_after_saving_open_edit(self):
        w=self.window();key=w.library.create('Project',notes='Old',questions=[],resources=[]);w.focus_record(key)
        w.notes.setPlainText('Unsaved user edit')
        source=self.registry.register(dict(app='wissen',kind='note',id='test.md',title='Source'))
        token=self.registry.enqueue('workbench','workbench.add',dict(title='Incoming',text='New material',source_url=source))
        choice=dict(id=key,title='Project',mode='copy',token=token,due='')
        with patch.object(interop_ui,'review',return_value=choice):
            interop_ui.controller(w).enqueue({'handoff':token})
            self.pump(lambda:self.registry.request(token)['state']=='done')
            self.pump(lambda:not w.job and not interop_ui.controller(w).queue)
        record=w.library.get(key)
        self.assertIn('Unsaved user edit',record['notes']);self.assertIn('New material',record['notes'])
        self.assertEqual(len(self.registry.related(self.registry.request(token)['result'])),1)
        with patch.object(interop_ui,'review',side_effect=AssertionError('Replay must not import')):
            interop_ui.controller(w).deliver({'handoff':token})
        self.assertEqual(len(w.library.all()),1)

    def test_cancel_keeps_request_pending_and_destination_unchanged(self):
        w=self.window();token=self.registry.enqueue('workbench','workbench.add',dict(title='Cancelled',text='Text'))
        with patch.object(interop_ui,'review',return_value=None):interop_ui.controller(w).deliver({'handoff':token})
        self.assertEqual(self.registry.request(token)['state'],'pending');self.assertEqual(w.library.all(),[])

    def test_note_attachment_picker_uses_local_links_and_ignores_remote_images(self):
        note=self.root/'note.md';note.write_text('Note')
        asset=self.root/'invoice one.pdf';asset.write_bytes(b'PDF')
        values=interop_ui.note_files('[Invoice](invoice%20one.pdf)\n![Tracking](https://example.invalid/image.png)',note)
        self.assertEqual(values,[str(note),str(asset)])

    def test_formatted_draft_escapes_markup_and_preserves_heading_list(self):
        from inbox_data import draft_html
        value=draft_html('# Heading\n\n- First\n- <img src="https://example.invalid">\n\nParagraph')
        self.assertIn('<h1>Heading</h1>',value);self.assertIn('<li>First</li>',value)
        self.assertNotIn('<img',value);self.assertIn('&lt;img',value)

    def test_file_context_offers_reader_and_filtered_real_actions(self):
        from types import SimpleNamespace
        file=self.root/'book.pdf';file.write_bytes(b'%PDF')
        menu=QMenu();window=SimpleNamespace()
        interop_ui.files_menu(window,menu,[str(file)])
        from lumen_i18n import language
        label='Open with Lumen Reader' if language()=='en' else 'Mit Lumen Reader öffnen'
        self.assertIn(label,[a.text() for a in menu.actions()])
        with patch.object(interop_ui,'launch') as launched:
            menu.actions()[0].trigger()
            launched.assert_called_once_with('reader',[str(file)],None)
        names=[a.text() for a in menu.actions()[1].menu().actions()]
        self.assertIn(interop_ui.tr('Sicherung einrichten …'),names)
        self.assertNotIn(interop_ui.tr('Mit Lumen Reader öffnen'),names)

    def test_busy_target_queues_reference_until_edits_can_be_flushed(self):
        w=self.window();first=w.library.create('First',notes='',questions=[],resources=[]);second=w.library.create('Second',notes='',questions=[],resources=[])
        w.focus_record(first);w.notes.setPlainText('Keep me')
        url=self.registry.register(dict(app='workbench',kind='record',id=second,title='Second'))
        controller=interop_ui.controller(w)
        controller.running=True;controller.enqueue({'ref':url});controller.process()
        self.assertEqual(w.current,first)
        controller.running=False;controller.process()
        self.assertEqual(w.current,second);self.assertEqual(w.library.get(first)['notes'],'Keep me')

if __name__=='__main__':unittest.main()
