"""Explicit desktop inputs. Pasted messages/events never imply a live connector."""
from datetime import datetime
from zoneinfo import ZoneInfo
from code_block_paths import source


def read(value, store, job):
    value=source(value);kind=value['kind'];now=datetime.now(ZoneInfo('Europe/Zurich'))
    result={'weekday':now.weekday(),'hour':now.hour,'success':True}
    if kind=='file':
        from code_blocks_run import read_file
        result.update(read_file(value.get('path',''),job))
    elif kind=='project':
        from lumen_projects import projects
        project=next((p for p in projects(store) if p['id']==value.get('project_id')),None)
        if project is None:raise ValueError('Das ausgewählte Lumen-Projekt ist nicht mehr verfügbar.')
        result.update(project_id=project['id'],text=project['name']+'\n'+project.get('note',''))
        if isinstance(project.get('status'),str):result['project_status']=project['status']
    else:
        result['text']=value.get('text','')
        for key in ('sender','subject','has_attachment'):
            if key in value:result[key]=value[key]
    return result
