"""Explicit desktop inputs. Pasted messages/events never imply a live connector."""
from datetime import datetime
from zoneinfo import ZoneInfo
from code_block_paths import source


def read(value, store, job, event=None):
    value=source(value);kind=value['kind'];now=datetime.now(ZoneInfo('Europe/Zurich'))
    result={'weekday':now.weekday(),'hour':now.hour,'success':True}
    if kind=='file':
        from code_blocks_run import read_file
        if value.get('trigger',{}).get('kind')=='directory':
            from code_triggers import file_event
            if not event or file_event(value,event.get('path',''))!={k:event.get(k) for k in ('path','stamp','root')}:
                raise ValueError('Die Beispieldatei fehlt oder wurde nach dem Auslösen geändert.')
            result.update(read_file(event['path'],job,event['stamp']))
        else:result.update(read_file(value.get('path',''),job))
    elif kind=='project':
        from code_triggers import project_snapshot
        current=project_snapshot(value.get('project_id',''),store)
        snapshot=event.get('project') if event else None
        if snapshot and snapshot.get('project_id')!=current['project_id']:raise ValueError('Das Ereignis gehört zu einem anderen Projekt.')
        result.update(snapshot or current)
    else:
        result['text']=value.get('text','')
        for key in ('sender','subject','has_attachment'):
            if key in value:result[key]=value[key]
    return result
