"""Word, Excel, PowerPoint and OpenDocument files as local reading pages; no server and no office suite.

Each format is read from its own XML and handed to the Reader's text layout as plain HTML:
headings, emphasis, lists, tables and pictures. It is a reading view, not the printed layout.
"""
from datetime import datetime, timedelta
from html import escape
import posixpath
import re
import zipfile

from lumen_i18n import tr
from lumen_pdf import PDFError
from lumen_reflow import xml

OFFICE = {'.docx', '.docm', '.xlsx', '.xlsm', '.pptx', '.pptm', '.odt', '.ods', '.odp'}
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
TEXT = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
TABLE = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'
DRAW = '{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}'
STYLE = '{urn:oasis:names:tc:opendocument:xmlns:style:1.0}'
FO = '{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}'
SVG = '{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}'
XLINK = '{http://www.w3.org/1999/xlink}'
PICTURES = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
MAX_HTML = 4 * 1024**2      # per document; more is cut with a visible note
MAX_ROWS, MAX_COLUMNS = 1000, 40
PAGE = 536                  # reading width in px inside the page margins


def open_archive(path):
    try: archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise PDFError(tr('Geschützte oder beschädigte Office-Datei.')) from error
    entries = archive.infolist()
    if (len(entries) > 10000 or len({e.filename for e in entries}) != len(entries) or sum(e.file_size for e in entries) > 256 * 1024**2
            or any(e.file_size > 64 * 1024**2 or e.flag_bits & 1 for e in entries)):
        archive.close(); raise PDFError(tr('Diese Office-Datei enthält zu viele, doppelte, verschlüsselte oder zu große Inhalte.'))
    return archive


def part(archive, name):
    if name not in archive.namelist(): raise PDFError(tr('Office-Datei unvollständig: ') + name)
    return xml(archive.read(name))


def relations(archive, name):
    """Targets of a part's relationships, as archive names; links out of the file are left out."""
    path = posixpath.join(posixpath.dirname(name), '_rels', posixpath.basename(name) + '.rels')
    if path not in archive.namelist(): return {}
    result = {}
    for item in xml(archive.read(path)):
        if item.get('TargetMode') == 'External': continue
        target = item.get('Target', '')
        result[item.get('Id')] = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    return result


def picture(archive, name, width=0, height=0):
    if name not in archive.namelist() or not name.lower().endswith(PICTURES): return '<p><i>' + escape(tr('[Bild in diesem Format nicht darstellbar]')) + '</i></p>'
    if width > PAGE: width, height = PAGE, height * PAGE / width
    size = f' width="{round(width)}" height="{round(height)}"' if width >= 1 and height >= 1 else f' width="{PAGE}"' if not width else ''
    return f'<img src="/{escape(name, quote=True)}"{size}>'


def enabled(properties, tag, space=W):
    node = properties.find(space + tag) if properties is not None else None
    return node is not None and node.get(space + 'val', 'true') not in ('0', 'false', 'none')


