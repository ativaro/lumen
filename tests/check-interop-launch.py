#!/usr/bin/python3
"""Real cold/warm reviewed handoffs and lumen URI launch in a disposable profile."""
import hashlib,os,subprocess,sys,tempfile,time
from pathlib import Path
repo=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(repo/'files'))
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket
from interop_data import Registry
from tools_data import Library
app=QCoreApplication([])
binaries=Path(sys.argv[1]) if len(sys.argv)>1 else repo/'bin'

def wait(check,process):
    for _ in range(150):
        if process.poll() is not None:raise AssertionError('Application exited before handoff completed')
        if check():return
        time.sleep(.1)
    raise AssertionError('Handoff did not finish')

with tempfile.TemporaryDirectory(prefix='lumen-interop-launch-') as tmp:
    root=Path(tmp);tools=root/'tools'
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',HOME=tmp,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),LUMEN_TOOLS_DATA=str(tools),LUMEN_DATA=str(root/'state/lumen'),LUMEN_LANGUAGE='de')
    registry=Registry(tools);library=Library('workbench',tools)
    project=library.create('Native handoff',notes='Original',resources=[],questions=[])
    source=dict(app='files',kind='file',id=str(root/'source.txt'),title='Source',path=str(root/'source.txt'))
    (root/'source.txt').write_text('Source remains intact')
    url=registry.register(source)
    def queued(text):
        token=registry.enqueue('workbench','workbench.add',dict(title=text,text=text,source=source,source_url=url))
        # This models a target review already confirmed before a process restart.
        registry.save_choice(token,dict(id=project,title=text,mode='copy',due='',token=token))
        return token
    first=queued('Cold transfer')
    with tempfile.TemporaryFile() as log:
        process=subprocess.Popen([str(binaries/'lumen-workbench'),'--handoff',first],env=env,stdout=log,stderr=log)
        try:
            wait(lambda:registry.request(first)['state']=='done',process)
            second=queued('Warm transfer')
            subprocess.run([str(binaries/'lumen-workbench'),'--handoff',second],env=env,stdout=log,stderr=log,timeout=10,check=True)
            wait(lambda:registry.request(second)['state']=='done',process)
            subprocess.run([str(binaries/'lumen-open'),registry.request(first)['result']],env=env,stdout=log,stderr=log,timeout=10,check=True)
            subprocess.run([str(binaries/'lumen-workbench'),'--handoff',first],env=env,stdout=log,stderr=log,timeout=10,check=True)
            name='lumen-tool-'+str(os.getuid())+'-'+hashlib.sha256(str(library.root.resolve()).encode()).hexdigest()[:20]
            socket=QLocalSocket();socket.connectToServer(name);assert socket.waitForConnected(2000)
            socket.disconnectFromServer()
            record=library.get(project)
            assert record['notes'].count('Cold transfer')==1 and record['notes'].count('Warm transfer')==1,record['notes']
            assert (root/'source.txt').read_text()=='Source remains intact'
            assert len(library.all())==1
            print('cold/warm handoff, URI activation, endpoint and replay passed')
        except BaseException:
            log.seek(0);print(log.read().decode(errors='replace')[-5000:],file=sys.stderr);raise
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
