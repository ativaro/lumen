"""Real local reader transfers, page matching and OCR; no network/model calls."""
import io
import tempfile
from pathlib import Path
import unittest

from test_pdf_fixtures import document,add_image
from tools_data import Library, Cancelled
from tools_ui import Job
import reader_data
import interop_reader as bridge


class ReaderBridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.library = Library('reader', self.root/'tools')
        self.job = Job(lambda _: None)

    def pdf(self, path, texts, toc=None):
        document(texts,font_size=20,position=(50,90),toc=toc).save(path)

    def test_progress_and_safe_refresh_relocate_marks_after_inserted_page(self):
        path = self.root/'book.pdf'; self.pdf(path, ['First chapter', 'Second chapter'])
        key = reader_data.import_file(self.library, path, self.job)
        mark = reader_data.add_note(self.library, key, 1, 'Second chapter', [0, 1])
        self.library.update(key, page=1, scroll=77)
        progress = bridge.progress_for_paths([str(path)], self.root/'tools')[str(path)][0]
        self.assertEqual((progress['page'], progress['pages'], progress['marks']), (1, 2, 1))
        path.unlink(); self.pdf(path, ['New introduction', 'First chapter', 'Second chapter'])
        status = bridge.compare_original(self.library, key, self.job); self.assertTrue(status['changed'])
        result = bridge.refresh_original(self.library, key, self.job)
        record = self.library.get(key)
        self.assertTrue(result['changed']); self.assertEqual(record['page'], 2); self.assertEqual(record['scroll'], 77)
        self.assertEqual(record['notes'][0], dict(mark, page=2)); self.assertEqual(record['pages'], 3)
        self.assertFalse(bridge.compare_original(self.library, key, self.job)['changed'])

    def test_ambiguous_or_changed_marked_page_keeps_old_copy_and_marks(self):
        path = self.root/'book.pdf'; self.pdf(path, ['Unique source'])
        key = reader_data.import_file(self.library, path, self.job)
        reader_data.add_note(self.library, key, 0, 'Unique source', [0, 1]); before = self.library.get(key)
        original = self.library.asset(before['asset']).read_bytes()
        path.unlink(); self.pdf(path, ['Unique source', 'Unique source'])
        with self.assertRaises(ValueError): bridge.refresh_original(self.library, key, self.job)
        self.assertEqual(self.library.get(key), before); self.assertEqual(self.library.asset(before['asset']).read_bytes(), original)
        self.assertEqual(len(list(self.library.assets.iterdir())), 1)

    def test_chapter_marks_have_individual_page_and_note_backlinks(self):
        path = self.root/'book.pdf'; self.pdf(path, ['Chapter one', 'Chapter two'], [[1, 'One', 1], [1, 'Two', 2]])
        key = reader_data.import_file(self.library, path, self.job)
        first = reader_data.add_note(self.library, key, 0, 'Chapter one')
        second = reader_data.add_note(self.library, key, 1, 'Chapter two')
        self.library.update(key, page=1)
        payload = bridge.marks_payload(self.library, key, chapter=True)
        self.assertIn(second['id'], payload['text']); self.assertNotIn(first['id'], payload['text'])
        self.assertIn('page=1', payload['text']); self.assertEqual(len(payload['items']), 1)
        self.assertEqual(len(bridge.marks_payload(self.library, key)['items']), 2)

    def test_scan_ocr_is_searchable_selectable_text_without_changing_original(self):
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (1600, 400), 'white'); draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 90)
        draw.text((70, 100), 'LUMEN LOCAL SCAN', fill='black', font=font)
        output = io.BytesIO(); image.save(output, format='PNG')
        path = self.root/'scan.pdf'
        writer=document(size=(800,200));page=writer.objects[writer.page_refs[0].number-1]
        add_image(writer,page,image.tobytes(),1600,400,(0,0,800,200));writer.save(path)
        original = path.read_bytes(); key = reader_data.import_file(self.library, path, self.job)
        text = bridge.ocr_page(self.library, key, 0, self.job)
        self.assertIn('LUMEN', text); self.assertEqual(self.library.get(key)['ocr_text']['0'], text)
        self.assertEqual(path.read_bytes(), original)

    def test_refresh_cancel_does_not_change_reader_state(self):
        path = self.root/'book.pdf'; self.pdf(path, ['First'])
        key = reader_data.import_file(self.library, path, self.job); before = self.library.get(key)
        self.job.cancelled.set()
        with self.assertRaises(Cancelled): bridge.refresh_original(self.library, key, self.job)
        self.assertEqual(self.library.get(key), before)

    def test_native_reader_focuses_exact_mark_and_uses_saved_ocr_in_text_view(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtTest import QTest
        from tools_reader import Reader
        app = QApplication.instance() or QApplication([])
        path = self.root/'book.pdf'; self.pdf(path, ['First', 'Second'])
        key = reader_data.import_file(self.library, path, self.job)
        note = reader_data.add_note(self.library, key, 1, 'Second')
        self.library.update(key, ocr_text={'1': 'LUMEN OCR TARGET'})
        window = Reader(self.library.root.parent)
        try:
            window.focus_record(key); window.focus_position(dict(page=1, note=note['id']))
            for _ in range(100):
                QTest.qWait(20)
                if window.data and not window.job: break
            self.assertEqual(window.page_index, 1); self.assertEqual(window.note_id, note['id'])
            self.assertEqual(window.text.toPlainText(), 'LUMEN OCR TARGET')
            self.assertEqual(bridge.search_ocr(window.library.get(key), 'target')[0]['page'], 1)
        finally:
            window.close(); window.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__': unittest.main()
