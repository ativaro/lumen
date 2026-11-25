"""Positions in portable Markdown; offsets refer to the unchanged source text. The headings and block IDs
come from the service (`notes.targets`)."""
import re
import unicodedata
from urllib.parse import unquote
from note_tags import FRONT
from wissen_data import _ask


def split_target(target):
    path, separator, anchor = target.split('|', 1)[0].partition('#')
    return path, unquote(anchor) if separator else ''


def slug(value):
    return re.sub(r'\s+', '-', re.sub(r'[^\w\s-]', '', unicodedata.normalize('NFC', value).casefold()).strip())


def targets(text):
    """Headings (`level` 1 to 6) and block IDs (`^id`, level 0) outside code: `title`, `anchor`, `start`
    (the code point where they begin) and `level`, from the service (`notes.targets`)."""
    return _ask('targets', text=text)['targets']


def anchor_position(text, anchor):
    anchor = unicodedata.normalize('NFC', unquote(anchor)).strip()
    if not anchor: return 0
    values = targets(text)
    exact = [value for value in values if unicodedata.normalize('NFC',value['anchor']).casefold() == anchor.casefold()]
    if exact: return exact[0]['start'] if len(exact)==1 or not anchor.startswith('^') else None
    if anchor.startswith('^'): return None
    matches = [value for value in values if value['level'] and slug(value['anchor'])==slug(anchor)]
    return matches[0]['start'] if matches else None


def document_parts(text, fallback):
    for value in targets(text):
        if value['level'] != 1: continue
        match = re.match(r'# ([^\n]*)(\n*)', text[value['start']:])
        if match:
            start = value['start']
            return text[:start], match[1], match[2], text[start+match.end():], True
    front = FRONT.match(text)
    prefix = front[0] + re.match(r'(?:\r?\n)*', text[front.end():])[0] if front else ''
    return prefix, fallback, '\n\n', text[len(prefix):], False
