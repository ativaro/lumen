"""Notebook-local links and bounded embeds; never read paths or fetch resources."""
import os
from pathlib import Path
import re
from urllib.parse import quote,unquote,urlsplit
from lumen_i18n import tr
from note_tags import FRONT,body_mask
from notes_structure import split_target,targets,anchor_position
from wissen_data import resolve_link


def literal(value):return re.sub(r'([\\`*_\[\]<>])',r'\\\1',value)


def section(text,anchor):
    if not anchor:return FRONT.sub('',text,count=1)
    start=anchor_position(text,anchor)
    if start is None:return None
    if anchor.startswith('^'):
        end=text.find('\n\n',start)
        return text[start:end if end>=0 else len(text)]
    headings=[value for value in targets(text) if value['level']]
    level=next((value['level'] for value in headings if value['start']==start),6)
    end=next((value['start'] for value in headings if value['start']>start and value['level']<=level),len(text))
    return text[start:end]


def prepare(text,origin,notes):
    budget=[131072]
    root_parent=str(Path(origin).parent)
    def render(text,current,trail):
        text=FRONT.sub('',text,count=1);mask=body_mask(text)
        pattern=r'(?<!\\)(!?\[\[([^\]\n]+)\]\]|!?\[[^\]\n]*\]\(([^)\n]+)\))'
        def replacement(match):
            if not mask[match.start():match.start()+1].strip():return match[0]
            raw=match[2] or match[3];path_part,anchor=split_target(raw)
            if match[0].startswith('!'):
                if Path(unquote(path_part)).suffix.lower() in ('.png','.jpg','.jpeg','.gif','.webp'):
                    source=unquote(path_part)
                    if urlsplit(source).scheme or source.startswith(('/', '\\')):return match[0] if not match[2] else literal(tr('Bild nicht verfügbar'))
                    path=os.path.normpath(str(Path(current).parent/source))
                    if path=='..' or path.startswith('../'):return literal(tr('Bild nicht verfügbar'))
                    relative=os.path.relpath(path,root_parent)
                    return '!['+literal(Path(path).name)+']('+quote(relative,safe='/')+')'
                if not match[2]:return match[0]
                path=resolve_link(current,raw,notes)
                if path not in notes:return literal(tr('Eingebettete Notiz nicht gefunden.'))
                if path in trail:return literal(tr('Zyklische Einbettung – Quelle über den Link öffnen.'))
                if len(trail)>=4:return literal(tr('Weitere Einbettungen über die Quelle öffnen.'))
                content=section(notes[path]['text'],anchor)
                if content is None:return literal(tr('Eingebetteter Abschnitt nicht gefunden.'))
                if len(content)>budget[0]:return literal(tr('Einbettung zu groß – Quelle öffnen.'))
                budget[0]-=len(content)
                link='['+literal(notes[path]['title'])+'](lumen-note:/'+quote(path,safe='')+('#'+quote(anchor,safe='') if anchor else '')+')'
                content=render(content,path,trail+(path,))
                return '\n\n> '+link+'\n>\n'+'\n'.join('> '+line for line in content.splitlines())+'\n\n'
            path=resolve_link(current,raw,notes)
            if path is None:return match[0]
            title=(raw.split('|',1)[1] if '|' in raw else notes[path]['title'] if path in notes else raw) if match[2] else match[0][1:match[0].index('](')]
            return '['+literal(title)+'](lumen-note:/'+quote(path,safe='')+('#'+quote(anchor,safe='') if anchor else '')+')'
        return re.sub(pattern,replacement,text)
    return render(text,origin,(origin,))
