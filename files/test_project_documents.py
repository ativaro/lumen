"""Office sources and linked conversation results participate in project retrieval."""
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools_data import Library


class ProjectDocumentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp)
        self.enterContext(patch.dict(os.environ, LUMEN_TOOLS_DATA=self.tmp, LUMEN_DATA=self.tmp+'/state'))
        self.folder = self.root/'sources'; self.folder.mkdir()
        self.library = Library('workbench')
        self.project = self.library.create('VCF', resources=[dict(kind='folder', title='Sources', target=str(self.folder))], references=[])

    def archive(self, name, parts):
        path = self.folder/name
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for key, value in parts.items(): z.writestr(key, value)
        return path




    def test_slide_order_inline_cells_and_partial_documents_are_explicit(self):
        from content_search import read_content
        path = self.archive('ordered.pptx', {
            'ppt/presentation.xml': '<presentation xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sldIdLst><sldId r:id="b"/><sldId r:id="a"/></sldIdLst></presentation>',
            'ppt/_rels/presentation.xml.rels': '<Relationships><Relationship Id="a" Target="slides/slide1.xml"/><Relationship Id="b" Target="slides/slide2.xml"/></Relationships>',
            'ppt/slides/slide1.xml': '<sld><p><t>Second authored slide</t></p></sld>',
            'ppt/slides/slide2.xml': '<sld><p><t>VCF first authored slide</t></p></sld>'})
        text, partial = read_content(path)
        self.assertTrue(text.startswith('Slide 1\nVCF first authored slide'))
        self.assertFalse(partial)
        path = self.archive('inline.xlsm', {
            'xl/workbook.xml': '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Decision" r:id="r"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="r" Target="worksheets/sheet1.xml"/><Relationship Id="external" TargetMode="External" Target="https://invalid.example"/></Relationships>',
            'xl/worksheets/sheet1.xml': '<worksheet><c r="A1" t="inlineStr"><is><t>VCF inline</t></is></c><c r="B1"><f>1+1</f></c></worksheet>',
            'xl/vbaProject.bin': b'must never execute'})
        text, partial = read_content(path)
        self.assertIn('Decision!A1: VCF inline', text)
        self.assertIn('[formula; no saved value]', text)
        self.assertNotIn('must never execute', text)
        path = self.archive('partial.docx', {'word/document.xml': '<document><p><t>'+('VCF '*400000)+'</t></p></document>'})
        text, partial = read_content(path)
        self.assertTrue(partial); self.assertLessEqual(len(text.encode()), 1024*1024)

    def test_presentation_sections_are_not_extra_slides(self):
        from content_search import read_content
        path = self.archive('sections.pptx', {
            'ppt/presentation.xml': '<presentation xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sldIdLst><sldId id="256" r:id="slide"/></sldIdLst><extLst><ext><sectionLst><section><sldIdLst><sldId id="256"/></sldIdLst></section></sectionLst></ext></extLst></presentation>',
            'ppt/_rels/presentation.xml.rels': '<Relationships><Relationship Id="slide" Target="slides/slide1.xml"/></Relationships>',
            'ppt/slides/slide1.xml': '<sld><p><t>VCF section evidence</t></p></sld>'})
        text, partial = read_content(path)
        self.assertEqual(text, 'Slide 1\nVCF section evidence')
        self.assertFalse(partial)

    def test_pdf_search_preserves_the_actual_reader_failure(self):
        import content_search
        pdf = self.folder/'unsupported.pdf'; pdf.write_bytes(b'%PDF fixture')
        worker = self.root/'lumen_pdf_worker.py'
        worker.write_text('import sys\nprint("PDF fixture graphics are unsupported", file=sys.stderr)\nraise SystemExit(1)\n')
        with patch.object(content_search, '__file__', str(self.root/'content_search.py')):
            with self.assertRaisesRegex(ValueError, 'fixture graphics are unsupported'):
                content_search.read_content(pdf)


if __name__ == '__main__':
    unittest.main()
