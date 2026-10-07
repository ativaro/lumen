"""Shared, inert answer blocks built from Qt's Markdown parser, never model HTML."""
import hashlib
import html
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextFormat, QTextTable, QTextBlockFormat
from search_document import SafeDocument, SafeHtml
from lumen_i18n import tr


def fragment(document, start, end):
    cursor = QTextCursor(document); cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.KeepAnchor)
    source = cursor.selection().toHtml()
    body = source.split('<body', 1)[1].split('>', 1)[1].rsplit('</body>', 1)[0]
    safe = SafeHtml(); safe.feed(body)
    return ''.join(safe.output)


def inline(block):
    """Keep emphasis and safe links without carrying list/paragraph margins."""
    parts = []; it = block.begin()
    while not it.atEnd():
        item = it.fragment(); fmt = item.charFormat()
        if item.isValid() and not fmt.isImageFormat():
            value = html.escape(item.text())
            if fmt.fontWeight() >= 600: value = '<b>'+value+'</b>'
            if fmt.fontItalic(): value = '<i>'+value+'</i>'
            if fmt.fontStrikeOut(): value = '<s>'+value+'</s>'
            from PySide6.QtCore import QUrl
            if fmt.isAnchor() and QUrl(fmt.anchorHref()).scheme() in ('https', 'http'):
                value = '<a href="'+html.escape(fmt.anchorHref(), quote=True)+'">'+value+'</a>'
            parts.append(value)
        it += 1
    return ''.join(parts)


def blocks(text):
    doc = SafeDocument(); doc.setMarkdown(text, QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
    from ui_typography import format_document
    format_document(doc)
    result = []; start = end = None; counts = {}
    def flush():
        nonlocal start, end
        if start is not None:
            result.append(dict(kind='text', body=fragment(doc, start, end)))
        start = end = None
    it = doc.rootFrame().begin()
    while not it.atEnd():
        frame, block = it.currentFrame(), it.currentBlock()
        if isinstance(frame, QTextTable):
            flush(); rows = []
            for row in range(frame.rows()):
                cells = []
                for col in range(frame.columns()):
                    cell = frame.cellAt(row, col); first = cell.firstCursorPosition(); last = cell.lastCursorPosition()
                    first.setPosition(last.position(), QTextCursor.KeepAnchor)
                    b = cell.firstCursorPosition().block(); values = []
                    while b.isValid() and b.position() <= last.position():
                        values.append(inline(b)); b = b.next()
                    align = cell.firstCursorPosition().blockFormat().alignment()
                    cells.append(dict(body='<br>'.join(values), text=first.selectedText(), right=bool(align & Qt.AlignRight)))
                rows.append(cells)
            if len(rows) > 1:
                for col, cell in enumerate(rows[0]):
                    cell['right'] = rows[1][col]['right']
                    cell['body'] = cell['body'].replace('<b>', '<span style="font-weight:500">').replace('</b>', '</span>')
            result.append(dict(kind='table', title=tr('Übersicht'), rows=rows))
        elif block.isValid():
            fmt = block.blockFormat(); marker = fmt.marker()
            checklist = block.textList() is not None and marker != QTextBlockFormat.NoMarker
            code = fmt.hasProperty(QTextFormat.BlockCodeFence) or fmt.nonBreakableLines()
            quote = bool(fmt.property(QTextFormat.BlockQuoteLevel))
            if checklist:
                flush()
                if not result or result[-1]['kind'] != 'checklist':
                    result.append(dict(kind='checklist', title=tr('Checkliste'), items=[]))
                digest = hashlib.sha256(block.text().encode()).hexdigest()[:20]
                occurrence = counts.get(digest, 0); counts[digest] = occurrence + 1
                result[-1]['items'].append(dict(key=f'{digest}-{occurrence}', body=inline(block), text=block.text(),
                    checked=marker == QTextBlockFormat.Checked, indent=max(0, block.textList().format().indent()-1)))
            elif code or quote:
                flush(); kind = 'code' if code else 'quote'
                language = str(fmt.property(QTextFormat.BlockCodeLanguage) or '')
                value = html.escape(block.text()).replace(' ', '&nbsp;').replace('\t', '&nbsp;'*4) if code else inline(block)
                if result and result[-1]['kind'] == kind and result[-1].get('language') == language:
                    result[-1]['body'] += ('<br>' if code else '<br><br>') + value
                else: result.append(dict(kind=kind, title=language or tr('Code') if code else tr('Hinweis'), language=language, body=value))
            elif block.text() or block.textList():
                if start is None: start = block.position()
                end = block.position()+block.length()-1
            elif start is not None:
                end = block.position()
        it += 1
    flush()
    return result


def table_html(block, width, muted, border, size=17):
    """Use stacked records when columns would get squeezed; keep every value."""
    rows = block['rows']
    if not rows: return ''
    headers = rows[0]
    narrow = width < max(520, len(headers)*145)
    if narrow:
        output = []
        for row in rows[1:]:
            fields = ['<p style="margin:8px 0"><b>'+row[0]['body']+'</b></p>']
            for index, cell in enumerate(row[1:], 1):
                fields.append('<p style="margin:6px 0"><span style="color:'+muted+'">'+headers[index]['body']+' · </span>'+cell['body']+'</p>')
            output.append(''.join(fields))
        return '<hr>'.join(output) if output else '<p>'+' · '.join(c['body'] for c in headers)+'</p>'
    output = ['<table width="100%" cellspacing="0" cellpadding="10" style="border-collapse:collapse">']
    for index, row in enumerate(rows):
        output.append('<tr>')
        for cell in row:
            style = 'border-bottom:1px solid '+border+';'
            if index == 0: style += 'color:'+muted+';font-size:'+str(max(12, size-3))+'px;'
            output.append('<td align="'+('right' if cell['right'] else 'left')+'" style="'+style+'">'+cell['body']+'</td>')
        output.append('</tr>')
    return ''.join(output)+'</table>'
