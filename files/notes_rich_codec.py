"""Loss-aware Qt Markdown bridge. Unknown blocks stay atomic and retain their source."""
import re
import uuid
from urllib.parse import quote, unquote

from markdown_it import MarkdownIt
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument, QTextCursor, QTextCharFormat, QTextTable

PARSER = MarkdownIt('commonmark', {'html': True}).enable(['table', 'strikethrough'])
# Qt escapes '[' inside labels; never consume the opening bracket of another link.
LINK_LABEL = r'\[((?:\\.|[^\[\\\n])*)\]'


class SafeDocument(QTextDocument):
    def loadResource(self, kind, url):
        # Resources are supplied by the notebook's bounded image worker only.
        return None


def signature(text):
    result = []
    def add(tokens):
        for token in tokens:
            if token.type in ('inline',):
                add(token.children or [])
            elif token.type in ('text', 'softbreak'):
                value = token.content if token.type == 'text' else ' '
                if result and result[-1][0] == 'text':
                    result[-1] = ('text', result[-1][1] + value)
                else: result.append(('text', value))
            else:
                result.append((token.type, token.tag, token.content, token.info, token.attrs))
    add(PARSER.parse(text))
    return result


def markdown(document):
    """Qt maps underline to emphasis; explicitly retain it as Markdown inline HTML."""
    clone = document.clone()
    replacements = {}
    block = clone.begin()
    while block.isValid():
        iterator = block.begin()
        fragments = []
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid(): fragments.append(fragment)
            iterator += 1
        for fragment in fragments:
            fmt = fragment.charFormat()
            if not fmt.fontUnderline() or fmt.isAnchor(): continue
            key = 'lumen-underline:' + uuid.uuid4().hex
            fmt.setFontUnderline(False); fmt.setAnchor(True); fmt.setAnchorHref(key)
            cursor = QTextCursor(clone); cursor.setPosition(fragment.position())
            cursor.setPosition(fragment.position()+fragment.length(), QTextCursor.KeepAnchor)
            cursor.setCharFormat(fmt); replacements[key] = True
        block = block.next()
    # Qt emits no separator dashes for an entirely empty column. Seed only the
    # export copy so empty columns remain valid Markdown tables after reopening.
    empty_columns = []
    frames = list(clone.rootFrame().childFrames())
    while frames:
        frame = frames.pop(); frames.extend(frame.childFrames())
        if not isinstance(frame, QTextTable): continue
        for column in range(frame.columns()):
            def empty(row):
                cell = frame.cellAt(row, column); cursor = cell.firstCursorPosition()
                cursor.setPosition(cell.lastCursorPosition().position(), QTextCursor.KeepAnchor)
                return not cursor.selectedText()
            if all(empty(row) for row in range(frame.rows())):
                marker = 'lumen-empty-' + uuid.uuid4().hex
                frame.cellAt(0, column).firstCursorPosition().insertText(marker)
                empty_columns.append(marker)
    tables = [frame for frame in clone.rootFrame().childFrames() if isinstance(frame,QTextTable)]
    if tables:
        # Qt's whole-document writer can join a preceding list to the table.
        # Export top-level ranges separately to retain a real block boundary.
        parts=[];start=0
        def fragment(first,last):
            cursor=QTextCursor(clone);cursor.setPosition(first)
            cursor.setPosition(last,QTextCursor.KeepAnchor)
            return cursor.selection().toMarkdown().strip('\n')
        for table in tables:
            parts.extend([fragment(start,table.firstPosition()-1),fragment(table.firstPosition()-1,table.lastPosition()+1)])
            start=table.lastPosition()+1
        parts.append(fragment(start,clone.characterCount()-1))
        value='\n\n'.join(part for part in parts if part)+'\n\n'
    else: value = clone.toMarkdown()
    for marker in empty_columns: value = value.replace(marker, '')
    for key in replacements:
        value = re.sub(LINK_LABEL+r'\('+re.escape(key)+r'\)', r'<u>\1</u>', value)
    return value


