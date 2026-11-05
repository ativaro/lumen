"""Native presentation of the shared Server reader; no local Office parser."""
import html
import json
import re
import os
import stat
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser
from lumen_i18n import tr
from tools_ui import button, label, row
from desktop_design import AppHeader

OFFICE = {'.docx','.docm','.xlsx','.xlsm','.pptx','.pptm','.odt','.ods','.odp'}


def read_file(path, offset, job, config):
    import lumen_connect
    from drive_http import Session
    if not config.get('token'):
        raise ValueError(tr('Bitte Lumen Server verbinden und Drive für dieses Gerät freigeben.'))
    if lumen_connect.read_config()!=config:
        raise ValueError(tr('Die Serververbindung wurde geändert. Bitte das Dokument erneut öffnen.'))
    path = Path(path)
    job.check()
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC),'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):raise ValueError(tr('Bitte eine reguläre Dokumentdatei öffnen.'))
        request = Request(config['server']+'/bridge/drive/documents/read?'+urlencode(dict(format=path.suffix.lower().lstrip('.'), offset=offset)),
                          data=source, headers={'Authorization':'Bearer '+config['token'],
                          'Content-Type':'application/octet-stream', 'Content-Length':str(before.st_size)})
        session = Session(config)
        try:
            job.check()
            with session.open(request, timeout=180) as response:
                raw = response.read(4*1024**2+1)
            job.check()
            after = os.fstat(source.fileno())
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise ValueError(tr('Die Datei wurde während des Lesens geändert. Bitte erneut öffnen.'))
            if len(raw)>4*1024**2: raise ValueError(tr('Die Readerantwort ist zu groß.'))
            if lumen_connect.read_config()!=config: raise ValueError(tr('Die Serververbindung wurde geändert.'))
            return json.loads(raw)
        except Exception as error:
            from urllib.error import HTTPError
            if isinstance(error, HTTPError):
                try: message=json.loads(error.read(8192)).get('detail')
                except (ValueError,UnicodeError): message=None
                raise ValueError(message or tr('Das Dokument konnte auf dem Server nicht gelesen werden.')) from None
            raise
        finally: session.close()


def reading_html(value, offset):
    parts=[]
    for block in value['blocks'] or [dict(start=offset,end=offset+len(value['text']),location={})]:
        location=block['location']; text=value['text'][max(0,block['start']-offset):max(0,block['end']-offset)]
        title=tr('Dokument')
        if 'sheet' in location: title=tr('Tabellenblatt')+' '+str(location['sheet'])
        elif 'slide' in location: title=tr('Folie')+' '+str(location['slide'])
        elif location.get('part') and location['part']!='word/document.xml': title=tr('Dokumentteil')
        text='\n'.join(re.sub(r'^Paragraph \d+: ', '', line.removeprefix(str(location.get('part',''))+' · ')) for line in text.splitlines() if line!=f"Slide {location.get('slide')}")
        parts.append('<h3>'+html.escape(title)+'</h3><p style="white-space:pre-wrap">'+html.escape(text)+'</p>')
    return ''.join(parts)


class ServerDocument(QDialog):
    def __init__(self, reader, path):
        super().__init__(reader)
        import lumen_connect
        from urllib.parse import urlsplit
        self.config=lumen_connect.read_config()
        self.reader=reader; self.path=Path(path); self.offset=0; self.history=[]; self.next=None
        self.setWindowTitle(tr('Lumen Reader')+' · '+self.path.name); self.resize(900,700)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,24,24,24);layout.setSpacing(16)
        server=urlsplit(self.config.get('server','')).hostname or tr('kein Server verbunden')
        header=AppHeader(self.path.name,tr('Inhaltsansicht über {0}. Das Original wird dort nicht gespeichert.',server),self)
        layout.addWidget(header)
        self.start=button(tr('Inhalt auf Lumen Server lesen'),self.load,'document-open');layout.addWidget(self.start)
        self.text=QTextBrowser();self.text.setOpenExternalLinks(False);self.text.setAccessibleName(tr('Dokumentinhalt'));layout.addWidget(self.text,1)
        self.previous=button(tr('Voriger Abschnitt'),self.back,'go-previous')
        self.forward=button(tr('Weiterlesen'),self.more,'go-next')
        self.state=label('');layout.addWidget(row(self.previous,self.state,self.forward,button(tr('Schließen'),self.close,'window-close')))
        self.previous.setEnabled(False);self.forward.setEnabled(False)

    def load(self):
        self.start.setEnabled(False)
        self.state.setText(tr('Dokument wird auf dem Server gelesen …'))
        self.previous.setEnabled(False);self.forward.setEnabled(False);self.text.clear()
        self.reader.work(tr('Dokument wird gelesen …'),lambda job:read_file(self.path,self.offset,job,self.config),self.loaded,failed=self.failed)

    def failed(self,message):
        self.state.setText(message);self.start.setEnabled(True)

    def loaded(self,value):
        self.text.setHtml(reading_html(value,self.offset));self.next=value['next_offset']
        self.start.setText(tr('Inhalt erneut lesen'));self.start.setEnabled(True)
        self.previous.setEnabled(bool(self.history));self.forward.setEnabled(self.next is not None)
        self.state.setText(tr('Ende des Dokuments') if self.next is None else tr('Weiterer Inhalt verfügbar'))

    def more(self):
        if self.next is not None:
            self.history.append(self.offset);self.offset=self.next;self.load()

    def back(self):
        if self.history:self.offset=self.history.pop();self.load()
