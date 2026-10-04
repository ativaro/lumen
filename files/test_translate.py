"""Translate contracts with synthetic text/PDFs and no personal/provider data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import translate_data as data
import translate_pdf as pdf
from PySide6.QtCore import QObject, Signal, QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


class FakeBackend(QObject):
    completed = Signal(bool, str)
    instances = []
    def __init__(self,*args,**kwargs):
        super().__init__(); self.busy=False; self.sent=[];self.instances.append(self)
        assert kwargs['project_config'] is False
    def send(self,prompt,**kwargs):
        self.sent.append((prompt,kwargs)); self.busy=True
        segments=json.loads(prompt.split('<source_data>\n')[1].split('\n</source_data>')[0])
        for segment in segments:
            segment['parts']=[p.replace('Helo','Hello') for p in segment['parts']]
        QTimer.singleShot(20,lambda:self.finish(json.dumps(dict(segments=segments))))
    def finish(self,answer):
        if self.busy:self.busy=False;self.completed.emit(True,answer)
    def stop(self):self.busy=False;self.completed.emit(False,'Cancelled')
    def shutdown(self):self.busy=False


class TextTest(unittest.TestCase):
    def test_paragraphs_whitespace_and_long_chunks_roundtrip(self):
        for text in ('  Helo!\n\n\n  Next line.\n', 'a '*5800, '\n\nHelo\n\n'):
            segments=data.text_segments(text)
            self.assertEqual(data.joined(segments,{s['id']:s['parts'] for s in segments}),text)
            self.assertTrue(all(sum(len(p) for s in batch for p in s['parts'])<=6000 for batch in data.batches(segments)))
        for text in ('','  ','a'*12001,'bad\0data'):
            with self.assertRaises(ValueError):data.text_segments(text)

    def test_modes_and_strict_complete_response(self):
        segments=data.text_segments('One\n\nTwo')
        answer=dict(segments=[dict(id=s['id'],parts=s['parts']) for s in reversed(segments)])
        self.assertEqual(len(data.parse_result(json.dumps(answer),segments)),2)
        for bad in ({},dict(segments=answer['segments'][:1]),dict(segments=answer['segments']*2),dict(segments=[dict(id='0',parts=[''])])):
            with self.assertRaises(ValueError):data.parse_result(json.dumps(bad),segments)
        with self.assertRaises(ValueError):data.options(source='de',target='de')
        correct=data.prompt(segments,data.options(source='de',target='de',mode='correct',style='concise'))
        self.assertIn('Correct ONLY',correct);self.assertNotIn('Tone: concise',correct)
        self.assertIn('SAME language',data.prompt(segments,data.options(mode='rewrite',style='formal')))


class PDFTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        import pymupdf
        self.pdf=pymupdf
        self.source=self.root/'source.pdf'
        with pymupdf.open() as doc:
            page=doc.new_page(width=450,height=500)
            page.insert_text((40,60),'Hello world',fontsize=16)
            page.draw_rect((35,100,400,250),color=(0,0,1))
            image=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,12,12),False);image.clear_with(90)
            page.insert_image((40,300,130,390),pixmap=image)
            page.insert_link(dict(kind=pymupdf.LINK_URI,**{'from':pymupdf.Rect(40,42,125,65),'uri':'https://example.org'}))
            doc.save(self.source)
    def translations(self,manifest):return {s['id']:['Hallo Welt']*len(s['parts']) for s in manifest['segments']}
    def test_layout_images_lines_links_and_original_preserved(self):
        before=self.source.read_bytes();manifest=pdf.inspect(self.source);output=self.root/'translated.pdf'
        report=pdf.write(manifest,self.translations(manifest),output)
        self.assertEqual(self.source.read_bytes(),before);self.assertEqual(report['pages'],1)
        with self.pdf.open(output) as doc,self.pdf.open(self.source) as source:
            page=doc[0]
            self.assertIn('Hallo Welt',page.get_text());self.assertNotIn('Hello world',page.get_text())
            self.assertEqual(page.rect,source[0].rect);self.assertEqual(len(page.get_images()),1)
            self.assertEqual([{k:v for k,v in d.items() if k!='seqno'} for d in page.get_drawings()], [{k:v for k,v in d.items() if k!='seqno'} for d in source[0].get_drawings()])
            self.assertEqual([l.get('uri') for l in page.get_links()],['https://example.org'])
        with self.assertRaises(ValueError):pdf.write(manifest,self.translations(manifest),output)
    def test_missing_output_overflow_and_changed_source_never_publish(self):
        manifest=pdf.inspect(self.source);output=self.root/'new.pdf'
        with self.assertRaises(ValueError):pdf.write(manifest,{},output)
        huge={s['id']:['word '*5000]*len(s['parts']) for s in manifest['segments']}
        with self.assertRaises(ValueError):pdf.write(manifest,huge,output)
        self.assertFalse(output.exists());self.assertFalse(list(self.root.glob('.lumen-*')))
        self.source.write_bytes(self.source.read_bytes()+b'\n')
        with self.assertRaises(ValueError):pdf.write(manifest,self.translations(manifest),output)
        self.assertFalse(output.exists())
    def test_scans_and_annotations_refused(self):
        scan=self.root/'scan.pdf'
        with self.pdf.open() as doc:
            page=doc.new_page();image=self.pdf.Pixmap(self.pdf.csRGB,self.pdf.IRect(0,0,12,12),False);image.clear_with(90)
            page.insert_image((20,20,200,200),pixmap=image);doc.save(scan)
        with self.assertRaises(ValueError):pdf.inspect(scan)
        annotated=self.root/'annotated.pdf'
        with self.pdf.open(self.source) as doc:
            doc[0].add_text_annot((40,40),'Note');doc.save(annotated)
        with self.assertRaises(ValueError):pdf.inspect(annotated)


class NativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def dispose(self,w):
        w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def wait(self,predicate):
        for _ in range(400):
            QTest.qWait(20)
            if predicate():return
        self.fail('Operation did not finish')
    def test_native_correction_persistence_and_cancel(self):
        from tools_translate import Translate
        with patch('assistant_backend.OpenCodeBackend',FakeBackend):
            w=Translate(self.root);w.error=lambda message:self.fail(message)
            w.input.setPlainText('Helo!\n\nMy writing.');w.mode.setCurrentIndex(w.mode.findData('correct'))
            self.assertFalse(w.style.isEnabled());self.assertFalse(w.target_language.isEnabled())
            w.run_translation();self.wait(lambda:not w.engine.busy)
            self.assertEqual(w.output.toPlainText(),'Hello!\n\nMy writing.')
            self.assertEqual(w.engine.sent[0][1],dict(proposal=True,title='Lumen Translate'))
            key=w.current;self.dispose(w)
            w=Translate(self.root);self.assertEqual(len(w.library.all()),1)
            self.assertEqual(w.current,key);self.assertEqual(w.output.toPlainText(),'Hello!\n\nMy writing.')
            w.input.setPlainText('Helo again');self.assertEqual(w.output.toPlainText(),'')
            w.run_translation();w.cancel();QTest.qWait(50)
            self.assertFalse(w.engine.busy);self.assertTrue(w.body.isEnabled());self.assertEqual(w.output.toPlainText(),'')
            self.dispose(w)
    def test_pdf_native_import_preview_process_and_export(self):
        import pymupdf
        from tools_translate import Translate
        source=self.root/'input.pdf'
        with pymupdf.open() as doc:
            doc.new_page().insert_text((40,60),'Helo world');doc.save(source)
        before=source.read_bytes()
        with patch('assistant_backend.OpenCodeBackend',FakeBackend):
            w=Translate(self.root/'tools');w.error=lambda message:self.fail(message);w.show()
            w.open_file(str(source))
            self.wait(lambda:not w.job and not w.pdf_original.pixmap().isNull())
            self.assertEqual(w.tabs.currentIndex(),1)
            w.run_translation()
            self.wait(lambda:bool(w.library.get(w.current).get('pdf_result')) and not w.job and not w.pdf_result.pixmap().isNull())
            target=self.root/'export.pdf'
            with patch('tools_translate.QFileDialog.getSaveFileName',return_value=(str(target),'PDF')):
                w.export_pdf();self.wait(lambda:not w.job)
            self.assertEqual(source.read_bytes(),before)
            with pymupdf.open(target) as doc:self.assertIn('Hello world',doc[0].get_text())
            self.dispose(w)

    def test_mcp_processing_is_bounded_and_does_not_make_drafts(self):
        from lumen_mcp_tools import invoke,DEFINITIONS
        with patch('assistant_backend.OpenCodeBackend',FakeBackend):
            result=invoke('lumen_translate_text',dict(text='Helo',mode='correct'))
            self.assertEqual(result['text'],'Hello')
        self.assertTrue(DEFINITIONS['lumen_translate_text']['annotations']['openWorldHint'])
        self.assertTrue(DEFINITIONS['lumen_translate_pdf']['action'])
        self.assertEqual(invoke('lumen_translate_options',{})['max_text'],12000)
    def test_text_handoff_prepares_draft_without_model_call(self):
        from interop_targets import apply,available
        from tools_ui import Job
        from tools_data import Library
        payload=dict(title='Message',text='Helo',paths=[],source=dict(app='reader',id='r',kind='record',title='Message'),source_url='lumen://object/'+'a'*32)
        self.assertIn('translate.import',available(payload))
        with patch('assistant_backend.OpenCodeBackend') as backend:
            result=apply('translate.import',payload,dict(title='Message',mode='copy',token='test'),Job(lambda _:None),root=self.root)
            backend.assert_not_called()
        record=Library('translate',self.root).get(result['id'])
        self.assertEqual(record['source'],'Helo');self.assertEqual(record['result'],'')
        self.assertEqual(record['interop_sources'],[payload['source_url']])


if __name__=='__main__':unittest.main()
