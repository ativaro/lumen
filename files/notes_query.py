"""Lookups over the notes a Notes window already holds: the list filter, link targets, the
connection map and the dates shown above a note. Reading and writing notes is the notebook core's
(native/service/src/notebook.rs, through wissen_data.py); these work on its answers in memory."""
from lumen_i18n import tr
import os
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit
from content_search import STOP_WORDS
from note_tags import matches_tags

MAX_SCAN_NOTES=10000


def timestamp(value):
    return value if type(value) in (int,float) and 0<value<253402214400 else 0


def timestamp_text(note):
    from datetime import datetime
    created=timestamp(note.get('created')) or timestamp(note.get('memory',{}).get('created'))
    modified=timestamp(note.get('modified')) or timestamp(note.get('memory',{}).get('updated'))
    def display(value):return datetime.fromtimestamp(value).strftime('%d.%m.%Y %H:%M') if value else ''
    first,last=display(created),display(modified)
    parts=[tr('Erstellt: {0}',first)] if first else []
    if last and last!=first:parts.append(tr('Geändert: {0}',last))
    return ' · '.join(parts)


def link_lookup(notes):
    lookup={}
    for path,note in notes.items():
        for key in {('id',note.get('note_id','')),('stem',Path(path).stem.casefold()),('title',note['title'].casefold())}:
            lookup[key]=path if key not in lookup else None
    return lookup


def resolve_link(origin,target,notes,lookup=None):
    target=unquote(target.split('|',1)[0].split('#',1)[0].strip())
    if not target:return origin
    if target.startswith('/?document='):
        identity=target.removeprefix('/?document=')
        if lookup is not None:return lookup.get(('id',identity))
        matches=[p for p,n in notes.items() if n.get('note_id')==identity]
        return matches[0] if len(matches)==1 else None
    if urlsplit(target).scheme or target.startswith(('/', '\\')):return None
    if not target.lower().endswith('.md'):target+='.md'
    local=os.path.normpath(str(Path(origin).parent/target))
    if local=='..' or local.startswith('../'):return None
    for candidate in (local,os.path.normpath(target)):
        if candidate in notes:return candidate
    if lookup is not None:
        keys={('stem',Path(target).stem.casefold()),('title',target[:-3].casefold())}
        matches={lookup[k] for k in keys if k in lookup}
        return next(iter(matches)) if len(matches)==1 and None not in matches else None
    matches=[p for p,n in notes.items() if Path(p).stem.casefold()==Path(target).stem.casefold() or n['title'].casefold()==target[:-3].casefold()]
    return matches[0] if len(matches)==1 else None


def connections(notes):
    lookup=link_lookup(notes);outgoing={};incoming={}
    for path,note in notes.items():
        outgoing[path]={target for link in note['links'] if (target:=resolve_link(path,link,notes,lookup)) in notes}
        for target in outgoing[path]:incoming.setdefault(target,set()).add(path)
    return outgoing,incoming


def search(notes,query,limit=60):
    from notes_properties import filters,for_note
    query,properties=filters(query)
    selected=re.findall(r'(?:^|\s)#([\w/-]+)',query)
    words=re.sub(r'(?:^|\s)#[\w/-]+',' ',query)
    terms=[w for w in re.findall(r'\w+',words.casefold()) if w not in STOP_WORDS and len(w)>1][:12]
    ranked=[]
    for note in notes:
        if properties:
            props=for_note(note)
            if not all(name in props and props[name]['value'].casefold()==value for name,value in properties):continue
        try:
            if selected and not matches_tags(note['tags'],selected):continue
        except ValueError:continue
        hay=(note['title']+' '+note['text']+' '+note['source']).casefold() if terms else ''
        score=sum((4 if t in note['title'].casefold() else 1) for t in terms if t in hay)
        if not terms or score:ranked.append((score,note))
    return [n for _,n in sorted(ranked,key=lambda p:(-p[0],p[1]['title'].casefold()))[:limit]]
