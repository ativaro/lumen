"""Project-scoped reversible removal using the existing archived flags."""
import json,time
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction,QKeySequence,QShortcut
from PySide6.QtWidgets import QMenu,QMessageBox,QSizePolicy
from lumen_i18n import tr
from studio_design import icon
from tools_ui import button


def state(project,item=None,parent=None):
    value=item or project
    blocked=project.get('server_role')=='reader' or bool(item and (project.get('_archived') or parent and parent['archived']))
    return dict(project=project['id'],scope=item['id'] if item else '',title=value['title'],
        revision=str(item['updated']) if item else project['_revision'],project_revision=project['_revision'],
        archived=bool(value.get('archived',value.get('_archived')) or item and parent and parent['archived']),blocked=blocked)


class ProjectTrash:
    def __init__(self,window):self.window=window

    def projects(self,archived=False):
        with self.window.library.connect() as db:
            return [self.record(r) for r in db.execute('SELECT * FROM records WHERE archived=? ORDER BY updated DESC',(int(archived),))]

    @staticmethod
    def record(row):
        return dict(json.loads(row['data']),id=row['id'],title=row['title'],updated=row['updated'],_revision=str(row['updated']),_archived=bool(row['archived']))

    def project(self,key):
        with self.window.library.connect() as db:row=db.execute('SELECT * FROM records WHERE id=?',(key,)).fetchone()
        if row is None:raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
        return self.record(row)

    def action(self,owner,expected):
        action=QAction(icon('edit-undo' if expected['archived'] else 'user-trash'),tr('Wiederherstellen' if expected['archived'] else 'In den Papierkorb'),owner)
        action.setEnabled(not expected['blocked']);action.setData(expected)
        if expected['blocked']:action.setToolTip(tr('Nur lesen oder übergeordneten Eintrag zuerst wiederherstellen.'))
        action.triggered.connect(lambda:self.window.safe(self.perform,expected))
        return action

    def menu_button(self,owner,menu,title):
        more=button(tr('Mehr'),lambda:None);more.setAccessibleName(tr(title));more.setToolTip(tr(title));more.setMenu(menu);more.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        return more

    def bind(self,control,menu,callback):
        control.setContextMenuPolicy(Qt.CustomContextMenu)
        control.customContextMenuRequested.connect(lambda pos:menu.exec(control.mapToGlobal(pos if pos.x()>=0 else control.rect().bottomLeft())))
        shortcut=QShortcut(QKeySequence(Qt.Key_Delete),control);shortcut.setContext(Qt.WidgetShortcut);shortcut.activated.connect(callback)

    def card(self,control,project):
        expected=state(project);menu=QMenu(control);action=self.action(menu,expected);menu.addAction(action)
        self.bind(control,menu,action.trigger)
        return self.menu_button(control,menu,'Projektaktionen')

    def current(self):
        w=self.window
        expected=w.editor.trash_state if w.scope else w.journal.project_archive.data()
        return self.perform(expected)

    def ready(self):
        if self.window.editor.dirty() or self.window.editor.draft_kind:
            raise ValueError(tr('Speichere oder verwerfe zuerst deine Änderungen. Die Papierkorb-Aktion speichert keinen Entwurf.'))
        return self.window.editor.allow_leave()

    def confirm(self,text,action):
        dialog=QMessageBox(self.window);dialog.setWindowTitle(tr('Lumen Projekte'));dialog.setIcon(QMessageBox.Question);dialog.setTextFormat(Qt.PlainText);dialog.setText(text)
        apply=dialog.addButton(action,QMessageBox.AcceptRole);cancel=dialog.addButton(tr('Abbrechen'),QMessageBox.RejectRole)
        dialog.setDefaultButton(cancel);dialog.setEscapeButton(cancel);dialog.exec()
        accepted=dialog.clickedButton() is apply;dialog.deleteLater();return accepted

    def locked(self,db,expected):
        from projects_data import Projects
        root=db.execute('SELECT * FROM records WHERE id=?',(expected['project'],)).fetchone()
        if root is None:raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
        Projects.writable(db,expected['project'])
        if json.loads(root['data']).get('server_role')=='reader':raise ValueError(tr('Dieses Serverprojekt ist nur lesbar.'))
        row=db.execute('SELECT * FROM project_items WHERE id=? AND project=?',(expected['scope'],expected['project'])).fetchone() if expected['scope'] else root
        if row is None:raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
        if str(root['updated'])!=expected['project_revision'] or str(row['updated'])!=expected['revision']:
            raise ValueError(tr('Der Eintrag wurde inzwischen geändert. Bitte erneut öffnen.'))
        if expected['scope']:
            parent=db.execute('SELECT archived FROM project_items WHERE id=?',(row['parent'],)).fetchone() if row['parent'] else None
            if root['archived'] or parent and parent['archived']:raise ValueError(tr('Zuerst den übergeordneten Eintrag wiederherstellen.'))
        return root,row

    def check_native(self,db,expected):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='project_flows'").fetchone():return
        query='SELECT flow FROM project_flows WHERE project=?';args=[expected['project']]
        if expected['scope']:query+=' AND scope=?';args.append(expected['scope'])
        linked=[row['flow'] for row in db.execute(query,args)]
        if not linked:return
        placeholders=','.join('?' for _ in linked)
        with self.window.project_store.connect() as native:
            native.execute('PRAGMA query_only=ON');native.execute('BEGIN')
            enabled=native.execute('SELECT name FROM workflows WHERE enabled!=0 AND id IN ('+placeholders+') LIMIT 1',linked).fetchone()
            if enabled:raise ValueError(tr('Der zugeordnete Ablauf „{0}“ ist aktiviert. Pausiere ihn zuerst in Lumen Automation.',enabled['name']))
            active=native.execute("SELECT coalesce(w.name,t.title) AS flow_title,t.title FROM tasks t JOIN events e ON e.task=t.id AND e.kind='workflow' LEFT JOIN workflows w ON w.id=e.detail WHERE e.detail IN ("+placeholders+") AND t.status IN ('queued','running','needs_input') LIMIT 1",linked).fetchone()
            if active:raise ValueError(tr('Der zugeordnete Ablauf „{0}“ hat einen aktiven Auftrag („{1}“). Pausiere oder beende diesen Auftrag zuerst in Lumen Automation.',active['flow_title'],active['title']))

    def perform(self,expected):
        w=self.window
        if not expected or not self.ready():return
        if expected['blocked']:raise ValueError(tr('Nur lesen oder übergeordneten Eintrag zuerst wiederherstellen.'))
        if not expected['archived']:
            text=tr('„{0}“ in den Papierkorb legen? Du kannst den Eintrag später wiederherstellen. Originaldateien bleiben erhalten.',expected['title'])
            if not self.confirm(text,tr('In den Papierkorb')):return
        with w.library.connect() as db:
            db.execute('BEGIN IMMEDIATE');root,target=self.locked(db,expected)
            if not target['archived']:self.check_native(db,expected)
            condition='project=?';args=[expected['project']]
            if expected['scope']:
                condition+=' AND (id=? OR parent=?)' if target['kind']=='initiative' else ' AND id=?'
                args.extend([target['id'],target['id']] if target['kind']=='initiative' else [target['id']])
            children=db.execute('SELECT * FROM project_items WHERE '+condition,args).fetchall()
            busy=lambda value:value in ('running','waiting','queued') or str(value).startswith('waiting_')
            if any(busy(json.loads(row['data']).get('status')) for row in children):raise ValueError(tr('Zuerst die laufenden oder wartenden Projektaufgaben beenden.'))
            ids={row['id'] for row in children}
            runs=db.execute("SELECT r.task,r.status FROM project_runs r JOIN project_items i ON i.id=r.task WHERE i.project=? AND (r.status IN ('running','waiting','queued') OR r.status LIKE 'waiting_%')",(expected['project'],))
            if any(r['task'] in ids and busy(r['status']) for r in runs):raise ValueError(tr('Zuerst die laufenden oder wartenden Projektaufgaben beenden.'))
            now=time.time();archived=not bool(target['archived'])
            for row in children:
                data=json.loads(row['data']);changed=bool(data.get('enabled'))
                if changed:data['enabled']=False
                if changed or row['id']==expected['scope']:
                    db.execute('UPDATE project_items SET data=?,archived=?,updated=? WHERE id=?',(json.dumps(data),int(archived) if row['id']==expected['scope'] else row['archived'],now,row['id']))
            if not expected['scope']:db.execute('UPDATE records SET archived=?,updated=? WHERE id=?',(int(archived),now,root['id']))
        if w.current==expected['project'] and w.home.pages.currentWidget() is w.home.detail:
            w.navigate(expected['project']);w.editor.hide()
        self.refresh()

    def unlink(self,expected,field,value):
        w=self.window
        if field not in ('resources','references','server_attachments','flow') or expected['scope']:raise ValueError(tr('Ungültige Projektzuordnung.'))
        if not self.ready():return
        if not self.confirm(tr('Nur die Zuordnung aus diesem Projekt entfernen? Der ursprüngliche Inhalt bleibt erhalten.'),tr('Zuordnung entfernen')):return
        with w.library.connect() as db:
            db.execute('BEGIN IMMEDIATE');root,_=self.locked(db,expected)
            if root['archived']:raise ValueError(tr('Zuerst den übergeordneten Eintrag wiederherstellen.'))
            data=json.loads(root['data'])
            if field=='flow':
                deleted=db.execute('DELETE FROM project_flows WHERE project=? AND flow=?',(root['id'],value)).rowcount
                if not deleted:raise ValueError(tr('Die Zuordnung wurde inzwischen geändert.'))
            else:
                rows=data.get(field,[])
                if value not in rows:raise ValueError(tr('Die Zuordnung wurde inzwischen geändert.'))
                data[field]=[r for r in rows if r!=value]
            db.execute('UPDATE records SET data=?,updated=? WHERE id=?',(json.dumps(data),time.time(),root['id']))
        self.refresh()

    def refresh(self):
        w=self.window;w.journal.signature=None;w.home.overview.signature=None
        if w.current and not w.scope and not w.editor.dirty():
            w.loading=True
            try:w.load_fields(w.library.get(w.current))
            finally:w.loading=False
        w.refresh();w.home.refresh()
