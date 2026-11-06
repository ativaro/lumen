import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMenu
from tools_data import Library
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




    def test_note_attachment_picker_uses_local_links_and_ignores_remote_images(self):
        note=self.root/'note.md';note.write_text('Note')
        asset=self.root/'invoice one.pdf';asset.write_bytes(b'PDF')
        values=interop_ui.note_files('[Invoice](invoice%20one.pdf)\n![Tracking](https://example.invalid/image.png)',note)
        self.assertEqual(values,[str(note),str(asset)])

    def test_note_attachment_picker_does_not_truncate_at_100(self):
        note = self.root / 'note.md'; note.touch()
        assets = [self.root / f'photo-{n:03}.jpg' for n in range(121)]
        for path in assets: path.touch()
        text = '\n'.join(f'![Photo]({path.name})' for path in assets)
        self.assertEqual(interop_ui.note_files(text, note), [str(note), *map(str, assets)])


    def test_file_context_offers_reader_and_filtered_real_actions(self):
        from types import SimpleNamespace
        file=self.root/'book.pdf';file.write_bytes(b'%PDF')
        menu=QMenu();window=SimpleNamespace()
        interop_ui.files_menu(window,menu,[str(file)])
        from lumen_i18n import language
        label='Open with Lumen Reader' if language()=='en' else 'Mit Lumen Reader öffnen'
        self.assertIn(label,[a.text() for a in menu.actions()[0].menu().actions()])
        with patch.object(interop_ui,'launch') as launched:
            menu.actions()[0].menu().actions()[0].trigger()
            launched.assert_called_once_with('reader',[str(file)],None)
        names=[a.text() for a in menu.actions()[0].menu().actions()]
        self.assertIn(interop_ui.tr('Sicherung einrichten …'),names)
        self.assertEqual(names.count(interop_ui.tr('Mit Lumen Reader öffnen')),1)


if __name__=='__main__':unittest.main()
