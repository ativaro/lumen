"""Bounded IMAP/SMTP, local mail storage and calendar worker. No automatic sending."""
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, formatdate
import base64
import hashlib
import imaplib
import ipaddress
import json
import os
from pathlib import Path
import re
import smtplib
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit, urljoin
import uuid
from tools_data import Library, ArticleParser
from tools_secrets import secret

MAX_MAIL = 20*1024**2
MAX_HTTP = 8*1024**2


def calendar_python():
    path=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'lumen/inbox-env-v1/bin/python'
    if not path.is_file():raise ValueError('Kalenderanbindung fehlt. In der Einrichtung Inbox vorbereiten.')
    return str(path)


def store(root=None):
    library=Library('inbox',root)
    with library.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS messages (
            account TEXT, folder TEXT, validity TEXT, uid TEXT, thread TEXT, subject TEXT,
            sender TEXT, sent TEXT, body TEXT, raw BLOB, unread INTEGER,
            PRIMARY KEY(account,folder,validity,uid));
            CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, account TEXT, data TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT, due TEXT, source TEXT, done INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS calendar_cache(account TEXT, uid TEXT, data TEXT, PRIMARY KEY(account,uid));''')
    return library


def loopback(host):
    try:return ipaddress.ip_address(host).is_loopback
    except ValueError:return host.lower()=='localhost'


def validate_account(account):
    kind=account.get('kind')
    if kind not in ('imap','bridge','caldav','ics'):raise ValueError('Unbekannte Kontoart.')
    if kind in ('imap','bridge'):
        for key in ('host','smtp_host'):
            host=account.get(key,'').strip()
            if not host or any(c.isspace() or c in '/\\\0' for c in host):raise ValueError('Ungültiger Servername.')
            if kind=='bridge' and not loopback(host):raise ValueError('Proton Bridge muss auf diesem Rechner laufen.')
        for key in ('port','smtp_port'):
            if type(account.get(key)) is not int or not 1<=account[key]<=65535:raise ValueError('Ungültiger Server-Port.')
        if account.get('tls') not in ('ssl','starttls') or account.get('smtp_tls') not in ('ssl','starttls'):
            raise ValueError('TLS ist erforderlich.')
        if not account.get('username') or any(c in account['username'] for c in '\0\r\n'):raise ValueError('Gültiger Benutzername fehlt.')
        if kind=='bridge' and not re.fullmatch('[a-f0-9]{64}',account.get('fingerprint','')):
            raise ValueError('Zuerst das exportierte Bridge-Zertifikat auswählen.')
    else: secure_url(account.get('url',''))
    return account


def secure_url(value):
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Eine HTTPS-Adresse ohne eingebettete Zugangsdaten eingeben.')
    return value


def trust_context(account):
    if account['kind']=='bridge':
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
        return context
    return ssl.create_default_context(cafile=account.get('ca_file') or None)


def verify_peer(account,sock):
    if account['kind']=='bridge':
        if not ipaddress.ip_address(sock.getpeername()[0]).is_loopback:raise ValueError('Bridge-Verbindung verlässt diesen Rechner.')
        if hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()!=account['fingerprint']:
            raise ValueError('Bridge-Zertifikat geändert. Das aktuelle Zertifikat erneut in der Kontoeinrichtung auswählen.')


def connect_mail(account):
    validate_account(account);context=trust_context(account)
    client=None
    try:
        if account['tls']=='ssl':client=imaplib.IMAP4_SSL(account['host'],account['port'],ssl_context=context,timeout=15)
        else:
            client=imaplib.IMAP4(account['host'],account['port'],timeout=15);client.starttls(context)
        verify_peer(account,client.sock)
        original_read=client.read
        def bounded_read(size):
            if size>MAX_MAIL:raise ValueError('Nachricht überschreitet die Grenze von 20 MiB.')
            return original_read(size)
        client.read=bounded_read
        client.login(account['username'],secret('inbox',account['id']))
        return client
    except BaseException:
        if client:
            try:client.shutdown()
            except OSError:pass
        raise


def text_message(raw):
    message=BytesParser(policy=policy.default).parsebytes(raw)
    body=message.get_body(preferencelist=('plain','html')) if message.is_multipart() else message
    text=''
    if body and body.get_content_maintype()=='text':
        content=body.get_content()
        if body.get_content_type()=='text/html':
            parser=ArticleParser();parser.feed(content[:1024**2]);text=parser.text()
        else:text=str(content)
    ids=re.findall(r'<[^<>\s]{1,500}>',str(message.get('References','')) or str(message.get('In-Reply-To','')) or str(message.get('Message-ID','')))
    return dict(subject=str(message.get('Subject','(Ohne Betreff)'))[:1000],sender=str(message.get('From',''))[:1000],
        sent=str(message.get('Date',''))[:100],body=text[:120000],thread=ids[0] if ids else hashlib.sha256(raw).hexdigest())


def sync_mail(library,account,job,folder='INBOX'):
    if not folder or '\r' in folder or '\n' in folder:raise ValueError('Ungültiger Postfachordner.')
    client=connect_mail(account)
    try:
        status,_=client.select('"'+folder.replace('\\','\\\\').replace('"','\\"')+'"',readonly=True)
        if status!='OK':raise ValueError('Postfachordner nicht erreichbar.')
        response=client.response('UIDVALIDITY')[1]
        validity=response[0].decode() if response and response[0] else ''
        if not validity.isdecimal():raise ValueError('Der Server liefert keine stabile Postfachkennung.')
        status,result=client.uid('search',None,'ALL')
        if status!='OK':raise ValueError('Nachrichtenliste konnte nicht gelesen werden.')
        # ponytail: bounded recent cache; paginated history only when older mail is needed.
        uids=result[0].split()[-200:];fetched=[];skipped=0;total=0
        for uid in reversed(uids):
            job.check();status,metadata=client.uid('fetch',uid,'(RFC822.SIZE FLAGS)')
            meta=b' '.join(v for v in metadata if isinstance(v,bytes));size=re.search(rb'RFC822.SIZE (\d+)',meta)
            if status!='OK' or not size or int(size[1])>MAX_MAIL or total+int(size[1])>64*1024**2:skipped+=1;continue
            with library.connect() as db:existing=db.execute('SELECT raw FROM messages WHERE account=? AND folder=? AND validity=? AND uid=?',(account['id'],folder,validity,uid.decode())).fetchone()
            raw=existing['raw'] if existing else None
            if raw is None:
                status,data=client.uid('fetch',uid,f'(BODY.PEEK[]<0.{MAX_MAIL+1}>)')
                raw=next((v[1] for v in data if isinstance(v,tuple)),b'')
                if status!='OK' or not raw or len(raw)>MAX_MAIL:skipped+=1;continue
            total+=len(raw)
            if total>64*1024**2:skipped+=1;continue
            item=text_message(raw)
            fetched.append((account['id'],folder,validity,uid.decode(),item['thread'],item['subject'],item['sender'],item['sent'],item['body'],raw,int(b'\\Seen' not in meta)))
            job.progress.emit(f'{len(fetched)} Nachrichten geladen · {skipped} übersprungen')
        job.check()
        with library.connect() as db:
            db.execute('DELETE FROM messages WHERE account=? AND folder=?',(account['id'],folder))
            db.executemany('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)',fetched)
        library.update(account['id'],synced=time.time(),last_error='')
        return f'{len(fetched)} Nachrichten · {skipped} übersprungen · maximal 200 / 64 MiB pro Ordner'
    finally:
        try:client.logout()
        except (OSError,imaplib.IMAP4.error):client.shutdown()


def folders(account):
    client=connect_mail(account)
    try:
        status,values=client.list()
        if status!='OK':raise ValueError('Ordner konnten nicht gelesen werden.')
        result=[]
        for value in values[:200]:
            match=re.match(rb'\([^)]*\) (?:"[^"]*"|NIL) (.+)',value)
            if match and b'\\Noselect' not in value:
                name=match[1].decode('ascii',errors='replace').strip('"').replace('\\"','"').replace('\\\\','\\')
                result.append(name)
        return result
    finally:client.logout()


def folder_title(name):
    def decode(match):
        value=match[1]
        if not value:return '&'
        try:return base64.b64decode(value.replace(',','/')+'='*(-len(value)%4),validate=True).decode('utf-16-be')
        except (ValueError,UnicodeError):return match[0]
    return re.sub(r'&([A-Za-z0-9+,]*)-',decode,name)


def save_attachment(raw,index,destination):
    message=BytesParser(policy=policy.default).parsebytes(raw);parts=list(message.iter_attachments())
    if type(index) is not int or not 0<=index<len(parts):raise ValueError('Anhang nicht mehr verfügbar.')
    payload=parts[index].get_payload(decode=True)
    if payload is None or len(payload)>MAX_MAIL:raise ValueError('Anhang zu groß oder nicht lesbar.')
    path=Path(destination)
    with path.open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(payload)
    return str(path)


def save_draft(library,account,values,identity=None):
    allowed={key:str(values.get(key,'')) for key in ('to','subject','body','reply_to')}
    if len(allowed['body'])>120000:raise ValueError('Entwurf zu lang.')
    identity=identity or uuid.uuid4().hex
    with library.connect() as db:
        row=db.execute('SELECT status FROM drafts WHERE id=?',(identity,)).fetchone()
        if row and row['status']!='draft':raise ValueError('Bereits versandten oder unklaren Entwurf zuerst als neuen Entwurf kopieren.')
        db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?,?)',(identity,account,json.dumps(allowed),'draft'))
    return identity


def send_draft(library,identity,job):
    with library.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM drafts WHERE id=?',(identity,)).fetchone()
        if not row or row['status']!='draft':raise ValueError('Entwurf wurde bereits versandt oder muss geprüft werden.')
        values=json.loads(row['data']);account=validate_account(library.get(row['account']))
        for key in ('to','subject','reply_to'):
            if any(c in values[key] for c in '\r\n\0'):raise ValueError('Ungültige Nachrichtenkopfzeile.')
        recipients=[address for _,address in getaddresses([values['to']])]
        if not recipients or len(recipients)>20 or any('@' not in a for a in recipients):raise ValueError('Gültige Empfängeradresse erforderlich.')
        sender=account.get('address','')
        if not sender or any(c in sender for c in '\r\n\0') or '@' not in sender:raise ValueError('Absenderadresse in den Kontoeinstellungen ergänzen.')
        message=EmailMessage();message['From']=sender;message['To']=', '.join(recipients);message['Subject']=values['subject']
        message['Date']=formatdate(localtime=True);message['Message-ID']=make_msgid()
        if values['reply_to']:message['In-Reply-To']=values['reply_to'];message['References']=values['reply_to']
        message.set_content(values['body']);db.execute("UPDATE drafts SET status='sending' WHERE id=?",(identity,))
    smtp=None;submitted=False
    try:
        job.check();context=trust_context(account)
        if account['smtp_tls']=='ssl':smtp=smtplib.SMTP_SSL(account['smtp_host'],account['smtp_port'],timeout=20,context=context)
        else:
            smtp=smtplib.SMTP(account['smtp_host'],account['smtp_port'],timeout=20);smtp.ehlo();smtp.starttls(context=context);smtp.ehlo()
        verify_peer(account,smtp.sock);smtp.login(account.get('smtp_username') or account['username'],secret('inbox',account['id']))
        job.check();submitted=True
        refused=smtp.send_message(message,from_addr=sender,to_addrs=recipients)
        if refused:raise ValueError('Mindestens ein Empfänger wurde abgewiesen. Gesendet-Ordner prüfen, nicht blind erneut senden.')
        with library.connect() as db:db.execute("UPDATE drafts SET status='sent' WHERE id=?",(identity,))
        return 'Nachricht vom Mailserver angenommen.'
    except BaseException:
        with library.connect() as db:db.execute('UPDATE drafts SET status=? WHERE id=?',('uncertain' if submitted else 'draft',identity))
        raise
    finally:
        if smtp:smtp.close()


def calendar_client(account):
    import caldav
    validate_account(account);origin=urlsplit(account['url'])
    client=caldav.DAVClient(url=account['url'],username=account.get('username'),password=secret('inbox',account['id']),
        timeout=15,ssl_verify_cert=account.get('ca_file') or True,enable_rfc6764=False,rate_limit_handle=False)
    original=client.session.request
    def bounded(method,url,**kwargs):
        target=urlsplit(str(url));secure_url(str(url))
        if (target.scheme,target.hostname,target.port)!=(origin.scheme,origin.hostname,origin.port):
            raise ValueError('Der Kalender verweist auf einen anderen Server. Dessen Adresse als eigenes Konto einrichten.')
        kwargs.update(allow_redirects=False,stream=True)
        response=original(method,url,**kwargs)
        if 300<=response.status_code<400:response.close();raise ValueError('Bitte die endgültige Kalenderadresse eingeben (Weiterleitung abgelehnt).')
        data=bytearray()
        try:
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>MAX_HTTP:raise ValueError('Kalenderantwort zu groß.')
        finally:response.close()
        response._content=bytes(data);response._content_consumed=True
        return response
    client.session.request=bounded
    return client


def parse_calendar(data,expand=False):
    from icalendar import Calendar
    calendar=Calendar.from_ical(data);result=[]
    originals=calendar.walk('VEVENT')
    by_uid={str(e.get('uid','')):e for e in originals}
    series={str(e.get('uid','')) for e in originals if any(k in e for k in ('rrule','rdate','exdate','recurrence-id'))}
    events=originals[:1000]
    if expand:
        import recurring_ical_events
        from itertools import islice
        begin=datetime.now(timezone.utc)-timedelta(days=30);end=begin+timedelta(days=395)
        events=islice(recurring_ical_events.of(calendar).after(begin),1000)
    for event in events:
        start=event.decoded('dtstart',None);end=event.decoded('dtend',None)
        if expand and start and start.isoformat()[:10]>(datetime.now(timezone.utc)+timedelta(days=365)).date().isoformat():break
        original=by_uid.get(str(event.get('uid','')),event)
        body=Calendar();body.add('version','2.0');body.add('prodid','-//Lumen Inbox//DE')
        for zone in calendar.walk('VTIMEZONE'):body.add_component(zone)
        body.add_component(original)
        result.append(dict(uid=str(event.get('uid',''))[:500],title=str(event.get('summary','(Ohne Titel)'))[:1000],
            start=start.isoformat() if start else '',end=end.isoformat() if end else '',
            description=str(event.get('description',''))[:120000],location=str(event.get('location',''))[:1000],
            recurring=str(event.get('uid','')) in series,
            invited=bool(original.get('attendee') or original.get('organizer')),ics=body.to_ical().decode()))
    return result


def calendar_operation(account,action,values):
    if account['kind']=='ics':
        if action!='sync':raise ValueError('Kalender-Abonnements sind nur lesbar.')
        import urllib.request
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        # Subscription links can contain private tokens; retrieve from the keyring.
        url=secure_url(secret('inbox',account['id']))
        opener=urllib.request.build_opener(NoRedirect,urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(url,timeout=20) as response:data=response.read(MAX_HTTP+1)
        if len(data)>MAX_HTTP:raise ValueError('Kalender-Abonnement zu groß.')
        return parse_calendar(data,expand=True)
    client=calendar_client(account)
    try:
        if action=='calendars':return [{'url':str(c.url),'name':str(c.get_display_name())} for c in client.principal().calendars()[:100]]
        url=values.get('calendar') or account.get('calendar')
        if not url:raise ValueError('Zuerst einen Kalender auswählen.')
        calendar=client.calendar(url=url)
        if action=='sync':
            start=datetime.now(timezone.utc)-timedelta(days=30);end=start+timedelta(days=395)
            result=[]
            for event in calendar.search(start=start,end=end,event=True,expand=False)[:1000]:
                etag=event.etag;etag=getattr(etag,'text',etag)
                for item in parse_calendar(event.data,expand=True):result.append(dict(item,url=str(event.url),etag=str(etag) if etag is not None else ''))
                if len(result)>1000:raise ValueError('Mehr als 1000 Termine im Zeitraum. Kleineren Kalender auswählen.')
            return result
        if action=='save':
            from icalendar import Calendar, Event
            if values.get('recurring') or values.get('invited'):raise ValueError('Serien oder Einladungen im ursprünglichen Kalender bearbeiten.')
            start=datetime.fromisoformat(values['start']);end=datetime.fromisoformat(values['end'])
            if start.tzinfo is None or end.tzinfo is None or end<=start:raise ValueError('Gültigen Zeitraum mit Zeitzone wählen.')
            if not values.get('title','').strip():raise ValueError('Termintitel fehlt.')
            uid=values.get('uid') or uuid.uuid4().hex+'@lumen.local'
            body=Calendar();body.add('version','2.0');body.add('prodid','-//Lumen Inbox//DE')
            if values.get('url') and values.get('ics'):
                body=Calendar.from_ical(values['ics'])
                if len(body.walk('VEVENT'))!=1:raise ValueError('Mehrteiligen Termin im ursprünglichen Kalender bearbeiten.')
                event=body.walk('VEVENT')[0]
            else:event=Event();body.add_component(event)
            if values.get('url') and not values.get('ics'):raise ValueError('Originaltermin fehlt. Kalender erneut laden.')
            if any(key in event for key in ('rrule','rdate','exdate','recurrence-id','attendee','organizer')):
                raise ValueError('Serien oder Einladungen im ursprünglichen Kalender bearbeiten.')
            for key in ('uid','dtstamp','dtstart','dtend','duration','summary','description','location'):event.pop(key,None)
            event.add('uid',uid);event.add('dtstamp',datetime.now(timezone.utc));event.add('dtstart',start);event.add('dtend',end)
            for key,field in [('summary','title'),('description','description'),('location','location')]:event.add(key,str(values.get(field,''))[:120000])
            event['sequence']=int(event.get('sequence',0))+1
            url=values.get('url') or urljoin(str(calendar.url).rstrip('/')+'/',uuid.uuid4().hex+'.ics')
            headers={'Content-Type':'text/calendar; charset=utf-8'}
            if values.get('url'):
                if not values.get('etag'):raise ValueError('Kalender liefert keinen Änderungsschutz. Termin erneut laden.')
                headers['If-Match']=values['etag']
            else:headers['If-None-Match']='*'
            response=client.request(url,'PUT',body.to_ical(),headers)
            if response.status==412:raise ValueError('Der Termin wurde inzwischen geändert. Kalender erneut laden.')
            if response.status not in (200,201,204):raise ValueError('Kalender hat die Änderung nicht bestätigt.')
            return 'Termin gespeichert.'
        raise ValueError('Unbekannte Kalenderaktion.')
    finally:client.close()


def main():
    try:
        payload=json.load(sys.stdin);library=store();account=library.get(payload['account'])
        result=calendar_operation(account,payload['action'],payload.get('values',{}));print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as error:
        # Never echo URLs carrying subscription tokens or server response bodies.
        print(str(error) if isinstance(error,ValueError) else 'Kalender nicht erreichbar. Adresse, Zugang und Zertifikat prüfen.',file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
