"""PDF constructs from ISO 32000, checked without a foreign PDF engine."""
import unittest
from lumen_pdf import Document, Writer, Name, PDFError


class ExtendedPDFTest(unittest.TestCase):
    def test_undefined_outline_reference_is_pdf_null(self):
        from lumen_pdf import Ref
        writer=Writer();writer.add_page(20,20)
        writer.objects[writer.root.number-1]['Outlines']=Ref(999)
        document=Document(writer.bytes())
        self.assertIsNone(document.resolve(Ref(999)))
        self.assertIsNone(document.resolve(Ref(0)))
        self.assertIsNone(document.resolve(Ref(1,7)))
        self.assertEqual(document.toc(),[])

    def test_presentation_exporter_malformed_zero_real_can_be_copied(self):
        from lumen_pdf import Syntax,serialize
        value=Syntax(b'[1 0 0.00000-9589016 22.159212]').value()
        self.assertEqual(value,[1,0,0,22.159212])
        self.assertEqual(Syntax(serialize(value)).value(),value)
        for value in (8.3179245e-14,21.937113,1.234567891234567,-0.0):
            self.assertEqual(Syntax(serialize(value)).value(),value)

    def test_rotated_mirrored_text_keeps_words_and_selection_boxes(self):
        from lumen_pdf_page import Page
        for matrix in ('0 1 -1 0 80 20','-1 0 0 1 150 60','.7071 .7071 -.7071 .7071 50 50'):
            writer=Writer();writer.add_page(200,200,('BT /F 16 Tf '+matrix+' Tm (Alpha beta) Tj ET').encode(),
                {'Font':{'F':{'Type':Name('Font'),'Subtype':Name('Type1'),'BaseFont':Name('Helvetica')}}})
            page=Page(Document(writer.bytes()),0)
            self.assertEqual([w[4] for w in page.words],['Alpha','beta'])
            for scale in (1,2):
                image=page.render(scale)
                for word in page.words:
                    x0,y0,x1,y1=(int(v*scale) for v in word[:4])
                    self.assertTrue(any(image.pixelColor(x,y).red()<100 for y in range(max(0,y0),min(image.height(),y1+1)) for x in range(max(0,x0),min(image.width(),x1+1))))

    def test_translation_preserves_rotated_text(self):
        from lumen_pdf_page import Page
        from translate_pdf import inspect,write
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'rotated.pdf';target=Path(folder)/'translated.pdf'
            writer=Writer();writer.add_page(200,200,b'BT /F 16 Tf 0 1 -1 0 80 20 Tm (Alpha beta) Tj ET',
                {'Font':{'F':{'Type':Name('Font'),'Subtype':Name('Type1'),'BaseFont':Name('Helvetica')}}});writer.save(source)
            manifest=inspect(source);write(manifest,{s['id']:s['parts'] for s in manifest['segments']},target)
            page=Page(Document(target),0)
            self.assertEqual([w[4] for w in page.words],['Alpha','beta'])
            word=page.words[0];self.assertGreater(word[3]-word[1],word[2]-word[0])
            self.assertLess(abs(word[0]-68),8)

    def test_bitmaps_decode_arrays_stencils_and_soft_masks(self):
        from lumen_pdf_page import Page
        def render(raw,**attrs):
            writer=Writer()
            mask=attrs.pop('soft',None)
            if mask is not None:attrs['SMask']=writer.stream(mask,Type=Name('XObject'),Subtype=Name('Image'),Width=2,Height=1,BitsPerComponent=8,ColorSpace=Name('DeviceGray'))
            ref=writer.stream(raw,Type=Name('XObject'),Subtype=Name('Image'),Width=2,Height=1,**attrs)
            writer.add_page(100,50,b'0 0 1 rg 0 0 100 50 re f 1 0 0 rg 100 0 0 50 0 0 cm /I Do',{'XObject':{'I':ref}})
            return Page(Document(writer.bytes()),0).render()
        for bits,raw in [(1,b'\x40'),(2,b'\x30'),(4,b'\x0f'),(8,b'\0\xff'),(16,b'\0\0\xff\xff')]:
            image=render(raw,BitsPerComponent=bits,ColorSpace=Name('DeviceGray'),Decode=[1,0])
            self.assertEqual(image.pixelColor(20,25).name(),'#ffffff')
            self.assertEqual(image.pixelColor(80,25).name(),'#000000')
        image=render(b'\x40',ImageMask=True)
        self.assertEqual(image.pixelColor(20,25).name(),'#ff0000')
        self.assertEqual(image.pixelColor(80,25).name(),'#0000ff')
        image=render(b'\xff\0\0\xff\0\0',BitsPerComponent=8,ColorSpace=Name('DeviceRGB'),soft=b'\0\x80')
        self.assertEqual(image.pixelColor(20,25).name(),'#0000ff')
        self.assertLess(abs(image.pixelColor(80,25).red()-128),2)
        self.assertLess(abs(image.pixelColor(80,25).blue()-127),2)
        image=render(b'\0\xff',BitsPerComponent=8,ColorSpace=[Name('Indexed'),Name('DeviceRGB'),1,b'\xff\0\0\0\xff\0'])
        self.assertEqual(image.pixelColor(20,25).name(),'#ff0000')
        self.assertEqual(image.pixelColor(80,25).name(),'#00ff00')
        image=render(b'\xff\0\0\0\xff\0',BitsPerComponent=8,ColorSpace=Name('DeviceRGB'),Mask=[255,255,0,0,0,0])
        self.assertEqual(image.pixelColor(20,25).name(),'#0000ff')
        self.assertEqual(image.pixelColor(80,25).name(),'#00ff00')

    def test_colour_functions_palettes_and_calibration(self):
        from lumen_pdf_color import ColorSpace, function
        writer=Writer();writer.add_page(10,10);document=Document(writer.bytes())
        tint={'FunctionType':2,'Domain':[0,1],'C0':[1,1,1],'C1':[1,0,0],'N':1}
        self.assertEqual(function(document,tint,[.5]),[1,.5,.5])
        self.assertEqual(ColorSpace(document,[Name('Separation'),Name('Red'),Name('DeviceRGB'),tint]).color([1]).name(),'#ff0000')
        self.assertEqual(ColorSpace(document,[Name('Indexed'),Name('DeviceRGB'),1,b'\xff\0\0\0\xff\0']).color([1]).name(),'#00ff00')
        for kind,sample in [('CalGray',[1]),('Lab',[100,0,0])]:
            self.assertEqual(ColorSpace(document,[Name(kind),{'WhitePoint':[.95047,1,1.08883]}]).color(sample).name(),'#ffffff')
        from lumen_pdf import Stream
        sampled=Stream({'FunctionType':0,'Domain':[0,1],'Range':[0,1],'Size':[2],'BitsPerSample':8},bytes([0,255]))
        self.assertEqual(function(document,sampled,[.25]),[.25])
        calculator=Stream({'FunctionType':4,'Domain':[0,1],'Range':[0,1]},b'{dup .5 gt {1 exch sub} if}')
        self.assertEqual(function(document,calculator,[.75]),[.25])
        with self.assertRaises(PDFError):function(document,Stream(dict(calculator.attrs),b'{1 0 div}'),[.5])
        with self.assertRaises(PDFError):function(document,Stream(dict(calculator.attrs),b'{dup mul}} ignored'),[.5])

    def test_named_destinations_and_reordered_export(self):
        writer=Writer()
        first=writer.add_page(100,120);writer.add_page(100,120)
        target=[writer.page_refs[1],Name('XYZ'),10,100,None]
        leaf=writer.add({'Names':[b'chapter',{'D':target}]})
        writer.objects[writer.root.number-1]['Names']={'Dests':{'Kids':[leaf]}}
        writer.objects[writer.root.number-1]['Dests']={'old':target}
        outline=writer.add({'Title':b'Chapter','Dest':b'chapter'})
        writer.objects[writer.root.number-1]['Outlines']={'First':outline}
        first['Annots']=[writer.add({'Subtype':Name('Link'),'Rect':[1,1,20,10],
                                    'A':{'S':Name('GoTo'),'D':b'chapter'}})]
        source=Document(writer.bytes())
        self.assertEqual(source.toc(),[[1,'Chapter',2]])
        self.assertEqual(source.destination(Name('old')),target)
        copied=Writer();copied.copy_page(source,1);copied.copy_page(source,0)
        output=Document(copied.bytes())
        annotation=output.resolve(output.pages[1]['Annots'][0])
        self.assertEqual(annotation['A']['D'][0],output.page_refs[0])
        self.assertEqual(annotation['A']['D'][1:],target[1:])
        source.catalog['Names']['Dests']['Kids']=[source.catalog['Names']['Dests']]
        with self.assertRaises(PDFError):source.destination(b'unknown')

    def test_page_units_are_applied_and_preserved(self):
        from lumen_pdf_page import Page
        writer=Writer();page=writer.add_page(20,30,b'1 0 0 rg 0 0 10 10 re f')
        page['UserUnit']=2
        document=Document(writer.bytes());rendered=Page(document,0)
        self.assertEqual((rendered.width,rendered.height),(40,60))
        self.assertEqual(rendered.render().pixelColor(15,45).name(),'#ff0000')
        copied=Writer();copied.copy_page(document,0,90)
        result=Page(Document(copied.bytes()),0)
        self.assertEqual((result.width,result.height),(60,40))


if __name__=='__main__':unittest.main()
