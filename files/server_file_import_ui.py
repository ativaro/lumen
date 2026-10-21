"""Inactive native coordinator; no Host callback, launcher or ACTIONS registration.

Series B must supply a lease: window, immutable Binding, permissions_revision,
thread-safe check() (None/True success, otherwise denied; Host/profile/session/connection generation), and GUI-only
accept_import(reference, resolved). Missing leases fail closed; no Web inputs.
"""
from uuid import UUID
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget
import drive_references as drive
import server_file_import as imports
from server_app_session import Binding, APPS
from interop_data import Registry
from interop_sources import from_paths
from interop_dialogs import run_job
from interop_ui import review, root_for
from lumen_i18n import tr


def _current(context,identity):
    checked=context.check()
    if checked is not None and checked is not True:
        raise ValueError(tr('Der native App-Kontext ist nicht mehr gültig.'))
    window,binding,revision=identity
    if (context.window is not window or (context.binding,context.permissions_revision)!=(binding,revision)):
        raise ValueError(tr('Die bestätigte App-Bindung wurde geändert.'))


class _Job:
    def __init__(self, job, context, identity):
        self.job=job;self.context=context;self.identity=identity
        _,self.binding,self.revision=identity

    def check(self):
        self.job.check();_current(self.context,self.identity)

    def profile(self):
        self.check();config=drive.lumen_connect.read_config()
        me=drive.lumen_connect.request(config,'/bridge/me')
        if (config.get('server')!=self.binding.origin or config.get('device_id')!=self.binding.device
                or me.get('id')!=self.binding.account or me.get('device_id')!=self.binding.device
                or type(me.get('permissions_revision')) is not int or me['permissions_revision']!=self.revision
                or not isinstance(me.get('capabilities'),list)
                or not {'drive',APPS[self.binding.app][1]}<=set(me['capabilities'])
                or drive.sync.scope(drive.lumen_connect.read_config())!=drive.sync.scope(config)):
            raise ValueError(tr('Aktuelles Konto, Gerät oder Datenfreigaben sind nicht bestätigt.'))
        self.check();return config


def _folders(job):
    cache=drive.sync.inventory(job.profile());job.profile()
    paths=drive.sync.paths(cache,None)
    result=[]
    for row in cache['folders'].values():
        if (row.get('trashed') is not False or row.get('can_write') is not True
                or type(row.get('revision')) is not int or row['revision']<1):continue
        ref=drive.validate(dict(app='files',kind='drive_folder',id=row['id'],title=row['name'],
            locator=dict(server=job.binding.origin,account=job.binding.account)))
        if paths.get(ref['id']):result.append(dict(reference=ref,title=paths[ref['id']]))
    if not result:raise ValueError(tr('Zuerst einen beschreibbaren Ordner in Lumen Drive anlegen.'))
    return sorted(result,key=lambda row:(row['title'].casefold(),row['reference']['id']))


def _filtered(ref,resolved,binding):
    ref=drive.validate(ref)
    if (ref['kind']!='drive_file' or ref['locator']!=dict(server=binding.origin,account=binding.account)
            or str(UUID(resolved['id']))!=resolved['id']
            or any(type(resolved.get(key)) is not int or resolved[key]<1 for key in ('version','revision'))):
        raise ValueError(tr('Der Drive-Ergebnisverweis passt nicht zu diesem App-Fenster.'))
    return dict(reference=ref,resolved={key:resolved[key] for key in ('id','version','revision')})


def _open_result(request,registry,job):
    job.profile();ref=drive.validate(registry.resolve(request['result']))
    _,rows=drive.resolve([ref],job);row=rows[0]
    if ref['kind']!='drive_file' or row['family']!=ref['id']:
        raise ValueError(tr('Der Drive-Ergebnisverweis ist nicht mehr verfügbar.'))
    job.profile()
    return _filtered(dict(ref,title=row['name']),row,job.binding)


