import io
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile
from tools_data import Library
from tools_ui import Job
import reader_data as reader


class ReaderTest(unittest.TestCase):
    def setUp(self):
        try:import pymupdf
        except ImportError:self.skipTest('Optional PyMuPDF is required for document rendering')
        self.pdf=pymupdf;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.library=Library('reader',self.root/'data');self.job=Job(lambda _:None)

    def test_pdf_copy_render_notes_search_rotation_and_password(self):
        path=self.root/'document.pdf'
        with self.pdf.open() as doc:
            for text in ['First page','Second page']:
                page=doc.new_page();page.insert_text((50,80),text)
            doc[1].set_rotation(90);doc.set_toc([[1,'Chapter two',2]]);doc.save(path)
        original=path.read_bytes();key=reader.import_file(self.library,path,self.job);book=self.library.get(key);asset=self.library.asset(book['asset'])
        data=reader.worker(self.job,'page',asset,page=1,stamp=book['stamp'])
        self.assertGreater(data['width'],data['height']);self.assertTrue(data['png']);self.assertEqual(data['words'][0][4],'Second')
        hits=reader.worker(self.job,'search',asset,query='second');self.assertEqual(hits[0]['page'],1)
        note=reader.add_note(self.library,key,1,'Second page',[0,1]);self.library.update(key,page=1,scroll=123)
        again=Library('reader',self.root/'data').get(key);self.assertEqual(again['page'],1);self.assertEqual(again['notes'][0],note);self.assertEqual(path.read_bytes(),original)
        asset.write_bytes(original+b'\n')
        with self.assertRaises(ValueError):reader.worker(self.job,'page',asset,page=1,stamp=book['stamp'])
        encrypted=self.root/'locked.pdf'
        with self.pdf.open(path) as doc:doc.save(encrypted,encryption=self.pdf.PDF_ENCRYPT_AES_256,user_pw='test-reader-pass',owner_pw='test-owner-pass')
        key=reader.import_file(self.library,encrypted,self.job);book=self.library.get(key)
        self.assertTrue(book['locked']);self.assertTrue(reader.worker(self.job,'page',self.library.asset(book['asset']),password='wrong')['locked'])
        self.assertEqual(reader.worker(self.job,'page',self.library.asset(book['asset']),password='test-reader-pass')['pages'],2)
        self.assertNotIn(b'test-reader-pass',self.library.db.read_bytes())

    def test_epub_layout_html_is_sanitized_and_archive_limits(self):
        path=self.root/'book.epub'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('mimetype','application/epub+zip')
            z.writestr('META-INF/container.xml','<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            z.writestr('OEBPS/book.opf','<package version="2.0" unique-identifier="id" xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test EPUB</dc:title><dc:language>de</dc:language><dc:identifier id="id">test</dc:identifier></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>')
            z.writestr('OEBPS/chapter.xhtml','<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Ein Buch</h1>'+('<p>Eine lesbare Geschichte mit mehreren Seiten.</p>'*100)+'</body></html>')
        key=reader.import_file(self.library,path,self.job);book=self.library.get(key);self.assertGreater(book['pages'],1)
        data=reader.worker(self.job,'page',self.library.asset(book['asset']),page=0);self.assertIn('Ein Buch',data['text'])
        page=self.root/'article.html';page.write_text('<h1>Artikel</h1><script>private-script</script><p>Lesbar</p><img src="file:///private">')
        key=reader.import_file(self.library,page,self.job);book=self.library.get(key);body=self.library.asset(book['asset']).read_text()
        self.assertNotIn('private-script',body);self.assertNotIn('<img',body)
        self.assertIn('Lesbar',reader.worker(self.job,'page',self.library.asset(book['asset']))['text'])
        with patch('reader_data.zipfile.ZipFile') as archive:
            entry=zipfile.ZipInfo('large');entry.file_size=300*1024**2;archive.return_value.__enter__.return_value.infolist.return_value=[entry]
            with self.assertRaises(ValueError):reader.validate_epub(path)

    def test_native_notes_reopen_knowledge_and_text_selection(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtTest import QTest
        from tools_reader import Reader
        from lumen_store import Store
        app=QApplication.instance() or QApplication([])
        path=self.root/'reading.txt';path.write_text('Eine markierte Stelle.\nEin eigener Gedanke.')
        def ready(window):
            for _ in range(150):
                QTest.qWait(20)
                if window.data and not window.job:return
            self.fail('Reader did not finish rendering')
        with patch.dict(os.environ,{'LUMEN_DATA':str(self.root/'knowledge')}):
            from wissen_data import activate
            activate(Store())
            window=Reader(self.root/'ui');window.open_file(str(path));ready(window);window.canvas.select_all();window.mark()
            window.note.setPlainText('Meine Randnotiz');window.save()
            window._interop_focus=window.note
            with patch('interop_ui.launch') as launch:
                window.remember();ready(window)
            from interop_data import Registry
            request=Registry(self.root/'ui').request(launch.call_args.args[1][1])
            self.assertEqual(request['action'],'wissen.import')
            self.assertEqual(request['payload']['source']['position']['page'],0)
            self.assertIn('Meine Randnotiz',request['payload']['text'])
            key=window.current;window.close()
            again=Reader(self.root/'ui');again.focus_record(key);ready(again)
            self.assertEqual(again.library.get(key)['notes'][0]['note'],'Meine Randnotiz')
            again.mode.setCurrentIndex(1);again.text.selectAll();again.mark();self.assertEqual(len(again.library.get(key)['notes']),2);again.close()
            window.deleteLater();again.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
