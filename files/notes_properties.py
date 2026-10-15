"""Small scalar property edits that preserve all unrelated Markdown/YAML bytes."""
from datetime import date
import json
import re
import yaml
from note_tags import FRONT
from lumen_i18n import tr


def document(text):
    front=FRONT.match(text)
    if not front:
        if text.startswith(('---\n','---\r\n')):raise ValueError(tr('Ungültige Notizeigenschaften.'))
        return None,None
    if len(front[1])>65536:raise ValueError(tr('Notizeigenschaften sind zu groß.'))
    try:node=yaml.compose(front[1],Loader=yaml.SafeLoader)
    except (yaml.YAMLError,RecursionError) as error:raise ValueError(tr('Ungültige Notizeigenschaften.')) from error
    if node is not None and (not isinstance(node,yaml.MappingNode) or node.flow_style):raise ValueError(tr('Eigenschaften zuerst als benannte YAML-Zeilen anlegen.'))
    if node and any(not isinstance(key,yaml.ScalarNode) or not key.tag.endswith(':str') for key,_ in node.value):raise ValueError(tr('Eigenschaftsnamen müssen Text sein.'))
    keys=[key.value for key,_ in node.value] if node else []
    if len(keys)!=len(set(keys)):raise ValueError(tr('Eine Eigenschaft ist mehrfach vorhanden.'))
    return front,node


def values(text):
    front,node=document(text);result={}
    for key,value in node.value if node else []:
        if not isinstance(key,yaml.ScalarNode) or not isinstance(value,yaml.ScalarNode) or key.value=='tags' or not re.fullmatch(r'[\w][\w .-]{0,79}',key.value):continue
        if not key.tag.endswith(':str') or not (value.tag.endswith(':str') or value.tag.endswith(':timestamp')):continue
        if value.start_mark.index<key.end_mark.index or front[1][value.start_mark.index:value.start_mark.index+1] in ('&','*'):continue
        kind='date' if value.tag.endswith(':timestamp') else 'text'
        if kind=='date':
            try:date.fromisoformat(value.value)
            except ValueError:continue
        result[key.value]=dict(kind=kind,value=value.value)
    return result


def for_note(note):
    front=FRONT.match(note['text']);source=front[1] if front else ''
    if note.get('_properties_source')!=source or '_properties' not in note:
        try:properties=values(note['text'])
        except ValueError:properties={}
        note['_properties_source']=source;note['_properties']=properties
    return note['_properties']


def change(text,name,kind='text',value='',remove=False):
    if not re.fullmatch(r'[\w][\w .-]{0,79}',name) or name=='tags':raise ValueError(tr('Einen Eigenschaftsnamen ohne Sonderzeichen wählen; Tags haben eine eigene Bedienung.'))
    if kind not in ('text','date') or len(value)>2000:raise ValueError(tr('Ungültiger Eigenschaftswert.'))
    if kind=='date' and not remove:
        try:parsed=date.fromisoformat(value)
        except ValueError as error:raise ValueError(tr('Datum als JJJJ-MM-TT eingeben.')) from error
        if parsed.isoformat()!=value:raise ValueError(tr('Datum als JJJJ-MM-TT eingeben.'))
    front,node=document(text);pairs=node.value if node else [];existing=next(((k,v) for k,v in pairs if k.value==name),None)
    encoded=value if kind=='date' else json.dumps(value,ensure_ascii=False)
    if existing:
        if name not in values(text):raise ValueError(tr('Diese komplexe oder verankerte Eigenschaft bleibt unverändert.'))
        key,val=existing;start=front.start(1)+val.start_mark.index;end=front.start(1)+val.end_mark.index
        if remove:
            start=text.rfind('\n',0,front.start(1)+key.start_mark.index)+1
            if not text[front.start(1)+val.start_mark.index:end].endswith('\n'):
                end=text.find('\n',end)
                if end<0:end=front.end(1)
                else:end+=1
            return text[:start]+text[end:]
        # Block scalars consume their final newline; retain separation from the next key.
        if text[start:end].endswith('\n'):encoded+='\n'
        return text[:start]+encoded+text[end:]
    if remove:return text
    line=json.dumps(name,ensure_ascii=False)+': '+encoded+'\n'
    if not front:return '---\n'+line+'---\n'+text
    return text[:front.start(1)]+line+text[front.start(1):]


def filters(query):
    selected=[]
    def collect(match):selected.append((match[1].strip(),match[2].strip().casefold()));return ' '
    text=re.sub(r'\[([^\[\]=\n]{1,80})=([^\[\]\n]{0,2000})\]',collect,query)
    return text,selected


def matches(text,selected):
    try:properties=values(text)
    except ValueError:return False
    return all(name in properties and properties[name]['value'].casefold()==value for name,value in selected)
