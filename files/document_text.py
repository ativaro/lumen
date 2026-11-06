"""Bounded Office text extraction from pinned streams; no execution or external links."""
from pathlib import PurePosixPath
import re
import zipfile
from xml.etree import ElementTree as ET

EXTENSIONS = {'.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm'}


def extract(stream, suffix, limit):
    with zipfile.ZipFile(stream) as archive:
        if len(archive.infolist()) > 10000:
            raise ValueError('Office archive contains too many entries.')
        budget = 32 * 1024 * 1024
        output = []; used = 0; partial = False

        def xml(name):
            nonlocal budget
            info = archive.getinfo(name)
            if info.file_size > 8 * 1024 * 1024 or info.file_size > budget:
                raise ValueError('Office XML exceeds the reading limit.')
            budget -= info.file_size
            data = archive.read(info)
            declarations = data.replace(b'\x00', b'').lower()
            if b'<!doctype' in declarations or b'<!entity' in declarations:
                raise ValueError('Office XML entity declarations are not supported.')
            return ET.fromstring(data)

        def tag(element):
            return element.tag.rsplit('}', 1)[-1]

        def add(text):
            nonlocal used, partial
            if used + len(text) + 1 > limit:
                output.append(text[:max(0, limit-used)])
                partial = True
                return False
            output.append(text); used += len(text) + 1
            return True

        def relationships(name, folder):
            result = {}
            for row in xml(name):
                if row.get('TargetMode') == 'External':
                    continue
                target = row.get('Target', '')
                path = PurePosixPath(target.lstrip('/')) if target.startswith('/') else PurePosixPath(folder)/target
                if '..' not in path.parts:
                    result[row.get('Id')] = str(path)
            return result

        def rid(element):
            return element.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')

        if suffix in {'.pptx', '.pptm'}:
            names = sorted((name for name in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', name)),
                           key=lambda name: int(re.search(r'(\d+)\.xml$', name)[1]))
            if 'ppt/presentation.xml' in archive.namelist():
                links = relationships('ppt/_rels/presentation.xml.rels', 'ppt')
                # Section lists repeat numeric slide IDs without relationship IDs.
                names = [links[rid(row)] for group in xml('ppt/presentation.xml') if tag(group) == 'sldIdLst'
                         for row in group if tag(row) == 'sldId']
            for index, name in enumerate(names, 1):
                rows = [' '.join(node.text or '' for node in paragraph.iter() if tag(node) == 't')
                        for paragraph in xml(name).iter() if tag(paragraph) == 'p']
                if not add(f'Slide {index}\n' + '\n'.join(rows)):
                    break
        elif suffix in {'.xlsx', '.xlsm'}:
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(node.text or '' for node in row.iter() if tag(node) == 't')
                           for row in xml('xl/sharedStrings.xml') if tag(row) == 'si']
            links = relationships('xl/_rels/workbook.xml.rels', 'xl')
            for sheet in xml('xl/workbook.xml').iter():
                if tag(sheet) != 'sheet':
                    continue
                for cell in xml(links[rid(sheet)]).iter():
                    if tag(cell) != 'c':
                        continue
                    values = [node.text or '' for node in cell.iter() if tag(node) in {'v', 't'}]
                    value = ' '.join(values)
                    if cell.get('t') == 's' and values:
                        if int(values[0]) < 0:
                            raise ValueError('Invalid shared string index.')
                        value = strings[int(values[0])]
                    # Cached values only: formulas and workbook links are never evaluated.
                    if not value:
                        formulas = [node.text or '' for node in cell if tag(node) == 'f']
                        if formulas: value = '[formula; no saved value] ' + ' '.join(formulas)
                    if value and not add(sheet.get('name', '') + '!' + cell.get('r', '?') + ': ' + value):
                        break
                if partial:
                    break
        else:
            for name in ['word/document.xml', 'word/footnotes.xml', 'word/endnotes.xml']:
                if name not in archive.namelist():
                    continue
                for paragraph in xml(name).iter():
                    if tag(paragraph) == 'p' and not add(''.join(node.text or '' for node in paragraph.iter() if tag(node) == 't')):
                        break
                if partial:
                    break
        return '\n'.join(output), partial
