import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFilter


class PhotoToolsTest(unittest.TestCase):
    def test_cache_reuses_decode_and_invalidates_changed_original(self):
        from preview import preview_data
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CACHE_HOME': tmp + '/cache'}):
            path = Path(tmp)/'source.jpg'; output = str(Path(tmp)/'out.png')
            Image.new('RGB',(1200,800),'red').save(path)
            before = preview_data(path, output, 1000)
            with patch('preview.QImageReader', side_effect=AssertionError('should use cached thumbnail')):
                small = preview_data(path, output, 640)
            self.assertEqual(small['stamp'], before['stamp'])
            with Image.open(output) as image: self.assertEqual(image.size, (640,426))
            Image.new('RGB',(800,600),'blue').save(path)
            after = preview_data(path, output, 640)
            self.assertNotEqual(before['stamp'], after['stamp'])
            self.assertEqual(after['width'],800)
            with Image.open(output) as image: self.assertGreater(image.getpixel((5,5))[2],240)

    def test_tidy_groups_real_capture_times_and_never_changes_sources(self):
        from photo_tools import tidy, quality, read_image, images
        from image_edit import file_stamp
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); image = Image.new('RGB',(256,256),'white'); draw=ImageDraw.Draw(image)
            for x in range(0,256,12): draw.rectangle((x,0,x+5,255),fill='black')
            self.assertGreater(quality(image)[0],quality(image.filter(ImageFilter.GaussianBlur(5)))[0])
            exif=Image.Exif(); exif[306]='2026:09:01 12:00:00'; exif[272]='Test camera'
            image.save(root/'one.jpg',exif=exif); image.save(root/'two.jpg',exif=exif)
            Image.new('RGB',(200,200),'white').save(root/'Screenshot.png')
            (root/'link.jpg').symlink_to(root/'one.jpg')
            self.assertEqual(len(list(images(root))),3)
            with self.assertRaises(ValueError): read_image(root/'link.jpg')
            stamps={p.name:file_stamp(p.stat()) for p in root.iterdir()}
            class Gate:
                def wait(self): pass
            events=[]
            with patch('photo_tools.emit', side_effect=lambda **e:events.append(e)): tidy(root,Gate())
            groups=[e['item']['group'] for e in events if 'item' in e]
            self.assertEqual(groups.count('Bildserie 1'),2); self.assertIn('Screenshots',groups); self.assertIn('Wenig Details',groups)
            self.assertEqual(stamps,{p.name:file_stamp(p.stat()) for p in root.iterdir()})

    def test_activity_and_sensor_units_and_policy(self):
        from lumen_hardware import activity, sensors, background_reason
        from lumen_store import Store
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); proc=root/'123'; proc.mkdir(); (proc/'comm').write_text('game.exe\n')
            (proc/'environ').write_bytes(b'SteamAppId=1234\0SECRET=not-returned\0')
            self.assertEqual(activity(root),['Steam-Spiel'])
            (proc/'comm').write_text('obs'); (proc/'environ').write_bytes(b'SteamAppId=0\0')
            self.assertEqual(activity(root),['OBS geöffnet'])
            (proc/'comm').write_text('gpu-screen-reco')
            self.assertEqual(activity(root),['GPU Screen Recorder geöffnet'])
            self.assertEqual(activity(root,uid=os.getuid()+1),[])
            store=Store(root/'state'); store.set_setting('modelPolicy',{'gpu_limit':100})
            with patch('lumen_hardware.activity',return_value=['OBS geöffnet']):
                self.assertIn('OBS',background_reason(store))
                store.set_setting('modelPolicy',{'gpu_limit':100,'pause_on_activity':False})
                self.assertEqual(background_reason(store),'')
        rows=sensors({'coretemp':{'Package':{'temp1_input':52,'temp1_max':90},'Power':{'power1_average':21},'Fan':{'fan1_input':0}}})
        self.assertEqual([(r['value'],r['unit']) for r in rows],[(52,'°C'),(21,'W'),(0,'U/min')])
        self.assertEqual(sensors({'bad':{'bad':{'temp1_input':float('nan')}}}),[])

    def test_stale_photo_is_not_trashed_by_transfer_worker(self):
        from lumen_store import Store
        from lumen_transfers import create, execute
        from image_edit import file_stamp
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'image.jpg'; path.write_bytes(b'first'); store=Store(root/'state')
            value=create(store,'trash',[str(path)],expected={str(path):file_stamp(path.stat())})
            path.write_bytes(b'changed')
            execute(store,value['id'])
            self.assertEqual(path.read_bytes(),b'changed')
            self.assertIn('verändert',store.setting('transfer/'+value['id'])['errors'][0])

    def test_native_review_is_explicit_cancellable_and_uses_preview(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from photo_tools_ui import PhotoToolsDialog
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            Image.new('RGB',(200,200),'white').save(Path(tmp)/'Screenshot.png')
            dialog=PhotoToolsDialog(tmp,'tidy'); dialog.show()
            self.assertIsNone(dialog.proc); self.assertFalse(dialog.trash_button.isEnabled())
            dialog.override.setChecked(True); dialog.start()
            deadline=time.monotonic()+10
            while dialog.proc and time.monotonic()<deadline: QTest.qWait(30)
            self.assertIsNone(dialog.proc); self.assertGreater(dialog.results.topLevelItemCount(),0)
            self.assertFalse(dialog.trash_button.isEnabled())
            dialog.results.setCurrentItem(dialog.results.topLevelItem(0)); QTest.qWait(100)
            self.assertTrue(dialog.open_button.isEnabled()); dialog.reject()


if __name__ == '__main__': unittest.main()