def word(archive):
    document = part(archive, 'word/document.xml'); links = relations(archive, 'word/document.xml')
    headings = {}; formats = {}
    if 'word/styles.xml' in archive.namelist():
        for style in part(archive, 'word/styles.xml').iter(W + 'style'):
            name = style.find(W + 'name'); name = (name.get(W + 'val', '') if name is not None else '').lower()
            match = re.fullmatch(r'heading (\d)', name)
            if match: headings[style.get(W + 'styleId')] = int(match[1])
            elif name == 'title': headings[style.get(W + 'styleId')] = 1
    if 'word/numbering.xml' in archive.namelist():
        numbering = part(archive, 'word/numbering.xml'); abstract = {}
        for item in numbering.iter(W + 'abstractNum'):
            abstract[item.get(W + 'abstractNumId')] = {level.get(W + 'ilvl'): (level.find(W + 'numFmt').get(W + 'val') if level.find(W + 'numFmt') is not None else 'bullet') for level in item.iter(W + 'lvl')}
        for item in numbering.iter(W + 'num'):
            reference = item.find(W + 'abstractNumId')
            if reference is not None: formats[item.get(W + 'numId')] = abstract.get(reference.get(W + 'val'), {})
    counters = {}

    def run(node):
        properties = node.find(W + 'rPr'); text = ''
        for child in node:
            if child.tag == W + 't': text += escape(child.text or '')
            elif child.tag == W + 'tab': text += '&emsp;'
            elif child.tag in (W + 'br', W + 'cr') and child.get(W + 'type') != 'page': text += '<br>'
            elif child.tag in (W + 'drawing', W + 'pict'):
                for blip in child.iter(A + 'blip'):
                    extent = next(child.iter('{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent'), None)
                    width, height = (int(extent.get('cx', 0)) / 9525, int(extent.get('cy', 0)) / 9525) if extent is not None else (0, 0)
                    text += picture(archive, links.get(blip.get(R + 'embed'), ''), width, height)
        if not text or properties is None: return text
        for tag, mark in (('b', 'b'), ('i', 'i'), ('strike', 's')):
            if enabled(properties, tag): text = f'<{mark}>{text}</{mark}>'
        if enabled(properties, 'u'): text = f'<u>{text}</u>'
        position = properties.find(W + 'vertAlign')
        if position is not None and position.get(W + 'val') in ('superscript', 'subscript'): text = '<{0}>{1}</{0}>'.format('sup' if position.get(W + 'val') == 'superscript' else 'sub', text)
        colour = properties.find(W + 'color')
        if colour is not None and re.fullmatch(r'[0-9A-Fa-f]{6}', colour.get(W + 'val', '')): text = f'<span style="color:#{colour.get(W + "val")}">{text}</span>'
        return text

    def inline(node):
        text = ''
        for child in node:
            if child.tag == W + 'r': text += run(child)
            elif child.tag in (W + 'hyperlink', W + 'ins', W + 'smartTag', W + 'sdt', W + 'sdtContent', W + 'fldSimple'): text += inline(child)
        return text

    def paragraph(node):
        properties = node.find(W + 'pPr'); text = inline(node)
        style = properties.find(W + 'pStyle') if properties is not None else None
        level = headings.get(style.get(W + 'val')) if style is not None else None
        if level and text.strip(): return f'<h{min(level, 6)}>{text}</h{min(level, 6)}>'
        align = properties.find(W + 'jc') if properties is not None else None
        align = {'center': 'center', 'right': 'right', 'end': 'right', 'both': 'justify'}.get(align.get(W + 'val')) if align is not None else None
        attributes = f' align="{align}"' if align else ''
        listing = properties.find(W + 'numPr') if properties is not None else None
        if listing is not None and text.strip():
            depth = listing.find(W + 'ilvl'); number = listing.find(W + 'numId')
            depth = depth.get(W + 'val', '0') if depth is not None else '0'; number = number.get(W + 'val') if number is not None else ''
            if number != '0':
                key = (number, depth); counters[key] = counters.get(key, 0) + 1
                for other in [k for k in counters if k[0] == number and int(k[1]) > int(depth)]: del counters[other]
                mark = '•' if formats.get(number, {}).get(depth, 'bullet') == 'bullet' else f'{counters[key]}.'
                return f'<p style="margin-left:{20 * (min(int(depth), 8) + 1)}px">{mark}&nbsp;{text}</p>'
        return f'<p{attributes}>{text or "&nbsp;"}</p>'

    def table(node):
        rows = ''
        for row in node.findall(W + 'tr'):
            cells = ''
            for cell in row.findall(W + 'tc'):
                properties = cell.find(W + 'tcPr'); span = properties.find(W + 'gridSpan') if properties is not None else None
                merge = properties.find(W + 'vMerge') if properties is not None else None
                # A continued vertical merge is an empty cell here; the text stands in the first one.
                content = '' if merge is not None and merge.get(W + 'val') != 'restart' else blocks(cell)
                cells += '<td' + (f' colspan="{int(span.get(W + "val", 1))}"' if span is not None else '') + f'>{content}</td>'
            rows += f'<tr>{cells}</tr>'
        return f'<table border="1" cellspacing="0" cellpadding="4" width="100%">{rows}</table>'

    def blocks(node):
        result = ''
        for child in node:
            if child.tag == W + 'p': result += paragraph(child)
            elif child.tag == W + 'tbl': result += table(child)
            elif child.tag in (W + 'sdt', W + 'sdtContent'): result += blocks(child)
        return result

    body = document.find(W + 'body')
    if body is None: raise PDFError(tr('Word-Dokument ohne Inhalt.'))
    return [blocks(body)]


def cell_text(value):
    number = float(value)
    return str(int(number)) if number.is_integer() and abs(number) < 1e15 else format(number, '.10g').replace('.', ',')


