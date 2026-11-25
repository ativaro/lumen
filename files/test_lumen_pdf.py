"""PDF reading, drawing and export through the document core, on synthetic files built without a PDF library."""
import tempfile
import unittest
from pathlib import Path
import zlib

from document_workshop import export
from lumen_office import signature
from test_pdf_fixtures import Name, Writer, info, pages, render, saved, streams, text


def fixture(objects):
    result=bytearray(b'%PDF-1.7\n'); offsets=[0]
    for number,value in enumerate(objects,1):
        offsets.append(len(result)); result.extend(f'{number} 0 obj\n'.encode()+value+b'\nendobj\n')
    offset=len(result); result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for position in offsets[1:]: result.extend(f'{position:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n'.encode())
    return bytes(result)


def plain(content=b'BT /F1 18 Tf 40 300 Td (Hello Lumen) Tj ET',rotation=0,box=b'[0 0 400 400]'):
    return fixture([
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox '+box+b' /Resources << /Font << /F1 5 0 R >> >> >>',
        f'<< /Type /Page /Parent 2 0 R /Rotate {rotation} /Contents 4 0 R >>'.encode(),
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
    ])


def refused(data):
    try: info(data)
    except ValueError: return True
    return False


class PDFTest(unittest.TestCase):
    def test_revisions_stream_boundaries_and_broken_files(self):
        original=plain(b'BT /F1 18 Tf 40 300 Td (endstream 99 0 obj Secret) Tj ET',box=b'[0 0 400 300]')
        self.assertIn('Secret',text(original))
        old=int(original.split(b'startxref\n')[-1].splitlines()[0]); offset=len(original)
        update=b'3 0 obj\n<< /Type /Page /Parent 2 0 R /Rotate 90 /Contents 4 0 R >>\nendobj\n'; xref=offset+len(update)
        updated=original+update+f'xref\n3 1\n{offset:010d} 00000 n \ntrailer\n<< /Size 6 /Root 1 0 R /Prev {old} >>\nstartxref\n{xref}\n%%EOF\n'.encode()
        # The later revision turns the page: it reads as 300 wide and 400 high.
        self.assertEqual((pages(updated)[0]['width'],pages(updated)[0]['height']),(300,400))
        # A cut end is rebuilt from the objects, as other readers do; the text that looks like an object stays text.
        self.assertIn('endstream 99 0 obj Secret',text(original[:-10]))
        for broken in (original.replace(b'/Count 1',b'/Count 2'),original.replace(b'/Kids [3 0 R]',b'/Kids [2 0 R]')):
            self.assertTrue(refused(broken))

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
        found=info(bytes(result)); self.assertEqual(found['pages'],1); self.assertEqual(found['content'][0]['box'],[0,0,200,300])

    def test_export_copies_turns_and_never_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf'; source.write_bytes(plain(box=b'[0 0 400 300]')); target=Path(tmp)/'copy.pdf'
            item=dict(path=str(source),page=0,rotation=0,boxes=[],stamp=signature(source))
            export([dict(item,rotation=90),item],target)
            result=pages(target); self.assertEqual([(p['width'],p['height']) for p in result],[(300,400),(400,300)])
            self.assertEqual(text(target,1),'Hello Lumen')
            expected=target.read_bytes()
            with self.assertRaises(FileExistsError): export([item],target)
            self.assertEqual(target.read_bytes(),expected); self.assertEqual(sorted(Path(tmp).iterdir()),[target,source])

    def test_render_text_rotation_and_form_state(self):
        for rotation in (0,90,180,270):
            data=plain(rotation=rotation); page=pages(data)[0]
            self.assertIn('Hello',text(data)); self.assertEqual(render(data,1.5).width(),600)
            for word in page['words']:
                self.assertTrue(0<=word[0]<word[2]<=page['width'])
                self.assertTrue(0<=word[1]<word[3]<=page['height'])
        writer=Writer(); form=writer.stream(b'0 0 20 20 re f',Type=Name('XObject'),Subtype=Name('Form'),BBox=[0,0,20,20])
        writer.add_page(100,100,b'1 0 0 rg q 1 0 0 1 10 10 cm /Form Do Q',{'XObject':{'Form':form}})
        self.assertEqual(render(writer.bytes()).pixelColor(15,85).name(),'#ff0000')

    def test_redaction_leaves_no_original_content_and_checks_its_source(self):
        secret=plain(b'BT /F1 18 Tf 40 320 Td (SECRET) Tj 0 -120 Td (Visible) Tj ET')
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf'; target=Path(tmp)/'redacted.pdf'; source.write_bytes(secret)
            recipe={'path':str(source),'page':0,'rotation':0,'boxes':[[.07,.13,.6,.25]],'stamp':signature(source)}
            export([recipe],target,dpi=150)
            self.assertEqual(text(target),''); self.assertEqual(render(target).pixelColor(50,80).name(),'#000000')
            self.assertFalse(any(b'SECRET' in data for data in streams(target)))
            self.assertNotIn(b'SECRET',target.read_bytes()); self.assertEqual(source.read_bytes(),secret)
            with self.assertRaises(FileExistsError): export([recipe],target)
            source.write_bytes(plain()); output=Path(tmp)/'stale.pdf'
            with self.assertRaises(ValueError): export([recipe],output)
            self.assertFalse(output.exists())

    def test_redaction_drops_shared_unused_resources_from_other_pages(self):
        writer=Writer(); font=writer.add({'Type':Name('Font'),'Subtype':Name('Type1'),'BaseFont':Name('Helvetica')})
        hidden=writer.stream(b'BT /F1 18 Tf 10 50 Td (SECRET) Tj ET',Type=Name('XObject'),Subtype=Name('Form'),BBox=[0,0,100,100],Resources={'Font':{'F1':font}})
        shared={'Font':{'F1':font},'XObject':{'Hidden':hidden}}
        writer.add_page(100,100,b'/Hidden Do',shared)
        writer.add_page(100,100,b'BT /F1 18 Tf 10 50 Td (Visible) Tj ET',shared)
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'shared.pdf'; target=Path(tmp)/'safe.pdf'; writer.save(source)
            items=[dict(path=str(source),page=0,rotation=0,boxes=[[0,0,1,1]],stamp=signature(source)),dict(path=str(source),page=1,rotation=0,boxes=[],stamp=signature(source))]
            export(items,target,dpi=150)
            self.assertFalse(any(b'SECRET' in data for data in streams(target)))
            self.assertEqual(render(target).pixelColor(30,30).name(),'#000000')
            self.assertEqual(text(target,1),'')

    def test_unsupported_features_are_refused(self):
        for content in (b'0 0 m 2 0 0 2 0 0 cm 1 1 l S',b'BI /W 1 /H 1 ID xx EI'):
            with self.assertRaises(ValueError): render(plain(content))
        external=fixture([b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 100 100] >>',
                          b'<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>',b'<< /Length 0 /F (/etc/passwd) >>\nstream\n\nendstream'])
        self.assertTrue(refused(external))
        writer=Writer(); writer.add_page(100,100,b''); layer=writer.add({'Type':Name('OCG'),'Name':b'L'})
        writer.objects[0]['OCProperties']={'OCGs':[layer],'D':{}}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'layers.pdf'; writer.save(source)
            with self.assertRaises(ValueError): export([dict(path=str(source),page=0,rotation=0,boxes=[],stamp=signature(source))],Path(tmp)/'out.pdf')

    def test_words_follow_replacement_text_and_gaps_without_a_space(self):
        self.assertEqual(text(plain(b'BT /F1 18 Tf 40 300 Td /Span << /ActualText (fi) >> BDC (xy) Tj EMC ( ok) Tj ET')),'fi ok')
        # A zero-width replacement makes the glyphs unread instead of leaving an invisible character in the word.
        self.assertEqual(text(plain(b'BT /F1 18 Tf 40 300 Td (a) Tj /Span << /ActualText <FEFF200B> >> BDC (x) Tj EMC (b) Tj ET')),'a b')
        self.assertEqual(text(plain(b'BT /F1 20 Tf 40 300 Td [(Hello) -300 (World)] TJ ET')),'Hello World')
        self.assertEqual(text(plain(b'BT /F1 20 Tf 40 300 Td [(Hel) -40 (lo)] TJ ET')),'Hello')

    def test_the_python_pdf_engine_is_gone(self):
        here=Path(__file__).parent
        self.assertEqual(sorted(path.name for path in here.glob('lumen_pdf*.py')),[])
        for path in here.glob('*.py'):
            if path.name.startswith('test_'): continue
            source=path.read_text(errors='replace')
            with self.subTest(path=path.name):
                self.assertNotIn('import lumen_pdf',source); self.assertNotIn('from lumen_pdf',source)


if __name__=='__main__': unittest.main()
