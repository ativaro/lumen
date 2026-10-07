"""Real loopback TLS protocols; no personal account or external mail required."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socketserver
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
import inbox_data as inbox


class Job:
    class Signal:
        def emit(self,value):pass
    progress=Signal()
    def check(self):pass


class MailServer(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True


class MailHandler(socketserver.StreamRequestHandler):
    def setup(self):
        if not self.server.starttls:self.request=self.server.context.wrap_socket(self.request,server_side=True)
        super().setup()
    def upgrade(self):
        self.rfile.close();self.wfile.close()
        self.request=self.server.context.wrap_socket(self.request,server_side=True)
        self.rfile=self.request.makefile('rb');self.wfile=self.request.makefile('wb',buffering=0)
    def finish(self):
        try:super().finish()
        finally:self.request.close()
    def send(self,text):self.wfile.write(text.encode()+b'\r\n');self.wfile.flush()
    def handle(self):
        smtp=self.server.smtp;self.send('220 localhost test SMTP' if smtp else '* OK IMAP test')
        while line:=self.rfile.readline(65536):
            words=line.decode().strip().split();tag=words[0];command=words[0].upper() if smtp else words[1].upper()
            if smtp:
                if command=='EHLO':self.send('250-localhost');self.send('250-STARTTLS');self.send('250 AUTH PLAIN')
                elif command=='STARTTLS':self.send('220 Ready');self.upgrade()
                elif command=='AUTH':self.server.logins+=1;self.send('235 Authenticated')
                elif command in ('MAIL','RCPT','RSET'):self.send('250 OK')
                elif command=='DATA':
                    self.send('354 Send data');data=bytearray()
                    while (part:=self.rfile.readline())!=b'.\r\n':
                        if not part:return
                        data.extend(part)
                    self.server.deliveries.append(bytes(data))
                    if self.server.drop:return
                    self.send('250 Accepted')
                elif command=='QUIT':self.send('221 Bye');return
                else:self.send('500 Unknown')
            else:
                if command=='CAPABILITY':self.send('* CAPABILITY IMAP4rev1 STARTTLS')
                elif command=='STARTTLS':self.send(tag+' OK start TLS');self.upgrade();continue
                elif command=='LOGIN':self.server.logins+=1
                elif command=='EXAMINE':self.send('* 1 EXISTS');self.send('* OK [UIDVALIDITY 42] stable')
                elif command=='UID':
                    if words[2].upper()=='SEARCH':self.send('* SEARCH 7')
                    elif 'RFC822.SIZE' in line.decode():self.send(f'* 1 FETCH (UID 7 RFC822.SIZE {len(self.server.raw)} FLAGS (\\Seen))')
                    else:
                        if self.server.oversize:self.send(f'* 1 FETCH (UID 7 BODY[] {{{inbox.MAX_MAIL+1}}}');return
                        self.send(f'* 1 FETCH (UID 7 BODY[] {{{len(self.server.raw)}}}')
                        self.wfile.write(self.server.raw);self.send(')')
                elif command=='LIST':self.send('* LIST (\\HasNoChildren) "/" "INBOX"')
                elif command=='LOGOUT':self.send('* BYE bye');self.send(tag+' OK done');return
                self.send(tag+' OK done')


class CalendarHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,status,data='',mime='application/xml'):
        data=data.encode() if isinstance(data,str) else data;self.send_response(status)
        if status==401:self.send_header('WWW-Authenticate','Basic realm="local test"')
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def authorized(self):
        import base64
        if self.headers.get('Authorization')=='Basic '+base64.b64encode(b'test:test-secret').decode():return True
        self.respond(401);return False
    def read(self):return self.rfile.read(int(self.headers.get('Content-Length','0')))
    def multi(self,href,props):
        return f'<d:response><d:href>{href}</d:href><d:propstat><d:prop>{props}</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
    def xml(self,inner):return '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'+inner+'</d:multistatus>'
    def do_PROPFIND(self):
        self.read()
        if not self.authorized():return
        if self.path=='/':props='<d:current-user-principal><d:href>/principal/</d:href></d:current-user-principal>'
        elif self.path=='/principal/':props='<c:calendar-home-set><d:href>/cal/</d:href></c:calendar-home-set>'
        else:props='<d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>Testkalender</d:displayname><c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set><d:getetag>"v1"</d:getetag>'
        self.respond(207,self.xml(self.multi('/cal/work/' if self.path=='/cal/' else self.path,props)))
    def do_REPORT(self):
        self.read()
        if not self.authorized():return
        props='<d:getetag>"v1"</d:getetag><c:calendar-data>'+escape(self.server.calendar)+'</c:calendar-data>'
        self.respond(207,self.xml(self.multi('/cal/work/event.ics',props)))
    def do_GET(self):self.respond(200,self.server.calendar,'text/calendar')
    def do_PUT(self):
        data=self.read()
        if not self.authorized():return
        self.server.writes.append((self.path,dict(self.headers),data))
        self.respond(412 if self.server.conflict else 204)


class InboxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.cert=cls.root/'cert.pem';key=cls.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-keyout',str(key),'-out',str(cls.cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);cls.context.load_cert_chain(cls.cert,key)
        cls.fingerprint=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cls.cert.read_text())).hexdigest()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def server(self,smtp=False,http=False,starttls=False):
        server=ThreadingHTTPServer(('127.0.0.1',0),CalendarHandler) if http else MailServer(('127.0.0.1',0),MailHandler)
        server.context=self.context;server.smtp=smtp;server.starttls=starttls;server.logins=0;server.deliveries=[];server.drop=False;server.oversize=False;server.conflict=False;server.writes=[]
        if http:server.socket=self.context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        return server

    def test_tls_mail_cache_attachments_drafts_and_uncertain_delivery(self):
        imap=self.server(starttls=True);smtp=self.server(smtp=True,starttls=True)
        message=EmailMessage();message['Subject']='Prüfung';message['From']='Sender <sender@example.invalid>';message['To']='me@example.invalid';message['Message-ID']='<thread@example.invalid>';message['Date']='Sat, 03 Oct 2026 12:00:00 +0200'
        message.set_content('Nur lokaler Test');message.add_attachment(b'file-data',maintype='application',subtype='octet-stream',filename='../../escape.txt');imap.raw=message.as_bytes()
        with tempfile.TemporaryDirectory() as tmp,patch('inbox_data.secret',return_value='test-secret'):
            library=inbox.store(tmp);key=library.create('Test',kind='bridge',host='127.0.0.1',port=imap.server_address[1],tls='starttls',smtp_host='127.0.0.1',smtp_port=smtp.server_address[1],smtp_tls='starttls',username='bridge-user',address='me@example.invalid',fingerprint=self.fingerprint)
            account=library.get(key);result=inbox.sync_mail(library,account,Job());self.assertIn('1 Nachrichten',result);self.assertEqual(inbox.folders(account),['INBOX'])
            with library.connect() as db:record=dict(db.execute('SELECT * FROM messages').fetchone())
            self.assertIn('Nur lokaler Test',record['body']);self.assertEqual(record['unread'],0)
            destination=Path(tmp)/'attachment.txt';inbox.save_attachment(record['raw'],0,destination);self.assertEqual(destination.read_bytes(),b'file-data')
            with self.assertRaises(FileExistsError):inbox.save_attachment(record['raw'],0,destination)
            before=imap.logins
            with self.assertRaises(ValueError):inbox.connect_mail(dict(account,fingerprint='0'*64))
            self.assertEqual(before,imap.logins)
            # Cache survives a failed refresh rather than silently disappearing.
            with library.connect() as db:db.execute("UPDATE messages SET uid='old'")
            imap.oversize=True
            with self.assertRaises(ValueError):inbox.sync_mail(library,account,Job())
            with library.connect() as db:self.assertEqual(db.execute('SELECT uid FROM messages').fetchone()[0],'old')
            draft=inbox.save_draft(library,key,dict(to='recipient@example.invalid',subject='Draft',body='Test'))
            self.assertEqual(smtp.deliveries,[]);inbox.send_draft(library,draft,Job());self.assertEqual(len(smtp.deliveries),1)
            with self.assertRaises(ValueError):inbox.send_draft(library,draft,Job())
            smtp.drop=True;other=inbox.save_draft(library,key,dict(to='recipient@example.invalid',subject='Connection lost',body='Test'))
            with self.assertRaises(Exception):inbox.send_draft(library,other,Job())
            with library.connect() as db:self.assertEqual(db.execute('SELECT status FROM drafts WHERE id=?',(other,)).fetchone()[0],'uncertain')
            with self.assertRaises(ValueError):inbox.send_draft(library,other,Job())
            direct=self.server();direct.raw=imap.raw
            external=dict(account,kind='imap',host='localhost',port=direct.server_address[1],tls='ssl',ca_file=str(self.cert))
            self.assertIn('1 Nachrichten',inbox.sync_mail(library,external,Job()))

    def test_untrusted_html_and_account_validation(self):
        self.assertEqual(inbox.folder_title('Entw&APw-rfe &- Test'),'Entwürfe & Test')
        message=EmailMessage();message.set_content('<script>secret-script</script><p>Readable</p><img src="https://example.invalid/track">',subtype='html')
        text=inbox.text_message(message.as_bytes())['body'];self.assertIn('Readable',text);self.assertNotIn('secret-script',text);self.assertNotIn('track',text)
        for url in ['http://example.invalid/','https://name:secret@example.invalid/','file:///etc/passwd']:
            with self.assertRaises(ValueError):inbox.secure_url(url)

    @unittest.skipUnless(importlib.util.find_spec('caldav'),'Run with Inbox calendar environment for CalDAV integration')
    def test_caldav_tls_discovery_sync_preserves_alarm_and_conflicts(self):
        server=self.server(http=True);now=datetime.now(timezone.utc).replace(microsecond=0)
        start=now.strftime('%Y%m%dT%H%M%SZ');end=(now+timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')
        server.calendar=f'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:test-event\r\nDTSTART:{start}\r\nDTEND:{end}\r\nSUMMARY:Test\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nDESCRIPTION:Reminder\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        account=dict(id='a'*32,kind='caldav',url=f'https://localhost:{server.server_port}/',username='test',ca_file=str(self.cert))
        with patch('inbox_data.secret',return_value='test-secret'):
            calendars=inbox.calendar_operation(account,'calendars',{});self.assertEqual(calendars[0]['name'],'Testkalender');account['calendar']=calendars[0]['url']
            events=inbox.calendar_operation(account,'sync',{});self.assertEqual(events[0]['title'],'Test');self.assertFalse(events[0]['recurring'])
            event=dict(events[0],title='Edited');inbox.calendar_operation(account,'save',event)
            self.assertIn(b'BEGIN:VALARM',server.writes[-1][2]);self.assertIn(b'SUMMARY:Edited',server.writes[-1][2]);self.assertEqual(server.writes[-1][1].get('If-Match'),'"v1"')
            server.conflict=True
            with self.assertRaisesRegex(ValueError,'inzwischen'):inbox.calendar_operation(account,'save',event)
            with self.assertRaises(ValueError):inbox.calendar_operation(account,'save',dict(event,url='https://example.invalid/event.ics'))
            with self.assertRaises(ValueError):inbox.calendar_operation(account,'save',dict(event,recurring=True))
            recurring=server.calendar.replace('SUMMARY:Test','RRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:Test')
            self.assertEqual(len(inbox.parse_calendar(recurring,expand=True)),3);self.assertTrue(inbox.parse_calendar(recurring,expand=True)[0]['recurring'])
        context=ssl.create_default_context(cafile=str(self.cert))
        with patch('inbox_data.secret',return_value=account['url']+'feed.ics'),patch('ssl.create_default_context',return_value=context):
            subscription=dict(account,kind='ics')
            self.assertEqual(inbox.calendar_operation(subscription,'sync',{})[0]['title'],'Test')
            with self.assertRaises(ValueError):inbox.calendar_operation(subscription,'save',{})


if __name__=='__main__':unittest.main()