def spreadsheet(archive):
    workbook = part(archive, 'xl/workbook.xml'); links = relations(archive, 'xl/workbook.xml')
    strings = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        for item in part(archive, 'xl/sharedStrings.xml').findall(S + 'si'):
            # Phonetic guides (rPh) repeat the text and are not part of it.
            strings.append(''.join(t.text or '' for child in item if child.tag != S + 'rPh' for t in ([child] if child.tag == S + 't' else child.iter(S + 't'))))
    dates = []; percents = []
    if 'xl/styles.xml' in archive.namelist():
        styles = part(archive, 'xl/styles.xml')
        custom = {item.get('numFmtId'): item.get('formatCode', '') for item in styles.iter(S + 'numFmt')}
        formats = styles.find(S + 'cellXfs')
        for item in formats if formats is not None else []:
            identity = item.get('numFmtId', '0'); code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', custom.get(identity, ''))
            dates.append(identity.isdigit() and (14 <= int(identity) <= 22 or 27 <= int(identity) <= 36 or 45 <= int(identity) <= 47 or 50 <= int(identity) <= 58) or bool(re.search(r'[ymdhs]', code, re.I)))
            percents.append(identity in ('9', '10') or '%' in code)
    properties = workbook.find(S + 'workbookPr'); epoch = datetime(1904, 1, 1) if properties is not None and properties.get('date1904') in ('1', 'true') else datetime(1899, 12, 30)
    result = []
    for sheet in workbook.iter(S + 'sheet'):
        if sheet.get('state') in ('hidden', 'veryHidden'): continue
        name = links.get(sheet.get(R + 'id'))
        if not name: continue
        rows = {}; cut = False
        for row in part(archive, name).iter(S + 'row'):
            for cell in row.findall(S + 'c'):
                match = re.fullmatch(r'([A-Z]{1,3})(\d{1,7})', cell.get('r', ''))
                if not match: continue
                column = 0
                for letter in match[1]: column = column * 26 + ord(letter) - 64
                line = int(match[2])
                if line > MAX_ROWS or column > MAX_COLUMNS: cut = True; continue
                kind = cell.get('t', 'n'); value = cell.find(S + 'v'); value = value.text or '' if value is not None else ''
                style = int(cell.get('s', 0)) if cell.get('s', '0').isdigit() else 0; numeric = False
                try:
                    if kind == 's': text = strings[int(value)]
                    elif kind == 'inlineStr': text = ''.join(t.text or '' for t in cell.iter(S + 't'))
                    elif kind == 'b': text = tr('WAHR') if value == '1' else tr('FALSCH')
                    elif kind in ('str', 'e') or not value: text = value
                    elif style < len(dates) and dates[style]:
                        moment = epoch + timedelta(days=float(value))
                        text = moment.strftime('%H:%M') if float(value) < 1 else moment.strftime('%d.%m.%Y') if float(value).is_integer() else moment.strftime('%d.%m.%Y %H:%M')
                    elif style < len(percents) and percents[style]: text = cell_text(str(round(float(value) * 100, 8))) + ' %'; numeric = True
                    else: text = cell_text(value); numeric = True
                except (ValueError, IndexError, OverflowError): text = value
                if text: rows.setdefault(line, {})[column] = (text, numeric)
        title = f'<h2>{escape(sheet.get("name", ""))}</h2>'
        if not rows: result.append(title + '<p><i>' + escape(tr('Leeres Tabellenblatt')) + '</i></p>'); continue
        width = max(max(row) for row in rows.values()); body = ''
        for line in range(min(rows), max(rows) + 1):
            row = rows.get(line, {})
            body += '<tr>' + ''.join('<td' + (' align="right"' if row.get(column, ('', False))[1] else '') + '>' + escape(row.get(column, ('', False))[0]) + '</td>' for column in range(1, width + 1)) + '</tr>'
        note = '<p><i>' + escape(tr('Gekürzt auf {0} Zeilen und {1} Spalten.', MAX_ROWS, MAX_COLUMNS)) + '</i></p>' if cut else ''
        result.append(title + f'<table border="1" cellspacing="0" cellpadding="3" style="font-size:{11 if width > 6 else 13}px">{body}</table>' + note)
    if not result: raise PDFError(tr('Arbeitsmappe ohne sichtbares Tabellenblatt.'))
    return result


