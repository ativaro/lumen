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
            result.extend(r for r in item['materials']['items'] if r['kind']=='folder')
            offset=item['materials']['next_offset']
            if offset is None:break
    return result,revisions


def search(identity, query):
    # shortcut: lexical on-demand scan; add incremental hybrid retrieval for large collections.
    from content_search import query_groups
    from lumen_jobs import Job
    refs,revisions=sources(identity)
    roots=list(dict.fromkeys(r['target'] for r in refs))
    if len(roots)>20:raise ValueError('More than 20 linked folders. Search a narrower project item.')
    groups=query_groups(query)
    job=Job(lambda _:None)
    data=job.command([sys.executable,__file__,'--scan'],data=json.dumps(dict(roots=roots,groups=groups)).encode(),timeout=30,max_output=256*1024)
    result=json.loads(data)
    if sources(identity)!=(refs,revisions):raise ValueError('Project sources changed during search. Search again.')
    result.update(query=query,coverage='Current text and text-bearing PDFs in linked folders and subfolders only. Hidden files, symlinks, unsupported formats and OCR-only images are excluded. No persistent index; limits/errors/empty/partial must be reported. No claim that every project file was read.')
    return result


def scan(roots,groups):
    from content_search import folder_fd,scan_tree
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
    return dict(items=hits,folders=folders,unsearched_folders=len(roots)-len(folders),hit_limit=40)


if __name__=='__main__' and sys.argv[1:]==['--scan']:
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024*1024,1024*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024*1024,4*1024*1024))
    request=json.load(sys.stdin)
    print(json.dumps(scan(request['roots'],request['groups'])))