class Codec:
    def __init__(self, source):
        self.original = source
        self.opaque = {}
        self.wiki = {}
        self.preserved = []
        self.rendered = self.prepare(source)
        doc = SafeDocument(); doc.setMarkdown(self.rendered)
        self.baseline = markdown(doc)

    def prepare(self, source):
        lines = source.splitlines(keepends=True)
        offsets = [0]
        for line in lines: offsets.append(offsets[-1]+len(line))
        tokens = [t for t in PARSER.parse(source) if t.level == 0 and t.map and t.nesting != -1]
        spans = [(t.map[0], t.map[1]) for t in tokens]
        out = []; end = 0
        for index, (first, last) in enumerate(spans):
            start, stop = offsets[first], offsets[last]
            if start < end: continue
            gap = source[end:start]
            if gap.strip(): out.append(self.protect(gap))
            else: out.append(gap)
            raw = source[start:stop]
            prepared = self.links(raw)
            doc = SafeDocument(); doc.setMarkdown(prepared)
            normalized = markdown(doc)
            # References, raw HTML, extensions and anything Qt cannot round-trip
            # remain a single selectable object, never silently normalized away.
            extension = re.search(r'!\[\[|\^[\w-]+(?:\s|$)|^\s*>\s*\[!|^\s*\[[^\]]+\]:', raw, re.M)
            # Qt carries a fence's block format into an immediately following table.
            fence_before_table = tokens[index].type == 'fence' and index+1 < len(tokens) and tokens[index+1].type == 'table_open'
            if extension or fence_before_table or signature(prepared) != signature(normalized):
                out.append(self.protect(raw))
            else:
                out.append(prepared)
                self.preserved.append((normalized.strip('\n'), raw.rstrip('\n')))
            end = stop
        rest = source[end:]
        out.append(self.protect(rest) if rest.strip() else rest)
        return ''.join(out)

    def protect(self, raw):
        key = 'lumen-preserved:' + uuid.uuid4().hex
        self.opaque[key] = raw
        return '\n\n![Lumen]('+key+')\n\n'

    def links(self, raw):
        # Work only in inline tokens: fenced/indented code and escaped links stay literal.
        tokens = PARSER.parse(raw)
        if not any(t.type == 'inline' for t in tokens): return raw
        from note_tags import body_mask
        mask = body_mask(raw)
        def replace(match):
            if not mask[match.start():match.start()+1].strip(): return match[0]
            if match[0].startswith('!'): return match[0]
            value = match[1]; target, _, label = value.partition('|')
            label = label or unquote(target).removesuffix('.md')
            key = 'lumen-wiki:' + uuid.uuid4().hex
            self.wiki[key] = (match[0], target, label)
            escaped = re.sub(r'([\\\[\]*_`])', r'\\\1', label)
            return '['+escaped+']('+key+')'
        return re.sub(r'(?<!\\)!?\[\[([^\]\n]+)\]\]', replace, raw)

    def encode(self, document):
        result = markdown(document)
        if result == self.baseline: return self.original
        # Match whole top-level blocks only, never text inside code or another block.
        originals = {}
        for canonical, raw in self.preserved:
            originals.setdefault(canonical,set()).add(raw)
        lines=result.splitlines(keepends=True);offsets=[0]
        for line in lines:offsets.append(offsets[-1]+len(line))
        edits=[]
        for token in PARSER.parse(result):
            if token.level!=0 or not token.map or token.nesting==-1:continue
            start,end=(offsets[i] for i in token.map)
            block=result[start:end];matches=originals.get(block.strip('\n'),set())
            if len(matches)==1:
                edits.append((start,end,next(iter(matches))+block[len(block.rstrip('\n')):]))
        for start,end,value in reversed(edits):result=result[:start]+value+result[end:]
        for key, raw in self.opaque.items():
            result = re.sub(r'!\[[^\]]*\]\('+re.escape(key)+r'\)', lambda _:raw.rstrip('\n'), result)
        for key, (raw, target, original_label) in self.wiki.items():
            def link(match):
                label = re.sub(r'\\([\\\[\]*_`])', r'\1', match[1])
                return raw if label == original_label else '[['+target+'|'+label+']]'
            result = re.sub(LINK_LABEL+r'\('+re.escape(key)+r'\)', link, result)
        if not self.original.endswith('\n'): result = result.rstrip('\n')
        return result