def slides(archive):
    presentation = part(archive, 'ppt/presentation.xml'); links = relations(archive, 'ppt/presentation.xml'); result = []

    def paragraphs(body, bullets):
        text = ''
        for paragraph in body.findall(A + 'p'):
            properties = paragraph.find(A + 'pPr'); line = ''
            for child in paragraph:
                if child.tag in (A + 'r', A + 'fld'):
                    piece = escape(''.join(t.text or '' for t in child.findall(A + 't'))); style = child.find(A + 'rPr')
                    if style is not None and piece:
                        if style.get('b') == '1': piece = f'<b>{piece}</b>'
                        if style.get('i') == '1': piece = f'<i>{piece}</i>'
                        if style.get('u', 'none') != 'none': piece = f'<u>{piece}</u>'
                    line += piece
                elif child.tag == A + 'br': line += '<br>'
            if not line.strip(): continue
            depth = min(int(properties.get('lvl', 0)), 8) if properties is not None and properties.get('lvl', '0').isdigit() else 0
            marked = bullets if properties is None else properties.find(A + 'buNone') is None and (bullets or properties.find(A + 'buChar') is not None or properties.find(A + 'buAutoNum') is not None)
            text += f'<p style="margin-left:{20 * depth + (16 if marked else 0)}px">{"•&nbsp;" if marked else ""}{line}</p>'
        return text

    def shapes(tree, own):
        title = ''; content = ''
        for shape in tree:
            if shape.tag == P + 'sp':
                body = shape.find(P + 'txBody')
                if body is None: continue
                holder = shape.find(f'{P}nvSpPr/{P}nvPr/{P}ph'); kind = holder.get('type', 'body') if holder is not None else None
                if kind in ('title', 'ctrTitle') and not title: title = re.sub(r'<[^>]+>', ' ', paragraphs(body, False)).strip()
                elif kind not in ('sldNum', 'dt', 'ftr'): content += paragraphs(body, kind in ('body', 'obj'))
            elif shape.tag == P + 'pic':
                blip = next(shape.iter(A + 'blip'), None); extent = next(shape.iter(A + 'ext'), None)
                width, height = (int(extent.get('cx', 0)) / 9525, int(extent.get('cy', 0)) / 9525) if extent is not None else (0, 0)
                if blip is not None: content += '<p>' + picture(archive, own.get(blip.get(R + 'embed'), ''), width / 2, height / 2) + '</p>'
            elif shape.tag == P + 'graphicFrame':
                for table in shape.iter(A + 'tbl'):
                    content += '<table border="1" cellspacing="0" cellpadding="4" width="100%">' + ''.join('<tr>' + ''.join('<td>' + (paragraphs(cell.find(A + 'txBody'), False) if cell.find(A + 'txBody') is not None else '') + '</td>' for cell in row.findall(A + 'tc')) + '</tr>' for row in table.findall(A + 'tr')) + '</table>'
            elif shape.tag == P + 'grpSp':
                inner, more = shapes(shape, own); title = title or inner; content += more
        return title, content

    order = presentation.find(P + 'sldIdLst')
    for number, entry in enumerate(order if order is not None else [], 1):
        name = links.get(entry.get(R + 'id'))
        if not name: continue
        tree = part(archive, name).find(f'{P}cSld/{P}spTree')
        title, content = shapes(tree, relations(archive, name)) if tree is not None else ('', '')
        result.append(f'<h2>{escape(tr("Folie"))} {number}' + (f' · {title}' if title else '') + '</h2>' + (content or '<p><i>' + escape(tr('Folie ohne Text')) + '</i></p>'))
    if not result: raise PDFError(tr('Präsentation ohne Folien.'))
    return result


def length(value):
    """An OpenDocument length such as 5.2cm, in reading pixels."""
    match = re.fullmatch(r'([0-9.]+)(cm|mm|in|pt|px)', value or '')
    return float(match[1]) * {'cm': 37.8, 'mm': 3.78, 'in': 96, 'pt': 96 / 72, 'px': 1}[match[2]] if match else 0


