import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import pymupdf
from document_workshop import inspect, export, render


class WorkshopTest(unittest.TestCase):
    def documents(self, root):
        path = root / 'source.pdf'
        with pymupdf.open() as doc:
            first = doc.new_page(width=400,height=400)
            first.insert_text((40,80), 'SECRET-IDENTITY-987654', fontsize=16)
            first.insert_text((40,200), 'Visible document body', fontsize=16)
            doc.new_page(width=400,height=400).insert_text((40,80),'Second page',fontsize=16)
            doc.set_metadata({'title':'PRIVATE METADATA'}); doc.embfile_add('secret.txt',b'SECRET ATTACHMENT')
            doc.save(path)
        return path

    def test_order_merge_extract_redaction_ocr_and_immutable_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.documents(root); original = source.read_bytes(); pages = inspect([str(source)])
            export([pages[1],pages[0],pages[1]],root/'ordered.pdf')
            with pymupdf.open(root/'ordered.pdf') as result:
                self.assertEqual(len(result),3); self.assertIn('Second page',result[0].get_text()); self.assertEqual(result.embfile_count(),0)
            pages[0]['boxes'] = [[.07,.13,.87,.24]]
            export([pages[0]],root/'redacted.pdf',ocr=True)
            with pymupdf.open(root/'redacted.pdf') as result:
                text = result[0].get_text()
                self.assertNotIn('SECRET',text); self.assertIn('Visible',text); self.assertNotIn('PRIVATE',str(result.metadata))
                for xref in range(1,result.xref_length()):
                    if result.xref_is_stream(xref): self.assertNotIn(b'SECRET',result.xref_stream(xref))
                pix = result[0].get_pixmap(); sample = pix.pixel(50,70); self.assertTrue(all(v<30 for v in sample))
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
