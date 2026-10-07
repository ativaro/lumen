"""Migration regressions, including independent encrypted files and crypto vectors."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PySide6.QtWidgets import QApplication
from lumen_pdf import Document,Writer,Name,Ref,Stream,UnsupportedPDF
from lumen_pdf_text import TextWriter
from test_pdf_fixtures import document


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_password_files_primitives_and_indirect_null_filters(self):
        from lumen_pdf_security import crypto,PasswordRequired,Security
        key=bytes.fromhex('603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4')
        iv=bytes.fromhex('000102030405060708090a0b0c0d0e0f');plain=bytes.fromhex('6bc1bee22e409f96e93d7e117393172a')
        self.assertEqual(crypto('aes-256-cbc',key,plain,iv,encrypt=True).hex(),'f58c4c04d6e5f1ba779eabfb5f7bfbd6')
        self.assertEqual(crypto('rc4',bytes.fromhex('0102030405'),bytes(16)).hex(),'b2396305f03dc027ccc3524a0a1118a8')
        for file in (Path(__file__).parent/'fixtures/pdf').glob('*.pdf'):
            for password in ('test-reader-pass','test-owner-pass'):
                doc=Document(file,password=password);self.assertEqual(len(doc),2);self.assertEqual(doc.page(0).text(),'First page')
            with self.assertRaises(PasswordRequired):Document(file,password='wrong')
            with self.assertRaises(PasswordRequired):Document(file)
        handler=Security.__new__(Security);handler.metadata=True;handler.methods={'StmF':'Identity','StrF':'Identity'}
        for value in (None,Ref(9)):
            result=handler.value(Stream({'Filter':value},b'abc'),Ref(1),lambda v:Name('FlateDecode') if v==Ref(9) else v)
            self.assertEqual(result.raw,b'abc')

    def test_unicode_styles_fallback_and_defined_text_state(self):
        samples=['office affinity ffi ff fi ﬃ','A 𝕏 𝕐 ℤ end','á è ẍ','é á̧ test','Grüezi café Ελληνικά']
        for sample in samples:
            writer=Writer();page=writer.add_page(600,180);text=TextWriter(writer);text.box(page,[20,20,580,160],[sample],[dict(size=20)]);text.finalize()
            self.assertEqual(Document(writer.bytes()).page(0).text(),sample)
        writer=Writer();page=writer.add_page(600,180);text=TextWriter(writer)
        text.box(page,[20,20,580,160],['Bold ','normal ','again'],[dict(size=20,bold=True),dict(size=20),dict(size=20,bold=True)]);text.finalize()
        self.assertEqual(Document(writer.bytes()).page(0).text(),'Bold normal again');self.assertTrue(Document(writer.bytes()).page(0).spans[0]['bold'])
        with self.assertRaises(UnsupportedPDF):text.box(page,[20,20,580,160],['مرحبا'],[dict(size=20)])
        import translate_pdf
        with tempfile.TemporaryDirectory() as folder:
            for index,transform in enumerate((b'1 0 0 1 120 0 cm',b'2 0 0 2 0 0 cm',b'3 Tr')):
                writer=document();page=writer.objects[writer.page_refs[0].number-1];page['Contents']=writer.stream(transform+b' BT /F1 20 Tf 30 150 Td (Hello) Tj ET')
                source=Path(folder)/f'{index}.pdf';writer.save(source);manifest=translate_pdf.inspect(source);output=Path(folder)/f'out{index}.pdf'
                translate_pdf.write(manifest,{'0':['Hallo']},output);result=Document(output).page(0)
                self.assertEqual(result.text(),'Hallo');self.assertLess(abs(result.words[0][0]-manifest['segments'][0]['rect'][0]),1)
                self.assertEqual(result.spans[0]['mode'],0)

    def test_annotations_do_not_inherit_page_transform_or_clip(self):
        writer=document(['Linked']);page=writer.objects[writer.page_refs[0].number-1];page['Annots']=[writer.add({'Subtype':Name('Link'),'Rect':[1,1,10,10],'Dest':b'named-page'})]
        with self.assertRaises(UnsupportedPDF):Writer().copy_page(Document(writer.bytes()),0)
        for content in (b'1 0 0 1 100 0 cm',b'0 0 5 5 re W n'):
            writer=Writer();page=writer.add_page(200,200,content);appearance=writer.stream(b'1 0 0 rg 0 0 20 20 re f',Type=Name('XObject'),Subtype=Name('Form'),BBox=[0,0,20,20])
            page['Annots']=[writer.add({'Type':Name('Annot'),'Subtype':Name('Stamp'),'Rect':[20,20,40,40],'AP':{'N':appearance}})]
            image=Document(writer.bytes()).page(0).render();self.assertEqual(image.pixelColor(30,170).name(),'#ff0000');self.assertEqual(image.pixelColor(130,170).name(),'#ffffff')

    def test_legacy_anchors_preserve_notes_and_rebuild_utf16_selection(self):
        from reader_data import reanchor,ENGINE
        writer=Writer();page=writer.add_page(600,180);text=TextWriter(writer);text.box(page,[20,20,580,160],['𝕏 before Hello world'],[dict(size=20)]);text.finalize();doc=Document(writer.bytes())
        note=dict(id='old',page=0,text='Hello world',note='private note',words=[],selection=[5,16]);result=reanchor(doc,[note])[0]
        self.assertEqual(result['selection'],[10,21]);self.assertEqual(result['legacy_anchor']['selection'],[5,16]);self.assertEqual(result['note'],'private note');self.assertEqual(result['engine'],ENGINE)
        bounded=reanchor(Document(document(['planet net']).bytes()),[dict(note,text='net',selection=[7,10])])[0];self.assertEqual(bounded['selection'],[7,10])
        duplicate=Document(document(['Hello world Hello world']).bytes());result=reanchor(duplicate,[note])[0]
        self.assertEqual(result['anchor_status'],'unresolved');self.assertEqual(result['words'],[]);self.assertEqual(result['selection'],[]);self.assertEqual(result['text'],note['text'])
        with tempfile.TemporaryDirectory() as folder:
            from lumen_reflow import ReflowBook
            path=Path(folder)/'book.txt';path.write_text('Hello world\n'+'Another paragraph.\n'*100)
            with ReflowBook(path) as book:
                result=reanchor(book,[dict(note,page=999)],True)[0];self.assertEqual(result['page'],0);self.assertEqual(result['legacy_anchor']['page'],999)

    def test_full_text_counts_characters_and_worker_keeps_inherited_limits(self):
        from tools_data import document_text
        from tools_ui import Job
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'unicode.pdf';document(['ä'*2000]*32+['FINAL_SENTINEL']).save(path)
            text=document_text(path,Job(lambda _:None));self.assertIn('FINAL_SENTINEL',text);self.assertEqual(text.count('ä'),64000)
            too_long=Path(folder)/'too-long.pdf';document(['ä'*2000]*61).save(too_long)
            with self.assertRaises(ValueError):document_text(too_long,Job(lambda _:None))
            code='import resource;resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));from lumen_pdf_worker import limits;limits();assert resource.getrlimit(resource.RLIMIT_AS)==(1024**3,1024**3)'
            subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).parent,check=True,capture_output=True,timeout=10)


if __name__=='__main__':unittest.main()
