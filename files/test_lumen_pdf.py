"""Synthetic format checks; fixture bytes are built without a PDF library."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zlib
import lumen_pdf as pdf


def fixture(objects):
    result=bytearray(b'%PDF-1.7\n'); offsets=[0]
    for number,value in enumerate(objects,1):
        offsets.append(len(result)); result.extend(f'{number} 0 obj\n'.encode()+value+b'\nendobj\n')
    offset=len(result); result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for position in offsets[1:]: result.extend(f'{position:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n'.encode())
    return bytes(result)


def plain(content=b'BT /F1 18 Tf 40 300 Td (Hello Lumen) Tj ET',rotation=0):
    return fixture([
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 400 400] /Resources << /Font << /F1 5 0 R >> >> >>',
        f'<< /Type /Page /Parent 2 0 R /Rotate {rotation} /Contents 4 0 R >>'.encode(),
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
    ])


class PDFTest(unittest.TestCase):
    def test_syntax_revisions_and_stream_boundaries(self):
        syntax=pdf.Syntax(b'<< /A#20B [(escaped\\(text\\)\\053) <123> -1.25 true null] /Ref 2 0 R >>')
        self.assertEqual(pdf.Syntax(b'2 % comment\n0 % comment\nR').value(),pdf.Ref(2))
        result=syntax.value(); self.assertEqual(result['A B'],[b'escaped(text)+',b'\x12\x30',-1.25,True,None]); self.assertEqual(result['Ref'],pdf.Ref(2))
        original=plain(b'BT /F1 18 Tf 40 300 Td (endstream 99 0 obj Secret) Tj ET')
        doc=pdf.Document(original); self.assertEqual(len(doc),1); self.assertIn(b'Secret',doc.contents(0))
        old=int(original.split(b'startxref\n')[-1].splitlines()[0]); offset=len(original)
        update=b'3 0 obj\n<< /Type /Page /Parent 2 0 R /Rotate 90 /Contents 4 0 R >>\nendobj\n'; xref=offset+len(update)
        updated=original+update+f'xref\n3 1\n{offset:010d} 00000 n \ntrailer\n<< /Size 6 /Root 1 0 R /Prev {old} >>\nstartxref\n{xref}\n%%EOF\n'.encode()
        self.assertEqual(pdf.Document(updated).pages[0]['Rotate'],90)
        for broken in (original[:-10],original.replace(b'/Count 1',b'/Count 2'),original.replace(b'/Kids [3 0 R]',b'/Kids [2 0 R]')):
            with self.assertRaises(pdf.PDFError): pdf.Document(broken).contents(0)
        with self.assertRaises(pdf.PDFError): pdf.Syntax(b'['*70+b']'*70).value()
        with self.assertRaises(pdf.PDFError): pdf.Syntax(b'<< /A 1 /A 2 >>').value()
        with patch.object(pdf,'MAX_STREAM',32):
            with self.assertRaises(pdf.PDFError): pdf.decoded(pdf.Stream({'Filter':pdf.Name('FlateDecode')},zlib.compress(b'x'*10000)))

    def test_filters_predictors_and_truncated_streams(self):
        import base64
        payload=b'PDF filters\x00\xff'*25
        for name,encoded in (
            ('FlateDecode',zlib.compress(payload)),
            ('ASCIIHexDecode',payload.hex().encode()+b'>'),
            ('ASCII85Decode',base64.a85encode(payload)+b'~>'),
        ):
            self.assertEqual(pdf.decoded(pdf.Stream({'Filter':pdf.Name(name)},encoded)),payload)
        self.assertEqual(pdf.decoded(pdf.Stream({'Filter':pdf.Name('RunLengthDecode')},b'\x02ABC\xfeZ\x80')),b'ABCZZZ')
        # Literal-only LZW stream exercises each code-width transition without
        # sharing the decoder's dictionary construction logic.
        expected=bytes(range(256))*12
        for early in (0,1):
            bits='100000000'; width=9
            for position,value in enumerate(expected,1):
                bits+=format(value,f'0{width}b')
                if position==(1<<width)-257-early and width<12: width+=1
            bits+=format(257,f'0{width}b'); bits+='0'*(-len(bits)%8)
            encoded=int(bits,2).to_bytes(len(bits)//8,'big')
            self.assertEqual(pdf.decoded(pdf.Stream({'Filter':pdf.Name('LZWDecode'),'DecodeParms':{'EarlyChange':early}},encoded)),expected)
        raw=bytes([1,10,10,10,2,5,5,5])
        stream=pdf.Stream({'Filter':pdf.Name('FlateDecode'),'DecodeParms':{'Predictor':15,'Columns':3}},zlib.compress(raw))
        self.assertEqual(pdf.decoded(stream),bytes([10,20,30,15,25,35]))
        # Complete data without its closing checksum is read; data cut short is refused.
        for missing in (1,4): self.assertEqual(pdf.decoded(pdf.Stream({'Filter':pdf.Name('FlateDecode')},zlib.compress(payload)[:-missing])),payload)
        with self.assertRaises(pdf.PDFError): pdf.decoded(pdf.Stream({'Filter':pdf.Name('FlateDecode')},zlib.compress(payload)[:-6]))
        with self.assertRaises(pdf.PDFError): pdf.decoded(pdf.Stream({'Filter':pdf.Name('RunLengthDecode')},b'\x7fA'))

    def test_object_and_xref_streams(self):
        catalog=b'<< /Type /Catalog /Pages 2 0 R >>'; tree=b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>'
        header=f'1 0 2 {len(catalog)+1} '.encode(); contents=header+catalog+b' '+tree
        result=bytearray(b'%PDF-1.7\n'); positions={}
        for number,body in ((3,b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] >>'),(4,b'<< /Type /ObjStm /N 2 /First '+str(len(header)).encode()+b' /Length '+str(len(contents)).encode()+b' >>\nstream\n'+contents+b'\nendstream')):
            positions[number]=len(result); result.extend(f'{number} 0 obj\n'.encode()+body+b'\nendobj\n')
        positions[5]=len(result)
        entries=[(0,0,65535),(2,4,0),(2,4,1),(1,positions[3],0),(1,positions[4],0),(1,positions[5],0)]
        data=b''.join(bytes([kind])+a.to_bytes(4,'big')+b.to_bytes(2,'big') for kind,a,b in entries); compressed=zlib.compress(data)
        result.extend(b'5 0 obj\n<< /Type /XRef /Size 6 /W [1 4 2] /Root 1 0 R /Filter /FlateDecode /Length '+str(len(compressed)).encode()+b' >>\nstream\n'+compressed+b'\nendstream\nendobj\n')
        result.extend(f'startxref\n{positions[5]}\n%%EOF\n'.encode())
        document=pdf.Document(bytes(result)); self.assertEqual(len(document),1); self.assertEqual(document.pages[0]['MediaBox'],[0,0,200,300])

    def test_writer_page_copy_and_exclusive_export(self):
        source=pdf.Document(plain()); writer=pdf.Writer(); writer.copy_page(source,0,90); writer.copy_page(source,0)
        output=pdf.Document(writer.bytes()); self.assertEqual(len(output),2); self.assertEqual(output.pages[0]['Rotate'],90); self.assertEqual(output.contents(1),source.contents(0))
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'copy.pdf'; writer.save(target); expected=target.read_bytes()
            with self.assertRaises(FileExistsError): writer.save(target)
            self.assertEqual(target.read_bytes(),expected); self.assertEqual(list(Path(tmp).iterdir()),[target])
        with patch.dict('sys.modules',{'pymupdf':None,'fitz':None,'pypdf':None,'pypdfium2':None,'reportlab':None,'PySide6.QtPdf':None}):
            self.assertEqual(len(pdf.Document(writer.bytes())),2)



class RenderingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication(['test-lumen-pdf'])

    def test_render_text_rotation_images_and_form_state(self):
        from lumen_pdf_page import Page, png
        from PySide6.QtGui import QImage
        for rotation in (0,90,180,270):
            page=Page(pdf.Document(plain(rotation=rotation)),0)
            self.assertIn('Hello',page.text()); image=page.render(1.5)
            self.assertEqual(image.width(),600); self.assertTrue(png(image).startswith(b'\x89PNG'))
            for word in page.words:
                self.assertTrue(0<=word[0]<word[2]<=page.width)
                self.assertTrue(0<=word[1]<word[3]<=page.height)
        writer=pdf.Writer(); form=writer.stream(b'0 0 20 20 re f',Type=pdf.Name('XObject'),Subtype=pdf.Name('Form'),BBox=[0,0,20,20])
        writer.add_page(100,100,b'1 0 0 rg q 1 0 0 1 10 10 cm /Form Do Q',{'XObject':{'Form':form}})
        image=Page(pdf.Document(writer.bytes()),0).render()
        self.assertEqual(image.pixelColor(15,85).name(),'#ff0000')
        from lumen_pdf_worker import raster_page
        writer=pdf.Writer(); raster=QImage(7,9,QImage.Format.Format_RGB888); raster.fill(0xff22aa66); raster_page(writer,raster,70,90)
        image=Page(pdf.Document(writer.bytes()),0).render()
        self.assertEqual(image.pixelColor(35,45).name(),'#22aa66')

    def test_redaction_no_original_content_and_no_clobber(self):
        from lumen_pdf_page import Page
        from lumen_pdf_worker import export,signature
        secret=plain(b'BT /F1 18 Tf 40 320 Td (SECRET) Tj 0 -120 Td (Visible) Tj ET')
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf'; target=Path(tmp)/'redacted.pdf'; source.write_bytes(secret)
            recipe={'path':str(source),'page':0,'rotation':0,'boxes':[[.07,.13,.6,.25]],'stamp':signature(source)}
            export([recipe],target,150); document=pdf.Document(target); page=Page(document,0)
            self.assertEqual(page.text(),''); self.assertEqual(page.render().pixelColor(50,80).name(),'#000000')
            for number,(kind,_,generation) in document.xref.items():
                if kind!=1: continue
                value=document.resolve(pdf.Ref(number,generation))
                if isinstance(value,pdf.Stream): self.assertNotIn(b'SECRET',document.decode(value))
            self.assertNotIn(b'SECRET',target.read_bytes()); self.assertEqual(source.read_bytes(),secret)
            limited=Path(tmp)/'too-large.pdf'
            with patch.object(pdf,'MAX_STREAM',4096):
                with self.assertRaises(pdf.PDFError): export([recipe],limited,150)
            self.assertFalse(limited.exists())
            with self.assertRaises(FileExistsError): export([recipe],target)
            source.write_bytes(plain()); output=Path(tmp)/'stale.pdf'
            with self.assertRaises(pdf.PDFError): export([recipe],output)
            self.assertFalse(output.exists())

    def test_redaction_drops_shared_unused_resources_from_other_pages(self):
        from lumen_pdf_worker import export,signature
        from lumen_pdf_page import Page
        writer=pdf.Writer(); font=writer.add({'Type':pdf.Name('Font'),'Subtype':pdf.Name('Type1'),'BaseFont':pdf.Name('Helvetica')})
        hidden=writer.stream(b'BT /F1 18 Tf 10 50 Td (SECRET) Tj ET',Type=pdf.Name('XObject'),Subtype=pdf.Name('Form'),BBox=[0,0,100,100],Resources={'Font':{'F1':font}})
        shared={'Font':{'F1':font},'XObject':{'Hidden':hidden}}
        writer.add_page(100,100,b'/Hidden Do',shared)
        writer.add_page(100,100,b'BT /F1 18 Tf 10 50 Td (Visible) Tj ET',shared)
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'shared.pdf'; target=Path(tmp)/'safe.pdf'; writer.save(source)
            pages=[dict(path=str(source),page=0,rotation=0,boxes=[[0,0,1,1]],stamp=signature(source)),dict(path=str(source),page=1,rotation=0,boxes=[],stamp=signature(source))]
            export(pages,target,150); result=pdf.Document(target)
            for number,(kind,_,generation) in result.xref.items():
                if kind!=1: continue
                value=result.resolve(pdf.Ref(number,generation))
                if isinstance(value,pdf.Stream): self.assertNotIn(b'SECRET',result.decode(value))
            self.assertEqual(Page(result,0).render().pixelColor(30,30).name(),'#000000')
            self.assertEqual(Page(result,1).text(),'')

    def test_unsupported_features_fail_and_expansion_budgets_apply_early(self):
        from lumen_pdf_page import Page,unicode_map
        document=pdf.Document(plain()); document.catalog['OCProperties']={pdf.Name('OCGs'):[pdf.Ref(99)]}
        with self.assertRaises(pdf.UnsupportedPDF): pdf.Writer().copy_page(document,0)
        with self.assertRaises(pdf.UnsupportedPDF): Page(pdf.Document(plain(b'0 0 m 2 0 0 2 0 0 cm 1 1 l S')),0)
        with self.assertRaises(pdf.UnsupportedPDF): Page(pdf.Document(plain(b'BI /W 1 /H 1 ID xx EI')),0)
        with patch.object(pdf,'MAX_STREAM',16),patch.object(pdf.base64,'a85decode',side_effect=AssertionError('must reject before allocating')):
            with self.assertRaises(pdf.PDFError): pdf.decoded(pdf.Stream({'Filter':pdf.Name('ASCII85Decode')},b'z'*10+b'~>'))
        document=pdf.Document(plain()); expansion=b'1 beginbfrange <0000> <07ff> <'+b'0041'*2048+b'> endbfrange'
        with self.assertRaises(pdf.PDFError): unicode_map(document,pdf.Stream({},expansion))
        with self.assertRaises(pdf.UnsupportedPDF): pdf.decoded(pdf.Stream({'F':b'/etc/passwd'},b''))

    def test_words_follow_replacement_text_and_gaps_without_a_space(self):
        from lumen_pdf_page import Page,symbol_cmap
        def text(content): return Page(pdf.Document(plain(content)),0).text()
        self.assertEqual(text(b'BT /F1 18 Tf 40 300 Td /Span << /ActualText (fi) >> BDC (xy) Tj EMC ( ok) Tj ET'),'fi ok')
        # A zero-width replacement makes the glyphs unread instead of leaving an invisible character in the word.
        self.assertEqual(text(b'BT /F1 18 Tf 40 300 Td (a) Tj /Span << /ActualText <FEFF200B> >> BDC (x) Tj EMC (b) Tj ET'),'a b')
        self.assertEqual(text(b'BT /F1 20 Tf 40 300 Td [(Hello) -300 (World)] TJ ET'),'Hello World')
        self.assertEqual(text(b'BT /F1 20 Tf 40 300 Td [(Hel) -40 (lo)] TJ ET'),'Hello')
        # A symbolic TrueType font names its glyphs by code in its own character map.
        import struct
        byte=struct.pack('>HH',0,1)+struct.pack('>HHI',1,0,12)+struct.pack('>HHH',0,262,0)+bytes([0,5,6])+bytes(253)
        self.assertEqual(symbol_cmap(byte),(1,{1:5,2:6}))
        segments=struct.pack('>HHHHHHH',4,32,0,4,4,1,0)+struct.pack('>HH',0xF002,0xFFFF)+struct.pack('>H',0)+struct.pack('>HH',0xF001,0xFFFF)+struct.pack('>HH',(3-0xF001)&0xFFFF,1)+struct.pack('>HH',0,0)
        self.assertEqual(symbol_cmap(struct.pack('>HH',0,1)+struct.pack('>HHI',3,0,12)+segments),(3,{0xF001:3,0xF002:4}))
        self.assertIsNone(symbol_cmap(b'\0\0\0\1\0\3'))

    def test_worker_runs_without_other_pdf_modules(self):
        import json,subprocess,sys
        from lumen_pdf_worker import signature
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.pdf'; source.write_bytes(plain())
            request=json.dumps({'action':'page','path':str(source),'page':0})
            code="import sys;sys.modules.update({name:None for name in ('pymupdf','fitz','pypdf','pypdfium2','reportlab','PySide6.QtPdf')});import lumen_pdf_worker;sys.exit(lumen_pdf_worker.main())"
            result=subprocess.run([sys.executable,'-c',code],input=request,text=True,capture_output=True,timeout=30,cwd=Path(__file__).parent)
            self.assertEqual(result.returncode,0,result.stderr); payload=json.loads(result.stdout)
            self.assertEqual(payload['text'],'Hello Lumen'); self.assertEqual(payload['pages'],1); self.assertEqual(payload['backend'],'lumen-pdf')


if __name__=='__main__': unittest.main()
