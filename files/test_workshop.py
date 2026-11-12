import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from test_pdf_fixtures import document,add_content,info,render as draw,streams,text
from document_workshop import inspect, export, render


class WorkshopTest(unittest.TestCase):
    def documents(self, root):
        path = root / 'source.pdf'
        writer=document(['SECRET-IDENTITY-987654','Second page'],size=(400,400),font_size=16,position=(40,80))
        first=writer.objects[writer.page_refs[0].number-1]
        add_content(writer,first,b'BT /F1 16 Tf 40 200 Td (Visible document body) Tj ET')
        writer.objects[writer.root.number-1].update(Metadata=writer.stream(b'PRIVATE METADATA'),Names={'EmbeddedFiles':writer.stream(b'SECRET ATTACHMENT')})
        writer.save(path)
        return path

    def test_order_merge_extract_redaction_ocr_and_immutable_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.documents(root); original = source.read_bytes(); pages = inspect([str(source)])
            export([pages[1],pages[0],pages[1]],root/'ordered.pdf')
            ordered=root/'ordered.pdf'
            self.assertEqual(info(ordered)['pages'],3); self.assertIn('Second page',text(ordered)); self.assertNotIn(b'/Names',ordered.read_bytes())
            pages[0]['boxes'] = [[.07,.13,.87,.24]]
            export([pages[0]],root/'redacted.pdf',ocr=True)
            redacted=root/'redacted.pdf'
            found=text(redacted)
            self.assertNotIn('SECRET',found); self.assertIn('Visible',found); self.assertNotIn(b'PRIVATE',redacted.read_bytes())
            self.assertFalse(any(b'SECRET' in data or b'PRIVATE' in data for data in streams(redacted)))
            pixel=draw(redacted).pixelColor(50,70);self.assertTrue(all(v<30 for v in pixel.getRgb()[:3]))
            self.assertEqual(source.read_bytes(),original)
            with self.assertRaises(FileExistsError): export([pages[0]],root/'redacted.pdf')
            with self.assertRaises(FileExistsError): export(pages,source)
            source.write_bytes(original + b'\n')
            with self.assertRaises(ValueError): export(pages,root/'stale.pdf')
            self.assertFalse((root/'stale.pdf').exists())

    def test_native_preview_draw_rotate_and_export_worker(self):
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from document_workshop_ui import DocumentWorkshop
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.documents(root); dialog = DocumentWorkshop([str(source)]); dialog.show()
            def wait():
                deadline = time.monotonic()+10
                while time.monotonic()<deadline:
                    app.processEvents(); time.sleep(.01)
                    if dialog.proc is None and dialog.pages.count() and dialog.canvas.page: return
                self.fail(dialog.status.text())
            wait(); self.assertEqual(dialog.pages.count(),2)
            dialog.redact.setChecked(True)
            first = dialog.canvas.mapFromScene(40,50); last = dialog.canvas.mapFromScene(350,95)
            QTest.mousePress(dialog.canvas.viewport(),Qt.LeftButton,pos=first)
            QTest.mouseMove(dialog.canvas.viewport(),last)
            QTest.mouseRelease(dialog.canvas.viewport(),Qt.LeftButton,pos=last)
            # Some offscreen backends omit intermediate moves; exercise the same stored recipe.
            from PySide6.QtCore import Qt
            value=dialog.pages.item(0).data(Qt.UserRole)
            if not value['boxes']: value['boxes']=[[.1,.125,.875,.2375]]; dialog.pages.item(0).setData(Qt.UserRole,value)
            dialog.rotate(); wait()
            self.assertEqual(dialog.pages.item(0).data(Qt.UserRole)['rotation'],90)
            target=root/'native.pdf'
            with patch('document_workshop_ui.QFileDialog.getSaveFileName',return_value=(str(target),'PDF')): dialog.save(True)
            wait(); self.assertTrue(target.exists(),dialog.status.text()); dialog.reject(); app.processEvents()
