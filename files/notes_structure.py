"""Positions in portable Markdown; offsets refer to the unchanged source text."""
import re
import unicodedata
from urllib.parse import unquote
from note_tags import body_mask, FRONT


def split_target(target):
    path, separator, anchor = target.split('|', 1)[0].partition('#')
    return path, unquote(anchor) if separator else ''


def heading_name(value):
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', value)
    return re.sub(r'[*_`~]', '', value).strip()


def slug(value):
    return re.sub(r'\s+', '-', re.sub(r'[^\w\s-]', '', unicodedata.normalize('NFC', value).casefold()).strip())


def targets(text):
    mask = body_mask(text)
    result = []; offset = 0
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    masked = [mask[offsets[i]:offsets[i+1]] for i in range(len(lines))]
    for index, line in enumerate(lines):
        visible = masked[index] if index < len(masked) else ''
        match = re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line.rstrip('\r\n'))
        if match and visible.strip():
            title = heading_name(match[2])
            result.append(dict(title=title, anchor=title, start=offset, level=len(match[1])))
        elif index+1 < len(lines) and visible.strip() and re.fullmatch(r' {0,3}(?:=+|-+)\s*', masked[index+1]):
            title = heading_name(line.strip())
            result.append(dict(title=title, anchor=title, start=offset, level=1 if '=' in lines[index+1] else 2))
        block = re.search(r'(?:^|\s)\^([\w-]+)\s*$', visible.rstrip('\r\n'))
        if block:
            start = offset
            if not line[:block.start()].strip():
                previous = index-1
                # Standalone block IDs refer to the preceding paragraph/list.
                while previous >= 0 and not lines[previous].strip(): previous -= 1
                while previous >= 0 and masked[previous].strip():
                    start = offsets[previous]; previous -= 1
            result.append(dict(title='^'+block[1], anchor='^'+block[1], start=start, level=0))
        offset += len(line)
    return result


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
