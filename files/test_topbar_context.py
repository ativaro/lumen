import base64
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from topbar_context import page_source, recording, transfer_snapshot, web_url, remember_page, reader_discuss, belongs_to, browser_pages


class TopbarContextTest(unittest.TestCase):
    def test_transfer_summary_is_read_only_and_only_current_drive_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lumen.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE settings(key TEXT,value TEXT)')
                for index,(action,status,updated,done,total) in enumerate([
                    ('drive-upload','running',99,42,100),('drive-download','running',99,100,200),
                    ('drive-upload','completed',99,500,500),('drive-upload','running',0,10,20),
                    ('copy','running',99,10,10)]):
                    row=dict(id=f'{index:032x}',action=action,status=status,updated=updated,bytes=done,total=total)
                    db.execute('INSERT INTO settings VALUES(?,?)',('workplace/transfer/'+row['id'],json.dumps(row)))
            before=path.read_bytes()
            self.assertEqual(transfer_snapshot(directory,100),dict(id='0'*32,count=2,percent=47))
            self.assertEqual(path.read_bytes(),before)
            self.assertIsNone(transfer_snapshot(directory,120))

    def test_unknown_transfer_total_does_not_invent_percentage(self):
        with tempfile.TemporaryDirectory() as directory:
            with sqlite3.connect(Path(directory)/'lumen.sqlite3') as db:
                db.execute('CREATE TABLE settings(key TEXT,value TEXT)')
                db.execute('INSERT INTO settings VALUES(?,?)',('workplace/transfer/'+'a'*32,
                    json.dumps(dict(id='a'*32,action='drive-upload',status='queued',updated=100,total=0,bytes=0))))
            self.assertIsNone(transfer_snapshot(directory,100)['percent'])

    def test_page_context_and_url_validation(self):
        source=dict(title='Workshop — Chromium',app='Chromium')
        encoded=base64.b64encode(json.dumps(source).encode()).decode()
        self.assertEqual(page_source(encoded),source)
        for invalid in ['not base64',base64.b64encode(b'{}').decode(),base64.b64encode(json.dumps(dict(title='x',app='Vault')).encode()).decode()]:
            with self.assertRaises(ValueError):page_source(invalid)
        self.assertEqual(web_url('https://example.org/workshop'),'https://example.org/workshop')
        for url in ['file:///etc/passwd','javascript:alert(1)','https://user:pw@example.org','https://example.org/\n']:
            with self.assertRaises(ValueError):web_url(url)

    def test_recording_requires_live_lumen_microphone_stream(self):
        node=dict(info=dict(state='running',props={'media.class':'Stream/Input/Audio','application.name':'Lumen Audio Studio'}))
        self.assertTrue(recording([node]))
        node['info']['state']='suspended';self.assertFalse(recording([node]))
        node['info']['state']='running';node['info']['props']['application.name']='Other app'
        self.assertFalse(recording([node]))

    def test_capture_process_ancestry(self):
        import os
        self.assertTrue(belongs_to(os.getpid(),{os.getppid()}))
        self.assertFalse(belongs_to('bad',{os.getpid()}))
        self.assertFalse(belongs_to(os.getpid(),set()))

    def test_browser_page_becomes_reviewable_notes_handoff(self):
        from interop_data import Registry
        encoded=base64.b64encode(json.dumps(dict(title='Workshop',app='Chromium')).encode()).decode()
        with tempfile.TemporaryDirectory() as directory:
            registry=Registry(directory)
            with patch('topbar_context.browser_pages',return_value=['https://example.org/workshop']), \
                 patch('PySide6.QtWidgets.QInputDialog.getText',return_value=('https://example.org/workshop',True)), \
                 patch('interop_data.Registry',return_value=registry),patch('interop_open.launch') as launch:
                remember_page(encoded)
                launch.assert_called_once()
                target,args=launch.call_args.args
                self.assertEqual(target,'wissen');self.assertEqual(args[0],'--handoff')
                row=registry.request(args[1])
                self.assertEqual(row['state'],'pending')
                self.assertEqual(row['payload']['url'],'https://example.org/workshop')
                self.assertEqual(row['action'],'wissen.import')

    def test_kde_tab_match_uses_title_column_before_icon_column(self):
        rows=[('7','Workshop','web-browser',100,1.0,{'urls':['https://example.org/workshop']}),
              ('8','Other page','Workshop',100,1.0,{'urls':['https://example.org/other']})]
        obj=SimpleNamespace(get_dbus_method=lambda *_:lambda *a,**kw:rows)
        bus=SimpleNamespace(list_names=lambda:['org.kde.plasma.browser_integration-123'],get_object=lambda *_:obj)
        with patch('dbus.SessionBus',return_value=bus):
            self.assertEqual(browser_pages(dict(title='Workshop — Chromium',app='Chromium')),['https://example.org/workshop'])

    def test_reader_attaches_current_document_without_sending_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.pdf';path.write_bytes(b'%PDF-1.4\n')
            window=SimpleNamespace(current='one',library=SimpleNamespace(get=lambda _:dict(asset='one'),asset=lambda _:path))
            with patch('lumen_launch.executable',return_value='/bin/lumen-test'),patch('topbar_context.subprocess.Popen') as launch:
                reader_discuss(window)
                args=launch.call_args.args[0]
                self.assertIn('--file',args);self.assertEqual(args[-1],str(path))
                self.assertNotIn('--prompt',args)


if __name__=='__main__':unittest.main()
