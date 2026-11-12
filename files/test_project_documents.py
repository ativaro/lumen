"""Office sources and linked conversation results participate in project retrieval."""
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools_data import Library
from test_lumen_office import OPEN, SHEET, SLIDE, TYPES, WORD, relations, setUpModule  # noqa: F401 - builds the document reader once


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




    def test_office_search_reads_slides_whole_sheets_footnotes_and_open_document(self):
        from content_search import read_content
        def slide(line):
            return f'<p:sld {SLIDE}><p:cSld><p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph idx="1"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>{line}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
        path = self.archive('ordered.pptx', {
            '[Content_Types].xml': TYPES,
            'ppt/presentation.xml': f'<p:presentation {SLIDE}><p:sldIdLst><p:sldId id="256" r:id="b"/><p:sldId id="257" r:id="a"/></p:sldIdLst>'
                                    '<p:extLst><p:ext><sectionLst><section><sldIdLst><sldId id="256"/></sldIdLst></section></sectionLst></p:ext></p:extLst></p:presentation>',
            'ppt/_rels/presentation.xml.rels': relations(('a', 'slides/slide1.xml'), ('b', 'slides/slide2.xml')),
            'ppt/slides/slide1.xml': slide('Second authored slide'), 'ppt/slides/slide2.xml': slide('VCF first authored slide')})
        text, partial = read_content(path)
        self.assertLess(text.index('VCF first authored slide'), text.index('Second authored slide'))
        self.assertEqual(text.count('Folie '), 2)  # a section list repeats slide IDs without adding slides
        self.assertFalse(partial)
        rows = ''.join(f'<row r="{n}"><c r="A{n}" t="inlineStr"><is><t>row {n}</t></is></c></row>' for n in range(1, 1501))
        path = self.archive('inline.xlsm', {
            '[Content_Types].xml': TYPES,
            'xl/workbook.xml': f'<workbook {SHEET} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Decision" r:id="r"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels': relations(('r', 'worksheets/sheet1.xml')),
            'xl/worksheets/sheet1.xml': f'<worksheet {SHEET}><sheetData>{rows}<row r="1501"><c r="AZ1501" t="inlineStr"><is><t>VCF beyond the reading view</t></is></c></row></sheetData></worksheet>',
            'xl/vbaProject.bin': b'must never execute'})
        text, partial = read_content(path)
        self.assertIn('Decision', text); self.assertIn('row 1500', text)
        self.assertIn('VCF beyond the reading view', text)  # the reading view stops at 1000 rows and 40 columns
        self.assertNotIn('Gekürzt', text); self.assertNotIn('must never execute', text)
        path = self.archive('notes.docx', {
            '[Content_Types].xml': TYPES,
            'word/document.xml': f'<w:document {WORD}><w:body><w:p><w:r><w:t>Body &amp; text</w:t></w:r></w:p></w:body></w:document>',
            'word/footnotes.xml': f'<w:footnotes {WORD}><w:footnote><w:p><w:r><w:t>VCF footnote</w:t></w:r></w:p></w:footnote></w:footnotes>'})
        self.assertEqual(read_content(path), ('Body & text\n\nVCF footnote', False))
        path = self.archive('minutes.odt', {
            'mimetype': 'application/vnd.oasis.opendocument.text',
            'content.xml': f'<office:document-content {OPEN}><office:body><office:text><text:p>VCF open document</text:p></office:text></office:body></office:document-content>'})
        self.assertIn('VCF open document', read_content(path)[0])
        path = self.archive('partial.docx', {
            '[Content_Types].xml': TYPES,
            'word/document.xml': f'<w:document {WORD}><w:body><w:p><w:r><w:t>'+('VCF '*400000)+'</w:t></w:r></w:p></w:body></w:document>'})
        text, partial = read_content(path)
        self.assertTrue(partial); self.assertLessEqual(len(text.encode()), 1024*1024)
        broken = self.folder/'broken.docx'; broken.write_bytes(b'not an archive')
        with self.assertRaisesRegex(ValueError, 'Office-Datei nicht lesbar'): read_content(broken)

    def test_knowledge_index_reads_office_files_and_names_the_slide(self):
        from lumen_knowledge import index_root, search
        from lumen_store import Store
        def slide(line):
            return f'<p:sld {SLIDE}><p:cSld><p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph idx="1"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>{line}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
        self.archive('plan.pptx', {
            '[Content_Types].xml': TYPES,
            'ppt/presentation.xml': f'<p:presentation {SLIDE}><p:sldIdLst><p:sldId r:id="a"/><p:sldId r:id="b"/></p:sldIdLst></p:presentation>',
            'ppt/_rels/presentation.xml.rels': relations(('a', 'slides/slide1.xml'), ('b', 'slides/slide2.xml')),
            'ppt/slides/slide1.xml': slide('Einleitung'), 'ppt/slides/slide2.xml': slide('Quartalsumsatz Nord')})
        store = Store(self.root/'knowledge')
        self.assertEqual(index_root(store, str(self.folder))['errors'], 0)
        rows = search(store, 'Quartalsumsatz')
        self.assertEqual([(Path(row['path']).name, row['page']) for row in rows], [('plan.pptx', 2)])

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