def _confirm(window,request,binding):
    plan=request['choice']['drive_import']
    dialog=QMessageBox(window);dialog.setWindowTitle(tr('Lumen Drive · Übernahme prüfen'))
    dialog.setTextFormat(Qt.PlainText)
    dialog.setText(tr('Bestätigte Kopie: {0}\nZiel: {1}\nServer: {2}\nKonto: {3}\n\nMit derselben Anfrage prüfen und gegebenenfalls fortsetzen?',
        plan['name'],plan['destination']['title'],binding.origin,binding.account))
    dialog.setStandardButtons(QMessageBox.Yes|QMessageBox.Cancel);dialog.setDefaultButton(QMessageBox.Cancel)
    return dialog.exec()==QMessageBox.Yes


def start_import(window,context,token=None,*,root=None):
    """Only an explicit native caller with a current Host lease may enter."""
    if (not isinstance(window,QWidget) or context is None or getattr(context,'window',None) is not window
            or not isinstance(getattr(context,'binding',None),Binding)
            or type(getattr(context,'permissions_revision',None)) is not int or context.permissions_revision<0
            or not callable(getattr(context,'check',None)) or not callable(getattr(context,'accept_import',None))):
        raise ValueError(tr('Ein aktueller nativer App-Kontext ist erforderlich.'))
    if getattr(window,'_lumen_file_import_running',False):
        raise ValueError(tr('In diesem Fenster wird bereits eine Dateiübernahme geprüft.'))
    binding=context.binding;identity=(window,binding,context.permissions_revision);_current(context,identity)
    window._lumen_file_import_running=True
    try:
        root=root_for(window) if root is None else root
        registry=Registry(root)
        def work(title,function):
            return run_job(window,title,lambda job:function(_Job(job,context,identity)))
        if token is not None:
            request=registry.request(token)
            if (request['target']!='files' or request['action']!=imports.ACTION
                    or request['state'] not in ('pending','done')):
                raise ValueError(tr('Diese Dateiübernahme ist nicht zur Prüfung bereit.'))
            if request['state']=='done':
                result=work(tr('Lumen Drive · Ergebnis wird geprüft …'),lambda job:_open_result(request,registry,job))
                if result is None:return None
                _current(context,identity);context.accept_import(result['reference'],result['resolved']);return result
        folders=work(tr('Lumen Drive · Zielordner werden geprüft …'),_folders)
        if folders is None:return None
        _current(context,identity)
        if token is None:
            path,_=QFileDialog.getOpenFileName(window,tr('Lumen Drive · Lokale Datei auswählen'))
            if not path:return None
            _current(context,identity);payload=from_paths([path])
            if payload['items'][0]['directory']:raise ValueError(tr('Genau eine reguläre lokale Datei auswählen.'))
            payload['source_url']=registry.register(payload['source'])
            token=registry.enqueue('files',imports.ACTION,payload)
        request=registry.request(token)
        if request['choice'].get('drive_import'):
            if not _confirm(window,request,binding):return None
            choice={key:request['choice'][key] for key in ('id','title','mode','due','token')}
            destination=request['choice']['drive_import']['destination']
        else:
            spec=dict(label='Lumen Drive · Datei übernehmen',title_label='Dateiname',save_label='Datei übernehmen',
                heading='Datei in Drive speichern',modes=['copy'],requires_choice=True,
                description=tr('Eine eigenständige Kopie im gewählten Ordner speichern.\nServer: {0}\nKonto: {1}',binding.origin,binding.account))
            choice=review(window,request,spec=spec,rows=[dict(id=row['reference']['id'],title=row['title']) for row in folders])
            if choice is None:return None
            destination=next(row['reference'] for row in folders if row['reference']['id']==choice['id'])
        _current(context,identity)
        def transfer(job):
            job.profile();imports.prepare(token,choice,destination,job,root=root)
            job.profile();result=imports.apply(token,job,root=root);job.profile()
            return _filtered(result['reference'],result['resolved'],job.binding)
        result=work(tr('Lumen Drive · Datei wird übernommen …'),transfer)
        if result is None:return None
        _current(context,identity);context.accept_import(result['reference'],result['resolved']);return result
    finally:window._lumen_file_import_running=False