def open_document(archive, kind):
    content = part(archive, 'content.xml'); marks = {}
    for style in content.iter(STYLE + 'style'):
        properties = style.find(STYLE + 'text-properties')
        if properties is not None:
            marks[style.get(STYLE + 'name')] = [mark for mark, on in (('b', properties.get(FO + 'font-weight') == 'bold'), ('i', properties.get(FO + 'font-style') == 'italic'),
                                                                     ('u', properties.get(STYLE + 'text-underline-style', 'none') != 'none')) if on]

    def inline(node):
        text = escape(node.text or '')
        for child in node:
            if child.tag == TEXT + 's': text += '&nbsp;' * min(int(child.get(TEXT + 'c', 1)), 40)
            elif child.tag == TEXT + 'tab': text += '&emsp;'
            elif child.tag == TEXT + 'line-break': text += '<br>'
            elif child.tag == DRAW + 'frame': text += frame(child)
            elif child.tag in (TEXT + 'span', TEXT + 'a'):
                piece = inline(child)
                for mark in marks.get(child.get(TEXT + 'style-name'), []): piece = f'<{mark}>{piece}</{mark}>'
                text += piece
            text += escape(child.tail or '')
        return text

    def frame(node):
        result = ''
        for image in node.findall(DRAW + 'image'): result += picture(archive, image.get(XLINK + 'href', '').lstrip('./'), length(node.get(SVG + 'width')), length(node.get(SVG + 'height')))
        for box in node.findall(DRAW + 'text-box'): result += blocks(box)
        return result

    def table(node):
        body = ''; lines = 0
        for row in node.iter(TABLE + 'table-row'):
            cells = ''; filled = False
            for cell in row.findall(TABLE + 'table-cell'):
                text = blocks(cell); repeat = int(cell.get(TABLE + 'number-columns-repeated', 1)) if cell.get(TABLE + 'number-columns-repeated', '1').isdigit() else 1
                filled = filled or bool(text)
                if cells.count('<td') + (repeat if text else 0) > MAX_COLUMNS: break
                span = cell.get(TABLE + 'number-columns-spanned')
                cells += ('<td' + (f' colspan="{int(span)}"' if span and span.isdigit() else '') + f'>{text}</td>') * (repeat if text or repeat <= MAX_COLUMNS else 1)
            # Sheets are padded with repeated empty rows and cells down to their last line.
            if not filled: continue
            lines += 1
            if lines > MAX_ROWS: break
            body += f'<tr>{re.sub(r"(<td></td>)+$", "", cells) or "<td></td>"}</tr>'
        return f'<table border="1" cellspacing="0" cellpadding="4">{body}</table>' if body else ''

    def blocks(node, depth=0):
        result = ''
        for child in node:
            if child.tag == TEXT + 'h':
                level = child.get(TEXT + 'outline-level', '1'); level = min(int(level), 6) if level.isdigit() else 1
                result += f'<h{level}>{inline(child)}</h{level}>'
            elif child.tag == TEXT + 'p':
                text = inline(child)
                result += f'<p style="margin-left:{20 * depth}px">{"•&nbsp;" if depth else ""}{text}</p>' if text.strip() else ''
            elif child.tag == TEXT + 'list':
                for item in child.findall(TEXT + 'list-item'): result += blocks(item, min(depth + 1, 8))
            elif child.tag == TABLE + 'table': result += table(child)
            elif child.tag == DRAW + 'frame': result += frame(child)
            elif child.tag in (TEXT + 'section', DRAW + 'g', DRAW + 'custom-shape', DRAW + 'rect'): result += blocks(child, depth)
        return result

    body = content.find('{urn:oasis:names:tc:opendocument:xmlns:office:1.0}body')
    root = body[0] if body is not None and len(body) else None
    if root is None: raise PDFError(tr('OpenDocument-Datei ohne Inhalt.'))
    if kind == '.ods':
        result = [f'<h2>{escape(sheet.get(TABLE + "name", ""))}</h2>' + (table(sheet) or '<p><i>' + escape(tr('Leeres Tabellenblatt')) + '</i></p>') for sheet in root.findall(TABLE + 'table')]
    elif kind == '.odp':
        result = [f'<h2>{escape(tr("Folie"))} {number}</h2>' + (blocks(page) or '<p><i>' + escape(tr('Folie ohne Text')) + '</i></p>') for number, page in enumerate(root.findall(DRAW + 'page'), 1)]
    else: result = [blocks(root)]
    if not result: raise PDFError(tr('OpenDocument-Datei ohne Inhalt.'))
    return result


def sections(kind, archive):
    """Title and one HTML section per document, sheet or slide."""
    parts = (word if kind in ('.docx', '.docm') else spreadsheet if kind in ('.xlsx', '.xlsm') else slides if kind in ('.pptx', '.pptm') else lambda a: open_document(a, kind))(archive)
    title = ''
    for name, tag in (('docProps/core.xml', '{http://purl.org/dc/elements/1.1/}title'), ('meta.xml', '{http://purl.org/dc/elements/1.1/}title')):
        if name in archive.namelist():
            node = next(xml(archive.read(name)).iter(tag), None)
            if node is not None and (node.text or '').strip(): title = node.text.strip()[:200]; break
    kept = []; size = 0
    for text in parts:
        size += len(text)
        if size > MAX_HTML:
            kept.append('<p><i>' + escape(tr('Das Dokument ist zu groß für die Leseansicht und wurde hier gekürzt.')) + '</i></p>'); break
        kept.append(text)
    return title, kept
