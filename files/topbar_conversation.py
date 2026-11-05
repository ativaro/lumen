"""Pipe adapter for the existing native conversation controller; no second engine."""
import copy
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QSocketNotifier, QTimer


class ConversationPipe(QObject):
    def __init__(self, controller, output, parent=None):
        super().__init__(parent)
        self.controller=controller; self.output=output; self.width=680
        self.language=None
        self.refresh=QTimer(self); self.refresh.setSingleShot(True); self.refresh.setInterval(60)
        self.refresh.timeout.connect(self.publish)
        for signal in (controller.stateChanged,controller.messagesChanged,controller.requestsChanged,
                       controller.sessionsChanged,controller.themeChanged,controller.voiceChanged,
                       controller.answerChecksChanged,controller.queryChanged,controller.rich.changed,
                       controller.rich.valuesChanged,controller.rich.tablesChanged,controller.rich.stateChanged):
            signal.connect(lambda: self.refresh.start() if not self.refresh.isActive() else None)

    def snapshot(self):
        c=self.controller
        value={name:getattr(c,name) for name in ('messages','busy','status','error','session','theme','query',
                'permissions','questions','voiceActive','voiceStatus','voiceSetupRequired','execution','serverOrigin')}
        value['messages']=copy.deepcopy(value['messages'])
        value['note']=c.note_context
        value['title']=next((s['title'] for s in c.sessions if s['id'] and s['id']==c.session),c.text('Gespräch mit Lumen'))
        for message in value['messages']:
            for block in message.get('blocks',[]):
                if block.get('kind')=='table':block['body']=c.answer_table(block,self.width)
        r=c.rich
        value['rich']={name:getattr(r,name) for name in ('blocks','title','submitLabel','values','active','editable','canSubmit','tableRevision')}
        value['rich']['rows']={b['id']:r.table_rows(b['id']) for b in r.blocks if b['type']=='table'}
        value['steps']=[dict(title=p.get('state',{}).get('title') or p.get('tool',''),
                             status=p.get('state',{}).get('status',''))
                        for m in c.backend.messages for p in m.get('parts',[]) if p.get('type')=='tool']
        return value

    def write(self, value):
        self.output.write(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n');self.output.flush()

    def publish(self):
        from lumen_i18n import catalog,language
        state=self.snapshot();current=language()
        if current!=self.language:
            state['labels']=catalog() if current=='en' else {};self.language=current
        self.write({'state':state})

    def dispatch(self, value):
        identity=value.get('id','') if isinstance(value,dict) else ''
        try:
            if not isinstance(value,dict) or set(value)-{'method','args','id'}:raise ValueError('Invalid conversation request')
            method=value.get('method');args=value.get('args')
            if not isinstance(method,str) or not isinstance(args,list) or not isinstance(identity,str):raise ValueError('Invalid conversation request')
            c=self.controller
            commands={'stop':((),c.stop),'voice':((),c.toggle_voice),'voice_setup':((),c.open_voice_setup),'hidden':((),c.hidden),
                'permission':((str,bool),c.permission_reply),'question':((str,list),c.question_reply),
                'reject_question':((str,),c.skip_question),'open_link':((str,),c.open_link),
                'save':((bool,),c.capture_knowledge),
                'check':((str,str,bool),c.check_answer_item),
                'rich.set_value':((str,object),c.rich.set_value),'rich.filter_table':((str,str),c.rich.filter_table),
                'rich.sort_table':((str,int),c.rich.sort_table),'rich.select_row':((str,int),c.rich.select_row),
                'rich.export_table':((str,str),c.rich.export_table),
                'rich.open_file':((str,int),c.rich.open_file),'rich.submit':((),c.rich.submit)}
            if method=='submit':
                if len(args)!=2 or not isinstance(args[0],str) or not isinstance(args[1],dict):raise ValueError('Invalid prompt')
                prompt,note=args
                if not prompt.strip() or len(prompt)>4000 or '\0' in prompt:raise ValueError('Invalid prompt')
                if c.busy:raise ValueError(c.text('Bitte den laufenden Vorgang zuerst abschließen oder abbrechen.'))
                if note:
                    from topbar_context import validate_note
                    note=validate_note(note)
                c.note_context=note;c.set_query(prompt);c.submit(True)
                if c.query==prompt:raise ValueError(c.error or c.text('Die Frage konnte nicht gesendet werden.'))
            elif method=='width':
                if len(args)!=1 or type(args[0]) not in (int,float) or not 120<=args[0]<=10000:raise ValueError('Invalid content width')
                self.width=args[0]
            elif method=='draft':
                if len(args)!=2 or not isinstance(args[0],str) or not isinstance(args[1],dict) or len(args[0])>4000 or '\0' in args[0]:raise ValueError('Invalid conversation draft')
                if args[1]:
                    from topbar_context import validate_note
                    args[1]=validate_note(args[1])
                c.set_query(args[0]);c.note_context=args[1]
            elif method=='copy' and not args:
                self.write({'clipboard':c.last_answer})
            elif method=='reset' and not args:
                if c.busy:raise ValueError(c.text('Bitte den laufenden Vorgang zuerst abschließen oder abbrechen.'))
                draft,note=c.query,c.note_context
                c.reset();c.show_conversation();c.set_query(draft);c.note_context=note
            elif method=='rich.copy_table' and len(args)==1 and isinstance(args[0],str):
                self.write({'clipboard':c.rich.table_text(args[0],'\t')})
            elif method in commands:
                types,command=commands[method]
                if len(args)!=len(types) or any(t is not object and type(a) is not t for a,t in zip(args,types)):raise ValueError('Invalid conversation arguments')
                command(*args)
            else:raise ValueError('Unknown conversation action')
            self.write({'id':identity,'error':''})
        except (ValueError,TypeError,KeyError,OSError) as error:
            self.controller.show_error(str(error)[:400])
            self.write({'id':identity,'error':str(error)[:400]})
        self.publish()


def main():
    from PySide6.QtGui import QGuiApplication
    from search_controller import SearchController
    from lumen_i18n import install
    from lumen_crash import read_json,write_json
    from lumen_store import state_path
    app=QGuiApplication(['lumen-topbar-conversation']);app.setQuitOnLastWindowClosed(False);install(app)
    directory=Path(os.environ.get('LUMEN_WORKDIR') or QSettings('Lumen','Assistant').value('workdir',str(Path.home()/'Documents/work'))).expanduser()
    controller=SearchController(str(directory if directory.is_dir() else Path.home()),applications=[])
    controller.cancel_scan();controller.debounce.stop();controller.show_conversation()
    recovery=state_path()/'topbar-conversation.json'
    saved=read_json(recovery)
    if saved:
        try:
            controller.restore_recovery(saved)
            if saved.get('topbar_note'):
                from topbar_context import validate_note
                controller.note_context=validate_note(saved['topbar_note'])
        except (TypeError,ValueError,KeyError,OSError):controller.show_error(controller.text('Das gespeicherte Gespräch konnte nicht wiederhergestellt werden. Bitte in Lumen erneut öffnen.'))
    bridge=ConversationPipe(controller,sys.stdout,app)
    buffer=bytearray();fd=sys.stdin.fileno();os.set_blocking(fd,False)
    notifier=QSocketNotifier(fd,QSocketNotifier.Read,app)
    def read():
        try:data=os.read(fd,65536)
        except BlockingIOError:return
        if not data:app.quit();return
        buffer.extend(data)
        while b'\n' in buffer:
            line,_,rest=buffer.partition(b'\n');buffer[:]=rest
            if len(line)>65536:bridge.write({'id':'','error':'Invalid conversation request'});continue
            try:request=json.loads(line)
            except (ValueError,UnicodeError):bridge.write({'id':'','error':'Invalid conversation request'});continue
            if isinstance(request,dict) and request.get('method')=='close':app.quit();return
            bridge.dispatch(request)
        if len(buffer)>65536:buffer.clear();bridge.write({'id':'','error':'Invalid conversation request'})
    notifier.activated.connect(read)
    previous=None
    def save():
        nonlocal previous
        try:
            state=controller.recovery_state();state['topbar_note']=controller.note_context
            if state!=previous:write_json(recovery,state);previous=copy.deepcopy(state)
        except (OSError,ValueError,TypeError):controller.show_error(controller.text('Der Gesprächsentwurf konnte nicht gespeichert werden.'))
    timer=QTimer(app);timer.setInterval(1000);timer.timeout.connect(save);timer.start()
    app.aboutToQuit.connect(save);app.aboutToQuit.connect(controller.shutdown)
    bridge.publish();app.exec()
