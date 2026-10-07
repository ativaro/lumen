"""Lumen Files properties: compact card and expanded overview share one state."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar,
    QPushButton, QTabWidget, QVBoxLayout, QWidget)
from core import size_text, valid_name
from lumen_i18n import tr
from lumen_jobs import Job
import file_properties_data as data


def label(text='', name=''):
    widget = QLabel(text); widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True); widget.setObjectName(name)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


def date(value):
    if value is None: return tr('Nicht verfügbar')
    if isinstance(value, (int, float)): return datetime.fromtimestamp(value).strftime('%d.%m.%Y · %H:%M')
    return str(value)


class Properties(QDialog):
    def __init__(self, window, paths):
        super().__init__(window)
        self.window = window; self.paths = list(paths); self.fact = None
        self.job = None; self.task_kind = ''; self.expanded = False; self.warning = ''; self.totals = None
        self.setWindowTitle(tr('Lumen Files · Eigenschaften'))
        self.resize(540, 620)
        self.setMinimumSize(510, 550)
        from drive_browser import is_drive
        self.drive = all(is_drive(p) for p in paths)
        self.remote = not self.drive and any(window.network.remote(p) for p in paths)
        self.drive_rows = [(kind, dict(row)) for kind,row in (window.drive.entries[p] for p in paths)] if self.drive else []
        self.drive_config = dict(window.drive.config or {}) if self.drive else None
        self.drive_role = next((s['role'] for s in window.drive.spaces if s['id'] == window.drive.space), 'reader') if self.drive else None
        outer = QVBoxLayout(self); outer.setContentsMargins(22, 22, 22, 16); outer.setSpacing(16)
        heading = QHBoxLayout(); heading.setSpacing(16)
        symbol = label(); self.symbol=symbol
        heading.addWidget(symbol)
        names = QVBoxLayout(); self.title = label(tr('Eigenschaften'), 'propertiesTitle'); self.location = label('', 'muted')
        names.addWidget(self.title); names.addWidget(self.location); heading.addLayout(names, 1); outer.addLayout(heading)
        self.tabs = QTabWidget(); outer.addWidget(self.tabs, 1)
        general = QWidget(); self.general_layout = QHBoxLayout(general); self.general_layout.setContentsMargins(0,16,0,0); self.general_layout.setSpacing(18)
        left = QWidget(); main = QVBoxLayout(left); main.setContentsMargins(0,0,0,0)
        main.addWidget(label(tr('Name'), 'muted')); self.name = QLineEdit(); self.name.setAccessibleName(tr('Name')); main.addWidget(self.name)
        form = QFormLayout(); form.setVerticalSpacing(13); self.summary = {}
        for key, title in [('type',tr('Typ')),('place',tr('Speicherort')),('size',tr('Größe')),('modified',tr('Geändert')),('created',tr('Erstellt'))]:
            field = label(); self.summary[key] = field
            if key=='place':
                wrap=QWidget(); line=QHBoxLayout(wrap); line.setContentsMargins(0,0,0,0); line.addWidget(field,1)
                copy=QPushButton(QIcon.fromTheme('edit-copy'),''); copy.setAccessibleName(tr('Pfad kopieren')); copy.setToolTip(tr('Pfad kopieren')); copy.clicked.connect(lambda:QApplication.clipboard().setText('\n'.join(self.paths))); line.addWidget(copy)
                form.addRow(label(title,'muted'),wrap)
            elif key=='size':
                wrap=QWidget(); line=QHBoxLayout(wrap); line.setContentsMargins(0,0,0,0); line.addWidget(field,1)
                self.calculate=QPushButton(tr('Berechnen')); self.calculate.setObjectName('quiet'); self.calculate.clicked.connect(self.count); line.addWidget(self.calculate); form.addRow(label(title,'muted'),wrap)
            else: form.addRow(label(title,'muted'),field)
        main.addLayout(form)
        separator=QFrame();separator.setFrameShape(QFrame.HLine);main.addWidget(separator)
        self.access_link=QPushButton(tr('Ansehen ›')); self.access_link.setObjectName('quiet'); self.access_link.clicked.connect(lambda:self.tabs.setCurrentIndex(1))
        access_row=QHBoxLayout();access_row.addWidget(label(tr('Zugriff')));access_row.addStretch();access_row.addWidget(self.access_link);main.addLayout(access_row)
        self.backup = label('', 'muted'); main.addWidget(self.backup)
        self.vault_button=QPushButton(tr('Versionen ansehen ›'));self.vault_button.setObjectName('quiet');self.vault_button.clicked.connect(self.vault)
        vault_row=QHBoxLayout();vault_row.addWidget(label('Lumen Vault'));vault_row.addStretch();vault_row.addWidget(self.vault_button);main.addLayout(vault_row)
        main.addStretch(); self.general_layout.addWidget(left,1)
        self.overview = QFrame(); self.overview.setObjectName('propertiesOverview'); right=QVBoxLayout(self.overview)
        right.addWidget(label(tr('Speicher & Inhalt'),'propertiesSection')); self.distribution=QVBoxLayout(); right.addLayout(self.distribution)
        self.counts=label(tr('Die Aufteilung erscheint nach der Größenberechnung.'),'muted'); right.addWidget(self.counts)
        right.addSpacing(16); right.addWidget(label(tr('Sicherungen & Verlauf'),'propertiesSection')); self.backup_detail=label('', 'muted'); right.addWidget(self.backup_detail)
        right.addStretch(); discuss=QPushButton(tr('Mit Lumen besprechen')); discuss.clicked.connect(self.discuss); discuss.setVisible(not self.drive); right.addWidget(discuss)
        self.general_layout.addWidget(self.overview,1,Qt.AlignTop); self.overview.hide()
        self.tabs.addTab(general,tr('Allgemein'))
        access=QWidget(); access_layout=QVBoxLayout(access); access_layout.setContentsMargins(0,16,0,0)
        self.owners=label(); access_layout.addWidget(self.owners); self.access_notice=label('', 'muted'); access_layout.addWidget(self.access_notice)
        grid=QGridLayout(); grid.setVerticalSpacing(18); self.bits=[]
        for col,title in enumerate([tr('Lesen'),tr('Schreiben'),tr('Ausführen / Betreten')],1):grid.addWidget(label(title,'muted'),0,col)
        for row,title in enumerate([tr('Eigentümer'),tr('Gruppe'),tr('Andere')],1):
            grid.addWidget(label(title),row,0)
            for col,bit in enumerate([4,2,1],1):
                value=bit << (3*(3-row)); check=QCheckBox(); check.setAccessibleName(title+' · '+[tr('Lesen'),tr('Schreiben'),tr('Ausführen / Betreten')][col-1]); self.bits.append((check,value)); grid.addWidget(check,row,col); check.toggled.connect(self.dirty)
        self.permissions_widget=QWidget();self.permissions_widget.setLayout(grid);access_layout.addWidget(self.permissions_widget)
        access_layout.addWidget(label(tr('Gilt nur für diesen Eintrag. Unterordner und Dateien werden nicht verändert.'),'muted'))
        self.acl=QPlainTextEdit(); self.acl.setReadOnly(True); self.acl.setAccessibleName(tr('ACL und Sonderrechte')); self.acl.setMaximumHeight(160); access_layout.addWidget(self.acl); access_layout.addStretch(); self.tabs.addTab(access,tr('Zugriff'))
        details=QWidget(); details_layout=QVBoxLayout(details); details_layout.setContentsMargins(0,16,0,0)
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); self.details.setAccessibleName(tr('Technische Dateieigenschaften')); details_layout.addWidget(self.details)
        self.hash_button=QPushButton(tr('SHA-256 berechnen')); self.hash_button.clicked.connect(self.hash); details_layout.addWidget(self.hash_button)
        details_layout.addWidget(label(tr('SHA-256 vom Server') if self.drive else 'SHA-256','muted'))
        self.hash_value=QLineEdit(); self.hash_value.setReadOnly(True); self.hash_value.setPlaceholderText(tr('Noch nicht berechnet')); self.hash_value.setAccessibleName(tr('SHA-256')); details_layout.addWidget(self.hash_value)
        self.tabs.addTab(details,tr('Details'))
        connections=QWidget(); links=QVBoxLayout(connections); links.addWidget(label(tr('Verwendung in anderen Lumen-Apps und vorhandene Verknüpfungen prüfen.')))
        self.related_button=QPushButton(tr('Verwendet in …')); self.related_button.clicked.connect(self.related); links.addWidget(self.related_button); links.addStretch(); self.tabs.addTab(connections,tr('Verknüpfungen'))
        versions=QWidget(); history=QVBoxLayout(versions); history.addWidget(label(tr('Vorhandene Versionen werden über die bestehende lokale Dateihistorie oder Lumen Vault geöffnet.')))
        self.local_versions=QPushButton(tr('Lokale Dateiversionen …')); self.local_versions.clicked.connect(lambda:window.show_versions(self.paths[0])); history.addWidget(self.local_versions)
        self.more_vault=QPushButton(tr('Versionen in Lumen Vault …')); self.more_vault.clicked.connect(self.vault); history.addWidget(self.more_vault); history.addStretch(); self.tabs.addTab(versions,tr('Versionen'))
        self.tabs.setTabVisible(3,False); self.tabs.setTabVisible(4,False)
        self.status=label(tr('Dateieigenschaften werden geladen …'),'muted'); status_row=QHBoxLayout();status_row.addWidget(self.status,1)
        self.cancel_button=QPushButton(tr('Abbrechen'));self.cancel_button.clicked.connect(self.cancel_read);self.cancel_button.hide();status_row.addWidget(self.cancel_button);outer.addLayout(status_row)
        footer=QHBoxLayout(); self.expand=QPushButton(tr('Mehr Details')); self.expand.clicked.connect(self.toggle); footer.addWidget(self.expand); footer.addStretch()
        self.close_button=QPushButton(tr('Schließen')); self.close_button.clicked.connect(self.reject); footer.addWidget(self.close_button)
        self.apply=QPushButton(tr('Übernehmen')); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); self.apply.setEnabled(False); footer.addWidget(self.apply); outer.addLayout(footer)
        self.name.textChanged.connect(self.dirty)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)
        self.setStyleSheet('''QLabel#propertiesTitle { font-size: 25px; font-weight: 600; }
            QLabel#propertiesSection { font-size: 15px; font-weight: 600; }
            QFrame#propertiesOverview { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
            QFrame#propertiesOverview QLabel { border: none; background: transparent; }
            QTabWidget::pane { border: none; } QTabBar::tab { min-width: 65px; padding: 10px 13px; background: transparent; border-radius: 0; border-bottom: 2px solid transparent; }
            QTabBar::tab:selected { color: palette(link); border-bottom-color: palette(link); }
            QPushButton#quiet { background: transparent; border-color: transparent; color: palette(link); padding: 6px 9px; }
            QPushButton#quiet:hover { background: palette(midlight); }
            QFrame[frameShape="4"] { color: palette(mid); }
            QLineEdit { padding: 9px 12px; }
            QProgressBar { min-height: 5px; max-height: 5px; border: none; }''')
        self.set_busy(True); QTimer.singleShot(0,self.reload)

    def start(self, kind, function):
        if self.job is not None: return
        self.task_kind=kind; self.set_busy(True)
        self.status.setText(tr('Änderungen werden gespeichert …') if kind in ('save','drive_save') else tr('Dateieigenschaften werden geladen …') if kind=='inspect' else tr('Berechnung läuft …'))
        self.cancel_button.setVisible(kind not in ('save','drive_save'))
        app=QApplication.instance()
        if not hasattr(app,'property_jobs'):app.property_jobs=[]
        job=Job(function,app); self.job=job; app.property_jobs.append(job)
        job.result.connect(self.received); job.failed.connect(self.failed); job.progress.connect(self.status.setText)
        job.finished.connect(self.job_finished)
        def dispose():
            app.property_jobs.remove(job); job.deleteLater()
        job.finished.connect(dispose); job.start()

    def reload(self):
        if self.drive:
            self.received_drive(); self.set_busy(False); return
        paths=list(self.paths); remote=bool(self.remote)
        self.start('inspect',lambda job:data.inspect(paths,job,remote))

    def set_busy(self, busy):
        for widget in (self.name,self.calculate,self.hash_button,self.expand,self.access_link,self.vault_button,self.more_vault,self.local_versions,self.related_button):widget.setEnabled(not busy and self.fact is not None)
        if not busy and self.fact:
            one=len(self.fact['rows'])==1; row=self.fact['rows'][0]
            self.name.setReadOnly(not one or (not self.drive and Path(row['path']).parent==Path(row['path'])) or (self.drive and (self.drive_role=='reader' or row['kind']=='space')))
            self.calculate.setEnabled(not self.drive)
            self.hash_button.setEnabled(one and not self.drive and row['kind']=='file')
            for button in (self.vault_button,self.more_vault,self.local_versions):button.setEnabled(one and not self.drive)
            self.related_button.setEnabled(not self.drive)
        for check,_ in self.bits:check.setEnabled(not busy and bool(self.fact) and len(self.fact['rows'])==1 and self.fact['rows'][0].get('can_mode',False))
        self.dirty()
        if busy:self.apply.setEnabled(False)

    def received(self, value):
        if self.task_kind=='inspect':self.fact=value; self.populate()
        elif self.task_kind=='count':
            self.totals=value
            self.summary['size'].setText(size_text(value['size'])+' · '+tr('{0} Dateien, {1} Ordner',value['files'],value['folders']))
            self.counts.setText(tr('{0} nicht lesbare Einträge übersprungen.',value['skipped']) if value['skipped'] else tr('Größe berechnet. Verknüpfungsziele nicht verfolgt.'))
            while self.distribution.count():
                item=self.distribution.takeAt(0)
                if item.widget():item.widget().deleteLater()
            for kind,amount in sorted(value['types'].items(),key=lambda pair:-pair[1]):
                names={'image':tr('Bilder'),'video':tr('Videos'),'audio':tr('Audio'),'text':tr('Text'),'application':tr('Dokumente & andere Dateien'),'links':tr('Verknüpfungen')}
                self.distribution.addWidget(label(names.get(kind,tr('Andere'))+' · '+size_text(amount)))
                bar=QProgressBar();bar.setRange(0,1000);bar.setValue(round(amount/max(1,value['size'])*1000));bar.setTextVisible(False);bar.setFixedHeight(5);self.distribution.addWidget(bar)
            self.status.setText(self.counts.text())
        elif self.task_kind=='hash':self.hash_value.setText(value);self.status.setText(tr('SHA-256 berechnet.'))
        elif self.task_kind=='save':
            self.paths=[value['path']];self.warning=value.get('warning','');self.window.refresh()
        elif self.task_kind=='drive_save':
            kind,row=self.drive_rows[0];row.update(value);self.drive_rows=[(kind,row)]
            if kind=='file':
                from urllib.parse import quote
                self.paths=[self.paths[0].rsplit('/',1)[0]+'/'+quote(row['name'],safe='')]
            self.window.refresh()

    def job_finished(self):
        kind=self.task_kind;self.job=None;self.cancel_button.hide();self.set_busy(False)
        if kind in ('save','drive_save'):self.reload()

    def failed(self, message):
        self.status.setText(message);self.warning=message

    def populate(self):
        rows=self.fact['rows'];row=rows[0];one=len(rows)==1
        self.symbol.setPixmap(QIcon.fromTheme('folder' if not one or row['kind'] in ('folder','space') else 'text-x-generic').pixmap(48,48))
        title=row['name'] if one else tr('{0} Einträge ausgewählt',len(rows))
        self.title.setText(self.title.fontMetrics().elidedText(title,Qt.ElideMiddle,420));self.title.setToolTip(title)
        self.location.setText('Lumen Drive' if self.drive else tr('Netzwerk') if self.remote else tr('Auf diesem Gerät'))
        self.name.setText(title)
        kinds={'folder':tr('Ordner'),'file':tr('Datei'),'link':tr('Verknüpfung'),'special':tr('Spezialdatei'),'space':tr('Serverbereich')}
        self.summary['type'].setText(kinds.get(row['kind'],tr('Datei')) if one else tr('Mehrfachauswahl'))
        place=self.paths[0] if self.drive else self.window.network.remote(self.paths[0]) or str(Path(self.paths[0]).parent)
        self.summary['place'].setText(place if one else tr('Mehrere Speicherorte'))
        self.summary['size'].setText(size_text(sum(r.get('size',0) for r in rows)) if all(r['kind'] in ('file','link') for r in rows) else tr('Noch nicht berechnet'))
        self.calculate.setVisible(any(r['kind']=='folder' for r in rows) and not self.drive)
        if self.drive and any(r['kind']!='file' for r in rows):
            self.summary['size'].setText(tr('Vom Server nicht angegeben'))
            self.counts.setText(tr('Speicheraufteilung nur für lokale oder eingehängte Ordner.'))
        self.summary['modified'].setText(date(row.get('modified')) if one else '—');self.summary['created'].setText(date(row.get('created')) if one else '—')
        self.owners.setText(tr('Eigentümer: {0}\nGruppe: {1}',row.get('owner','—'),row.get('group','—')) if one and not self.drive and not self.remote else tr('Zugriff wird vom Server verwaltet.') if self.drive or self.remote else tr('Berechtigungen einzelner Einträge separat bearbeiten.'))
        self.access_notice.setText(tr('Diese Rechte können hier geändert werden.') if one and row.get('can_mode') else tr('Rechte werden hier nur angezeigt: Netzwerk, Verknüpfung, ACL oder fehlende Eigentümerrechte.'))
        self.permissions_widget.setVisible(one and not self.drive and not self.remote)
        for check,bit in self.bits:
            check.blockSignals(True);check.setChecked(one and bool(row.get('mode',0)&bit));check.blockSignals(False)
        self.acl.setPlainText(self.fact.get('acl_text') or tr('Keine zusätzlichen ACL-Angaben verfügbar.'))
        self.acl.setVisible(not self.drive)
        plans=self.fact.get('plans',[])
        self.backup.setText(tr('Sicherungsstatus pro Eintrag prüfen') if not one else tr('Sicherungsplan vorhanden') if plans else tr('Kein Sicherungsplan gefunden') if not self.drive else tr('Sicherungen werden vom Server verwaltet.'))
        lines=[]
        for plan in plans:lines.append(plan['title']+'\n'+tr('Letzter Sicherungslauf: {0}',date(plan.get('last_backup') or None)))
        self.backup_detail.setText('\n\n'.join(lines)+'\n\n'+tr('Planstatus; Sicherungsinhalt noch nicht geprüft.') if lines else self.backup.text())
        if self.fact.get('backup_error'):self.backup.setText(tr('Sicherungsstatus nicht verfügbar.'));self.backup_detail.setText(self.backup.text())
        details=[]
        if one:
            for key,title in [('mime',tr('Dateityp (MIME)')),('target',tr('Verknüpfungsziel')),('allocated',tr('Belegter Speicher')),('links',tr('Hardlinks'))]:
                if key=='allocated' and row['kind']!='file':continue
                if key in row and row[key]!='':details.append(title+': '+(size_text(row[key]) if key=='allocated' else str(row[key])))
            if 'identity' in row:details.append(tr('Gerät / Inode')+': '+str(row['identity']))
            if 'mode' in row:details.append(tr('POSIX-Rechte')+': '+format(row['mode'],'04o'))
            if self.drive:details.extend([tr('Serverrolle')+': '+str(self.drive_role),tr('Revision')+': '+str(row.get('revision','—'))])
            details.extend(str(k)+': '+str(v) for k,v in self.fact.get('metadata',{}).items())
        else:details=[str(r.get('path',r['name'])) for r in rows]
        self.details.setPlainText('\n\n'.join(details));self.hash_value.setText(row.get('sha256','') if one else '')
        if self.totals:
            value=self.totals; self.summary['size'].setText(size_text(value['size'])+' · '+tr('{0} Dateien, {1} Ordner',value['files'],value['folders']))
        self.status.setText(self.warning or tr('Änderungen werden erst mit „Übernehmen“ gespeichert.'))
        self.set_busy(self.job is not None)

    def received_drive(self):
        rows=[]
        for kind,source in self.drive_rows:
            row=dict(source,kind=kind,can_mode=False);row['modified']=source.get('updated_at');row['created']=source.get('created_at');rows.append(row)
        self.fact=dict(rows=rows);self.populate()

    def mode(self):
        if not self.fact:return 0
        return (self.fact['rows'][0].get('mode',0)&~0o777) | sum(bit for check,bit in self.bits if check.isChecked())

    def dirty(self):
        one=self.fact and len(self.fact['rows'])==1
        changed=bool(one and ((not self.name.isReadOnly() and self.name.text()!=self.fact['rows'][0]['name']) or (self.fact['rows'][0].get('can_mode') and self.mode()!=self.fact['rows'][0]['mode'])))
        self.apply.setEnabled(changed and self.job is None)

    def save(self):
        if not self.fact or self.job:return
        try:name=valid_name(self.name.text())
        except ValueError as error:self.status.setText(str(error));return
        self.warning=''
        if self.drive:
            import lumen_connect
            import drive_sync as sync
            if sync.scope(lumen_connect.read_config())!=sync.scope(self.drive_config):self.status.setText(tr('Serververbindung geändert. Drive neu öffnen.'));return
            if not self.window.drive.writable():return
            kind,row=self.drive_rows[0];config=dict(self.drive_config)
            if kind=='space':return
            payload=dict(name=name,revision=row['revision'],trashed=False);key='parent_id' if kind=='folder' else 'folder_id';payload[key]=row[key]
            endpoint=('/folders/' if kind=='folder' else '/files/')+row['id']
            def update(job):
                job.check(); result=sync.request(config,endpoint,payload)
                if not isinstance(result,dict):raise ValueError(tr('Unerwartete Antwort des Servers. Drive erneut öffnen.'))
                return result
            self.start('drive_save',update)
        else:
            if self.window.file_job:self.status.setText(tr('Bitte den laufenden Dateivorgang abwarten.'));return
            row=dict(self.fact['rows'][0]);mode=self.mode();self.start('save',lambda job:data.apply_local(row,name,mode,job))

    def cancel_read(self):
        if self.job and self.task_kind not in ('save','drive_save'):self.job.cancelled.set()

    def count(self):
        paths=list(self.paths);self.start('count',lambda job:data.folder_totals(paths,job))

    def hash(self):
        row=dict(self.fact['rows'][0]);self.start('hash',lambda job:data.checksum(row,job))

    def toggle(self):
        self.expanded=not self.expanded;self.overview.setVisible(self.expanded)
        self.tabs.setTabVisible(3,self.expanded);self.tabs.setTabVisible(4,self.expanded)
        self.tabs.setTabText(0,tr('Übersicht') if self.expanded else tr('Allgemein'))
        self.expand.setText(tr('Kompakte Ansicht') if self.expanded else tr('Mehr Details'))
        self.resize(960 if self.expanded else 540,680 if self.expanded else 620)
        if self.expanded and self.totals is None and not self.drive:self.count()

    def vault(self):
        from interop_vault import show_file_versions
        show_file_versions(self,self.paths[0])

    def related(self):
        from interop_ui import browse,safe_action
        from interop_sources import from_paths
        safe_action(self.window,lambda:browse(self.window,'related',from_paths(self.paths)))

    def discuss(self):
        self.reject();self.window.ask_lumen('open',self.paths)

    def reject(self):
        if self.job and self.task_kind in ('save','drive_save'):return
        if self.job:self.job.cancelled.set()
        super().reject()

    def closeEvent(self,event):
        if self.job and self.task_kind in ('save','drive_save'):event.ignore();return
        if self.job:self.job.cancelled.set()
        super().closeEvent(event)


def show(window, paths):
    if not paths:return
    dialog=Properties(window,paths)
    dialog.exec();dialog.deleteLater()
