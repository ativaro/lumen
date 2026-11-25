"""Small scalar property edits that preserve all unrelated Markdown/YAML bytes. The service reads the front
matter and edits it (`notes.properties`, `notes.set_property`; native/service/src/notebook/)."""
import re
from note_tags import FRONT
from wissen_data import _ask


def values(text):
    """The simple named properties `{name: {kind, value}}`; ValueError for unusable front matter."""
    return _ask('properties', text=text)['properties']


def for_note(note):
    front=FRONT.match(note['text']);source=front[1] if front else ''
    if note.get('_properties_source')!=source or '_properties' not in note:
        try:properties=values(note['text'])
        except ValueError:properties={}
        note['_properties_source']=source;note['_properties']=properties
    return note['_properties']


def change(text,name,kind='text',value='',remove=False):
    return _ask('set_property',text=text,name=name,kind=kind,value=value,remove=remove)['text']


def filters(query):
    selected=[]
    def collect(match):selected.append((match[1].strip(),match[2].strip().casefold()));return ' '
    text=re.sub(r'\[([^\[\]=\n]{1,80})=([^\[\]\n]{0,2000})\]',collect,query)
    return text,selected


def matches(text,selected):
    try:properties=values(text)
    except ValueError:return False
    return all(name in properties and properties[name]['value'].casefold()==value for name,value in selected)
