"""Fresh, bounded retrieval from explicitly linked folders; no persistent content copy."""
import json
import os
from pathlib import Path
import sys


def sources(identity):
    from projects_mcp import invoke
    result=[]; revisions={}
    current=invoke('lumen_project_read',dict(id=identity))
    for key in [identity]+[item['id'] for item in current['ancestors']]:
        offset=0
        while True:
            item=invoke('lumen_project_read',dict(id=key,limit=100,offset=offset))
            revision=item['item']['revision']
            if key in revisions and revision!=revisions[key]:raise ValueError('Project changed. Read it again.')
            revisions[key]=revision
            result.extend(r for r in item['materials']['items'] if r['kind'] in {'folder','file'})
            result.extend(r for r in item['references']['items'] if r['kind']=='chat')
            offset=item['materials']['next_offset']
            if offset is None:break
    return result,revisions


def search(identity, query):
    # shortcut: lexical on-demand scan; add incremental hybrid retrieval for large collections.
    from content_search import query_groups
    from lumen_jobs import Job
    refs,revisions=sources(identity)
    roots=list(dict.fromkeys(r['target'] for r in refs if r['kind']=='folder'))
    files=list(dict.fromkeys(r['target'] for r in refs if r['kind']=='file'))
    chats=[r for r in refs if r['kind']=='chat']
    if len(roots)>20:raise ValueError('More than 20 linked folders. Search a narrower project item.')
    if len(files)+len(chats)>100:raise ValueError('More than 100 linked files/conversations. Search a narrower project item.')
    groups=query_groups(query)
    job=Job(lambda _:None)
    data=job.command([sys.executable,__file__,'--scan'],data=json.dumps(dict(roots=roots,files=files,chats=chats,groups=groups)).encode(),timeout=30,max_output=256*1024)
    result=json.loads(data)
    if sources(identity)!=(refs,revisions):raise ValueError('Project sources changed during search. Search again.')
    result.update(query=query,coverage='Current text, text-bearing PDF and DOCX/PPTX/XLSX body/slide/cell text (including macro-enabled text only) in linked files/folders and subfolders, plus locally saved turns/results of explicitly linked conversations. Office formulas use saved values, never execution; embedded images/charts are not interpreted. Conversation answers are previous AI output, not independent evidence or a guarantee of current facts. Hidden files, symlinks, unsupported formats, archive contents, OCR-only images and unavailable conversation history are excluded. No persistent index; limits/errors/empty/partial must be reported. No claim that every project file was read.')
    return result


def scan(roots,groups,files=(),chats=()):
    from content_search import folder_fd,scan_tree,read_content,find_passage
    hits=[];folders=[]
    for root in roots:
        path=Path(root)
        if not path.is_absolute():raise ValueError('Linked folder must be absolute.')
        descriptor=None
        try:
            base=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
            try:descriptor=folder_fd(base,path.relative_to('/'))
            finally:os.close(base)
            before=os.fstat(descriptor);events=[];summary=None
            for event in scan_tree(path,descriptor,groups,False,40-len(hits),5000,visual=False):
                if event['type']=='hit':events.append(event)
                elif event['type']=='done':summary=event
            # Refuse a root replaced while its pinned descriptor was being scanned.
            current=os.stat(path,follow_symlinks=False)
            if (before.st_dev,before.st_ino)!=(current.st_dev,current.st_ino):raise ValueError('Folder changed during search.')
            hits.extend(events);folders.append(dict(path=root,**summary))
            if len(hits)>=40:break
        except (OSError,ValueError) as error:
            folders.append(dict(path=root,error=str(error),incomplete=True))
        finally:
            if descriptor is not None:os.close(descriptor)
    documents=[]
    for filename in files:
        if len(hits)>=40:break
        path=Path(filename);descriptor=None
        try:
            if not path.is_absolute():raise ValueError('Linked file must be absolute.')
            base=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
            try:descriptor=folder_fd(base,path.parent.relative_to('/'))
            finally:os.close(base)
            from core import file_kind
            from document_text import EXTENSIONS
            if file_kind(path) not in {'text','pdf'} and path.suffix.lower() not in EXTENSIONS:
                raise ValueError('Unsupported source format.')
            text,partial=read_content(path,descriptor)
            passage=find_passage(text,groups)
            if passage:hits.append(dict(passage,type='hit',path=str(path),partial=partial))
            documents.append(dict(path=str(path),partial=partial,empty=not bool(text.strip())))
        except (OSError,ValueError) as error:
            documents.append(dict(path=str(path),error=str(error),incomplete=True))
        finally:
            if descriptor is not None:os.close(descriptor)
    conversations=[]
    for reference in chats:
        if len(hits)>=40:break
        chat=reference['chat'];status=dict(chat=chat,title=reference['title'])
        from lumen_store import state_path
        database=state_path()/'lumen.sqlite3'
        rows=[]
        if database.is_file() and not chat['session'].startswith('lumen-server/'):
            import sqlite3
            from contextlib import closing
            try:
                with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
                    rows=db.execute('SELECT id,substr(prompt,1,20000),substr(result,1,40000),status,updated,length(prompt)>20000 OR length(result)>40000 FROM tasks WHERE directory=? AND session=? ORDER BY created LIMIT 101',
                                    (chat['directory'],chat['session'])).fetchall()
            except sqlite3.Error as error:
                status['error']=str(error)[:200]
        status.update(turns=min(len(rows),100),partial=len(rows)>100,unavailable=not bool(rows))
        for task,prompt,answer,state,updated,truncated in rows[:100]:
            for role,text in [('user',prompt),('assistant',answer)]:
                passage=find_passage(text,groups)
                if passage:
                    hits.append(dict(passage,type='hit',kind='chat',chat=chat,title=reference['title'],task=task,role=role,status=state,updated=updated,partial=bool(truncated),saved_turns_only=True))
                if len(hits)>=40:break
            if len(hits)>=40:break
        conversations.append(status)
    return dict(items=hits,folders=folders,documents=documents,conversations=conversations,
                unsearched_folders=len(roots)-len(folders),unsearched_files=len(files)-len(documents),unsearched_conversations=len(chats)-len(conversations),hit_limit=40)


if __name__=='__main__' and sys.argv[1:]==['--scan']:
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024*1024,1024*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024*1024,4*1024*1024))
    request=json.load(sys.stdin)
    print(json.dumps(scan(request['roots'],request['groups'],request.get('files',[]),request.get('chats',[]))))
