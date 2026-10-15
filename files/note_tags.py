"""Portable tag identities and narrowly scoped, source-preserving tag edits."""
import json
import re
import unicodedata

import yaml
from lumen_i18n import tr

FRONT = re.compile(r'\A---\r?\n([\s\S]*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)')
TAG = re.compile(r'(?<![\w/#\\])#([\w/-]+)')


def identity(value):
    value = unicodedata.normalize('NFC', value.strip().lstrip('#')).casefold()
    if not re.fullmatch(r'[\w/-]+', value) or not any(not c.isdigit() and c!='/' for c in value) or any(not part for part in value.split('/')):
        raise ValueError(tr('Ungültiger Tag.'))
    return value


def frontmatter(text):
    match = FRONT.match(text)
    if not match: return None, None
    if len(match[1]) > 65536: raise ValueError(tr('Notizeigenschaften sind zu groß.'))
    try: node = yaml.compose(match[1], Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError) as error: raise ValueError(tr('Ungültige Notizeigenschaften.')) from error
    if node is not None and not isinstance(node, yaml.MappingNode): raise ValueError(tr('Notizeigenschaften benötigen benannte Felder.'))
    pairs = [(key, value) for key, value in node.value if key.value=='tags'] if node else []
    if len(pairs)>1: raise ValueError(tr('Das Tags-Feld ist mehrfach vorhanden.'))
    return match, pairs[0] if pairs else None


def yaml_tags(pair):
    if not pair: return []
    _, value = pair
    values = value.value if isinstance(value, yaml.SequenceNode) else [value]
    result = []
    for node in values:
        if not isinstance(node, yaml.ScalarNode): raise ValueError(tr('Tags müssen Text oder eine Liste aus Text sein.'))
        if node.tag.endswith(':null'): continue
        result.extend(node.value.split(',') if not isinstance(value, yaml.SequenceNode) else [node.value])
    return result


def body_mask(text):
    # Retain offsets while excluding literal code, link destinations and metadata.
    chars = list(text)
    front = FRONT.match(text)
    if front: chars[:front.end()] = ' ' * front.end()
    offset = 0; fence = ''
    for line in text.splitlines(keepends=True):
        marker = re.match(r' {0,3}(`{3,}|~{3,})', line)
        was_fenced = bool(fence)
        if marker:
            if not fence: fence = marker[1]
            elif marker[1][0]==fence[0] and len(marker[1])>=len(fence) and not line[marker.end():].strip(): fence = ''
        if was_fenced or marker: chars[offset:offset+len(line)] = ' '*len(line)
        offset += len(line)
    masked = ''.join(chars)
    return re.sub(r'(`+)[\s\S]*?\1|\]\([^\n)]*\)', lambda match:' '*len(match[0]), masked)


def tags(text):
    values = [match[1] for match in TAG.finditer(body_mask(text))]
    try: values += yaml_tags(frontmatter(text)[1])
    except ValueError: pass  # Invalid metadata remains editable and is never rewritten here.
    result = set()
    for value in values:
        try: result.add(identity(value))
        except ValueError: continue
    return sorted(result)[:100]


def matches_tags(values, selected):
    normalized = {identity(value) for value in values}
    return all(any(tag==identity(wanted) or tag.startswith(identity(wanted)+'/') for tag in normalized) for wanted in selected)


def add_tag(text, tag):
    tag = identity(tag)
    if tag in tags(text): return text
    if len(tags(text)) >= 100: raise ValueError(tr('Maximal 100 Tags pro Notiz.'))
    match, pair = frontmatter(text)
    if text.startswith('---\n') and not match:
        raise ValueError(tr('Ungültige Notizeigenschaften.'))
    if not match: return '---\ntags: '+json.dumps([tag], ensure_ascii=False)+'\n---\n'+text
    if not pair:
        node = yaml.compose(match[1], Loader=yaml.SafeLoader)
        if node is not None and node.flow_style:
            raise ValueError(tr('Tags in kompakten Notizeigenschaften zuerst im Quelltext anlegen.'))
        return text[:match.start(1)]+'tags: '+json.dumps([tag], ensure_ascii=False)+'\n'+text[match.start(1):]
    key, value = pair
    if value.start_mark.index < key.end_mark.index or '&' in match[1][key.end_mark.index:value.start_mark.index+1]:
        raise ValueError(tr('Verankerte Tags zuerst in unabhängige Werte umwandeln.'))
    current = yaml_tags(pair)
    changed = sorted({identity(item) for item in current} | {tag})
    start, end = value.start_mark.index, value.end_mark.index
    suffix = '\n' if match[1][start:end].endswith('\n') else ''
    padding = ' ' if text[match.start(1)+start-1:match.start(1)+start] == ':' else ''
    return text[:match.start(1)+start]+padding+json.dumps(changed, ensure_ascii=False)+suffix+text[match.start(1)+end:]


def rename_tag(text, old, new, *, descendants=True):
    old = identity(old); new = identity(new) if new else ''
    def replacement(value):
        value = identity(value)
        if value==old or (descendants and value.startswith(old+'/')):
            return new+value[len(old):] if new else ''
        return value
    match, pair = frontmatter(text)
    edits = []
    if pair:
        key, value = pair
        if value.start_mark.index < key.end_mark.index or '&' in match[1][key.end_mark.index:value.start_mark.index+1]:
            raise ValueError(tr('Verankerte Tags zuerst in unabhängige Werte umwandeln.'))
        current = yaml_tags(pair)
        changed = sorted({replacement(tag) for tag in current if replacement(tag)})
        if changed != sorted({identity(tag) for tag in current}):
            start, end = value.start_mark.index, value.end_mark.index
            suffix = '\n' if match[1][start:end].endswith('\n') else ''
            edits.append((match.start(1)+start, match.start(1)+end, json.dumps(changed, ensure_ascii=False)+suffix))
    for token in TAG.finditer(body_mask(text)):
        try: result = replacement(token[1])
        except ValueError: continue
        if result != identity(token[1]): edits.append((token.start(), token.end(), '#'+result if result else ''))
    for start, end, value in sorted(edits, reverse=True): text = text[:start]+value+text[end:]
    return text
