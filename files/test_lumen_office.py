"""The Reader's own Office reader on small hand-written files; no office suite and no server."""
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

import lumen_office
from lumen_pdf import PDFError
from lumen_reflow import ReflowBook

TYPES = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
WORD = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
SHEET = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
SLIDE = ('xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
OPEN = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
        'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"')


def relations(*items):
    return ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + ''.join(f'<Relationship Id="{identity}" Type="t" Target="{target}"/>' for identity, target in items) + '</Relationships>')


def png():
    def chunk(kind, data): return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 40, 20, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(b'\0' + bytes((200, 40, 40)) * 40 for _ in range(20)))) + chunk(b'IEND', b''))


class OfficeTest(unittest.TestCase):
    def book(self, name, parts):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        path = Path(folder.name) / name
        with zipfile.ZipFile(path, 'w') as archive:
            for part, content in parts.items(): archive.writestr(part, content)
        book = ReflowBook(path); self.addCleanup(book.close)
        return book

    def test_word_keeps_headings_emphasis_lists_tables_and_pictures(self):
        body = ('<w:p><w:pPr><w:pStyle w:val="H1"/></w:pPr><w:r><w:t>Bericht</w:t></w:r></w:p>'
                '<w:p><w:r><w:t xml:space="preserve">Umsatz </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>&lt;stark&gt;</w:t></w:r></w:p>'
                '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr><w:r><w:t>eins</w:t></w:r></w:p>'
                '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr><w:r><w:t>zwei</w:t></w:r></w:p>'
                '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Nord</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1200</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                '<w:p><w:r><w:drawing><a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="rId5"/></w:drawing></w:r></w:p>')
        book = self.book('bericht.docx', {
            '[Content_Types].xml': TYPES, 'word/document.xml': f'<w:document {WORD}><w:body>{body}</w:body></w:document>',
            'word/styles.xml': f'<w:styles {WORD}><w:style w:styleId="H1"><w:name w:val="heading 1"/></w:style></w:styles>',
            'word/numbering.xml': f'<w:numbering {WORD}><w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>'
                                  f'<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num></w:numbering>',
            'word/_rels/document.xml.rels': relations(('rId5', 'media/bild.png')), 'word/media/bild.png': png(),
            'docProps/core.xml': '<p xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Bericht Q3</dc:title></p>'})
        page = book.page(0)
        self.assertEqual(page.text(), 'Bericht\nUmsatz <stark>\n1. eins\n2. zwei\nNord\n1200')
        self.assertEqual((book.metadata['title'], book.toc()), ('Bericht Q3', [[1, 'Bericht', 1]]))
        image = page.render(1)
        # The embedded picture is drawn, and nothing but the archive's own files is loaded.
        self.assertTrue(any(image.pixelColor(x, y).red() > 180 and image.pixelColor(x, y).green() < 80 for x in range(30, 80, 4) for y in range(60, 400, 4)))

    def test_sheets_show_values_dates_percentages_and_skip_hidden_sheets(self):
        book = self.book('zahlen.xlsx', {
            '[Content_Types].xml': TYPES,
            'xl/workbook.xml': f'<workbook {SHEET} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                               '<sheet name="Umsatz" r:id="rId1"/><sheet name="Intern" state="hidden" r:id="rId2"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels': relations(('rId1', 'worksheets/sheet1.xml'), ('rId2', 'worksheets/sheet2.xml')),
            'xl/sharedStrings.xml': f'<sst {SHEET}><si><t>Monat</t></si><si><r><t>Jan</t></r><r><t>uar</t></r><rPh><t>x</t></rPh></si></sst>',
            'xl/styles.xml': f'<styleSheet {SHEET}><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="9"/></cellXfs></styleSheet>',
            'xl/worksheets/sheet1.xml': f'<worksheet {SHEET}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>Wert</t></is></c></row>'
                                        '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>1234.5</v></c><c r="C2" s="1"><v>46000</v></c><c r="D2" s="2"><v>0.125</v></c>'
                                        '<c r="E2" t="b"><v>1</v></c><c r="F2"><f>B2*2</f><v>2469</v></c></row></sheetData></worksheet>',
            'xl/worksheets/sheet2.xml': f'<worksheet {SHEET}><sheetData><row r="1"><c r="A1"><v>7</v></c></row></sheetData></worksheet>'})
        self.assertEqual(len(book), 1)
        self.assertEqual(book.page(0).text(), 'Umsatz\nMonat\nWert\nJanuar\n1234,5\n09.12.2025\n12,5 %\nWAHR\n2469')

    def test_slides_follow_presentation_order_with_titles_and_bullets(self):
        def slide(title, line):
            return (f'<p:sld {SLIDE}><p:cSld><p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>'
                    f'<p:sp><p:nvSpPr><p:nvPr><p:ph idx="1"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>{line}</a:t></a:r></a:p></p:txBody></p:sp>'
                    '<p:sp><p:nvSpPr><p:nvPr><p:ph type="sldNum"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:fld><a:t>9</a:t></a:fld></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
        book = self.book('plan.pptx', {
            '[Content_Types].xml': TYPES,
            'ppt/presentation.xml': f'<p:presentation {SLIDE}><p:sldIdLst><p:sldId r:id="rId2"/><p:sldId r:id="rId1"/></p:sldIdLst></p:presentation>',
            'ppt/_rels/presentation.xml.rels': relations(('rId1', 'slides/slide1.xml'), ('rId2', 'slides/slide2.xml')),
            'ppt/slides/slide1.xml': slide('Zahlen', 'Umsatz'), 'ppt/slides/slide2.xml': slide('Strategie', 'Wachstum')})
        self.assertEqual([book.page(index).text() for index in range(len(book))], ['Folie 1 · Strategie\n• Wachstum', 'Folie 2 · Zahlen\n• Umsatz'])
        self.assertEqual(book.toc(), [[2, 'Folie 1 · Strategie', 1], [2, 'Folie 2 · Zahlen', 2]])

    def test_open_document_text_with_styles_lists_and_tables(self):
        book = self.book('protokoll.odt', {
            'mimetype': 'application/vnd.oasis.opendocument.text',
            'content.xml': f'<office:document-content {OPEN}><office:automatic-styles><style:style style:name="T1"><style:text-properties fo:font-weight="bold"/></style:style>'
                           '</office:automatic-styles><office:body><office:text><text:h text:outline-level="1">Protokoll</text:h>'
                           '<text:p>Beschluss:<text:s/><text:span text:style-name="T1">angenommen</text:span>, einstimmig.</text:p>'
                           '<text:list><text:list-item><text:p>Punkt A</text:p></text:list-item></text:list>'
                           '<table:table><table:table-row><table:table-cell><text:p>Name</text:p></table:table-cell>'
                           '<table:table-cell table:number-columns-repeated="16000"/></table:table-row>'
                           '<table:table-row table:number-rows-repeated="1000000"><table:table-cell table:number-columns-repeated="16384"/></table:table-row>'
                           '</table:table></office:text></office:body></office:document-content>'})
        self.assertEqual(book.page(0).text(), 'Protokoll\nBeschluss: angenommen, einstimmig.\n• Punkt A\nName')

    def test_unreadable_and_hostile_files_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            legacy = Path(folder) / 'alt.docx'; legacy.write_bytes(b'\xd0\xcf\x11\xe0 kein Zip')
            with self.assertRaises(PDFError): ReflowBook(legacy)
            bomb = Path(folder) / 'entity.docx'
            with zipfile.ZipFile(bomb, 'w') as archive:
                archive.writestr('word/document.xml', f'<!DOCTYPE d [<!ENTITY a "aaaa">]><w:document {WORD}><w:body/></w:document>')
            with self.assertRaises(PDFError): ReflowBook(bomb)
            outside = Path(folder) / 'fremd.docx'
            with zipfile.ZipFile(outside, 'w') as archive:
                archive.writestr('word/document.xml', f'<w:document {WORD}><w:body><w:p><w:r><w:drawing><a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                                                      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="rId1"/></w:drawing></w:r></w:p></w:body></w:document>')
                archive.writestr('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                                                 '<Relationship Id="rId1" Target="file:///etc/passwd" TargetMode="External"/></Relationships>')
            # A picture outside the file is not fetched; the page says that a picture is missing.
            with ReflowBook(outside) as book: self.assertIn('Bild', book.page(0).text())
        self.assertEqual(lumen_office.cell_text('3.0'), '3')


if __name__ == '__main__': unittest.main()
