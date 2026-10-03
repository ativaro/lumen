import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from content_search import scan
from lumen_ocr import save_cache, stamp


class OCRTest(unittest.TestCase):
    def test_real_image_scanned_pdf_and_cached_image_description(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            root = Path(tmp) / 'documents'; root.mkdir()
            image = Image.new('RGB', (1600, 450), 'white')
            ImageDraw.Draw(image).text((50, 130), 'Monitor invoice 987654', fill='black', font=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf', 65))
            image.save(root / 'scan.png'); image.save(root / 'scan.pdf', resolution=150)
            results = list(scan(root, [['monitor'], ['invoice']], ocr=True))
            hits = [e for e in results if e['type'] == 'hit']
            self.assertEqual({Path(e['path']).name for e in hits}, {'scan.png', 'scan.pdf'}, results)
            self.assertTrue(all(e['page'] == 1 for e in hits))
            save_cache(root / 'scan.png', stamp((root / 'scan.png').stat()), caption='Rotes Auto neben einem Haus. Red car.')
            hits = [e for e in scan(root, [['rot'], ['auto']]) if e['type'] == 'hit']
            self.assertEqual(len(hits), 1)
            image.save(root / 'scan.png')
            self.assertFalse([e for e in scan(root, [['auto']]) if e['type'] == 'hit'])

    def test_native_vision_queue_is_opt_in_and_reuses_provider_without_tools(self):
        from PySide6.QtWidgets import QApplication
        from content_search_dialog import ContentSearchDialog
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            path = Path(tmp) / 'car.png'; Image.new('RGB', (100, 100), 'red').save(path)
            dialog = ContentSearchDialog(tmp)
            self.assertFalse(dialog.vision.isChecked())
            dialog.active_groups = [['rot'], ['auto']]
            thumb = Path(dialog.model_context.name) / 'thumb.jpg'; Image.new('RGB', (100, 100)).save(thumb)
            dialog.image_queue = [dict(path=str(path), thumbnail=str(thumb), stamp=stamp(path.stat()))]
            with patch.object(dialog.backend, 'send') as send:
                dialog.next_image(); self.assertTrue(send.call_args.kwargs['proposal'])
                self.assertEqual(send.call_args.args[1][0][1], 'image/jpeg')
            dialog.image_completed(True, '{"caption":"Ein rotes Auto."}')
            self.assertEqual(dialog.results.topLevelItemCount(), 1)
            self.assertFalse(thumb.exists()); dialog.reject(); app.processEvents()
