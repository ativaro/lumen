"""Office sources and linked conversation results participate in project retrieval."""
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools_data import Library
from project_folder_search import search


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

    def test_office_text_has_slide_sheet_cell_and_document_evidence(self):
        self.archive('workshop.pptx', {'ppt/slides/slide1.xml': '<sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>VCF license</a:t></a:r></a:p></sld>'})
        self.archive('costs.xlsx', {
            'xl/workbook.xml': '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Costs" r:id="rId1"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            'xl/sharedStrings.xml': '<sst><si><t>VCF price</t></si></sst>',
            'xl/worksheets/sheet1.xml': '<worksheet><sheetData><row r="2"><c r="A2" t="s"><v>0</v></c><c r="B2"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>'})
        self.archive('plan.docx', {'word/document.xml': '<document xmlns:w="urn:word"><w:p><w:r><w:t>VCF decision</w:t></w:r></w:p></document>'})
        result = search(self.project, 'VCF')
        self.assertEqual({Path(item['path']).suffix for item in result['items']}, {'.pptx', '.xlsx', '.docx'})
        snippets = '\n'.join(item['snippet'] for item in result['items'])
        self.assertIn('Slide 1', snippets)
        self.assertIn('Costs!A2', snippets)
        self.assertIn('VCF price', snippets)
        self.assertIn('VCF decision', snippets)
        self.assertEqual(result['folders'][0]['errors'], 0)

    def test_direct_file_and_linked_chat_results_are_searchable_without_other_chats(self):
        from lumen_store import Store
        document = self.archive('direct.docx', {'word/document.xml': '<document><p><t>VCF direct document</t></p></document>'})
        chat = dict(kind='chat', title='Workshop discussion', chat=dict(directory=self.tmp, session='ses_linked'))
        self.library.update(self.project, resources=[dict(kind='file', title='Direct', target=str(document))], references=[chat])
        store = Store()
        for session, result in [('ses_linked', 'VCF answer from linked conversation'), ('ses_private', 'VCF private secret')]:
            key = store.create_task('Discussion', prompt='Explain the costs', directory=self.tmp)
            store.update_task(key, status='completed', session=session, result=result)
        result = search(self.project, 'VCF')
        self.assertEqual(len(result['items']), 2)
        passage = next(item for item in result['items'] if item.get('kind') == 'chat')
        self.assertEqual(passage['chat'], chat['chat'])
        self.assertIn('linked conversation', passage['snippet'])
        self.assertNotIn('private secret', str(result))
        self.library.update(self.project, references=[])
        self.assertFalse(any(item.get('kind') == 'chat' for item in search(self.project, 'VCF')['items']))

    def test_corrupt_oversized_and_entity_documents_report_limits_without_reading_externals(self):
        from content_search import read_content
        broken = self.folder/'broken.pptx'; broken.write_bytes(b'invalid archive')
        self.archive('external.docx', {'word/document.xml': '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><document>&e;</document>'})
        large = self.archive('huge.docx', {'word/document.xml': '<p>'+('a'*(9*1024*1024))+'</p>'})
        result = search(self.project, 'VCF')
        self.assertEqual(result['items'], [])
        self.assertEqual(result['folders'][0]['errors'], 3)
        self.assertEqual(len(result['folders'][0]['error_details']), 3)
        link = self.folder/'escape.docx'; link.symlink_to(large)
        with self.assertRaises(OSError): read_content(link)

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
