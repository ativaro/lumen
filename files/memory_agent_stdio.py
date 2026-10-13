"""Expose only the two event-bound learning tools over Lumen's existing MCP transport."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from memory_agent import LearningSession, TOOLS


def serve(event):
    event=Path(event)
    data=json.loads(event.read_text())
    run=LearningSession(data['text'],data['candidates'],data['context'],solutions=data['solutions'])
    transport=Path(__file__).resolve().parent.parent/'bin/lumen_mcp.py'
    spec=importlib.util.spec_from_file_location('lumen_learning_transport',transport)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from lumen_store import Store
    from lumen_memory import stamp,options
    store=Store(data['store'])
    def check():
        current=options(store)
        if not current['enabled'] or not current['learn'] or stamp(store)!=data['stamp']:
            raise ValueError('Learning consent changed')
    def invoke(name,args):
        check()
        result=run.call(name,args)
        check()
        if run.items is not None:
            output=event.with_name('result.json')
            with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600),'w') as stream:
                json.dump(run.items,stream,ensure_ascii=False)
        return result
    from functools import partial
    module.TOOLS={t['name']:dict(desc=t['description'],schema=t['inputSchema'],fn=partial(invoke,t['name']),native=True) for t in TOOLS}
    for _ in range(20):
        line=sys.stdin.readline(32769)
        if not line:return
        if len(line)>32768:raise ValueError('Learning request too large')
        module.handle(json.loads(line))


if __name__=='__main__':serve(sys.argv[1])
