"""Allow formatted model text without implicit image/file/network loads."""
import html
from html.parser import HTMLParser
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument
from lumen_i18n import tr


class SafeDocument(QTextDocument):
    def loadResource(self, kind, url): return None


class SafeHtml(HTMLParser):
    allowed = {'p', 'br', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'pre', 'code', 'blockquote',
               'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'hr', 'table', 'tr', 'td', 'th', 'a'}

    def __init__(self): super().__init__(convert_charrefs=True); self.output = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed: return
        safe = []
        for key, value in attrs:
            if key == 'href' and tag == 'a' and QUrl(value or '').isValid() and QUrl(value or '').scheme() in ('https', 'http'):
                safe.append('href="'+html.escape(value, quote=True)+'"')
            elif key == 'style' and 'url(' not in (value or '').lower():
                safe.append('style="'+html.escape(value or '', quote=True)+'"')
        self.output.append('<'+tag+(' '+' '.join(safe) if safe else '')+'>')

    def handle_endtag(self, tag):
        if tag in self.allowed: self.output.append('</'+tag+'>')

    def handle_data(self, data): self.output.append(html.escape(data))


def render(text):
    doc = SafeDocument()
    doc.setMarkdown(text, QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
    from ui_typography import format_document
    format_document(doc)
    body = doc.toHtml().split('<body', 1)[1].split('>', 1)[1].rsplit('</body>', 1)[0]
    safe = SafeHtml(); safe.feed(body)
    return ''.join(safe.output)


def message_rows(messages):
    from answer_blocks import blocks
    rows = []; answer = ''
    for index, message in enumerate(messages):
        role = message.get('info', {}).get('role')
        if role not in ('assistant', 'user'): continue
        parts = message.get('parts', [])
        text = '\n\n'.join(p.get('text', '') for p in parts if p.get('type') == 'text' and not p.get('synthetic'))
        activity = [p.get('state', {}).get('title') or p.get('tool', tr('Werkzeug')) for p in parts if p.get('type') == 'tool' and p.get('state', {}).get('status') in ('running', 'pending')]
        if role == 'assistant' and text: answer = text
        if text or activity: rows.append(dict(key=message.get('info', {}).get('id', str(index)), role=role, text=text, body=render(text) if role == 'user' else '', blocks=blocks(text) if role == 'assistant' else [], activity=' · '.join(activity), actions=False))
    for row in reversed(rows):
        if row['role'] == 'assistant' and row['text']:
            row['actions'] = True
            break
    return rows, answer
