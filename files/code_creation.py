"""Kind-specific creation without writing a collection entry before confirmation."""
import json
from pathlib import Path
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QStackedWidget,QWidget,
    QGridLayout,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QFileDialog,QTextBrowser,QMessageBox,QScrollArea)
from lumen_i18n import tr,language
from tools_ui import button
from code_library_contract import definition

IDEAS=json.loads(Path(__file__).with_name('code_creation_ideas.json').read_text())
KINDS={'app':('Kleine App','Eine eigene Oberfläche mit Eingaben, Schaltflächen und Ergebnissen.'),
       'tool':('Werkzeug','Einen Auftrag mit neuen Dateien oder Eingaben immer wieder ausführen.'),
       'automation':('Automation','Einen Auslöser mit deinen Apps, Diensten und Werkzeugen verbinden.'),
       'code':('Code im Projekt','Software entwickeln, einen Fehler beheben oder eine Änderung prüfen.')}


class CreationDialog(QDialog):
    def __init__(self,parent=None,projects=None,tools=None):
        super().__init__(parent);self.setWindowTitle(tr('Lumen · Neu erstellen'));self.resize(1120,800)
        self.goal_engine=None;self.goal_directory=None;self.recommendation=None;self.goal_submitted='';self.closed=False
        self.selected_idea=None;self.value=None;self.kind='app';self.drafts={};self.idea_buttons={};self.loading=False;self.flow_dirty=False
        from code_design import shell,navigation,card
        from tools_ui import label
        main,nav,self.footer=shell(self)
        self.nav=navigation(nav,self.reject,self.select_kind)
        root=QVBoxLayout(main);root.setContentsMargins(30,20,30,24);root.setSpacing(18)
        topline=QHBoxLayout();self.back_link=button(tr('‹ Zur Sammlung'),self.reject);self.back_link.setObjectName('codeLink');topline.addWidget(self.back_link);topline.addStretch()
        close=button(tr('Schließen'),self.reject);close.setObjectName('codeLink');topline.addWidget(close);root.addLayout(topline)
        self.pages=QStackedWidget();root.addWidget(self.pages,1)
        choose=QWidget();layout=QVBoxLayout(choose);layout.setContentsMargins(0,0,0,0);layout.setSpacing(14)
        layout.addWidget(label(tr('Was möchtest du erstellen?'),'codeTitle'))
        layout.addWidget(label(tr('Wähle, wie dein neuer Helfer funktionieren soll.'),'codeSubtitle'));layout.addSpacing(8)
        grid=QGridLayout();grid.setSpacing(13);layout.addLayout(grid)
        examples={'app':'Zum Beispiel: Angebote vergleichen','tool':'Zum Beispiel: Dokumente auf fehlende Angaben prüfen','automation':'Zum Beispiel: Neuer Beleg → prüfen → mich benachrichtigen','code':'Zum Beispiel: Einen CSV-Import korrigieren'}
        for index,(key,(title,description)) in enumerate(KINDS.items()):
            grid.addWidget(card(tr(title),tr(description),tr(examples[key]),lambda _=False,k=key:self.select_kind(k),key),index//2,index%2)
        layout.addStretch();self.pages.addWidget(choose)
        edit=QWidget();layout=QVBoxLayout(edit);layout.setContentsMargins(0,0,0,0);layout.setSpacing(10)
        self.progress=label(tr('① Beschreiben     ② Prüfen     ③ Anlegen'),'codeMuted');layout.addWidget(self.progress)
        self.heading=label('','codeTitle');layout.addWidget(self.heading)
        self.subtitle=label('','codeSubtitle');layout.addWidget(self.subtitle)
        body=QWidget();fields=QVBoxLayout(body);fields.setContentsMargins(0,12,4,12);fields.setSpacing(14)
        self.ideas_box=QWidget();self.ideas_layout=QHBoxLayout(self.ideas_box);self.ideas_layout.setContentsMargins(0,0,0,0);self.ideas_layout.setSpacing(10);fields.addWidget(self.ideas_box)
        self.prompt_label=label(tr('Was soll dein Helfer für dich erledigen?'));fields.addWidget(self.prompt_label)
        self.prompt=QPlainTextEdit();self.prompt.setAccessibleName(tr('Dein Auftrag'));self.prompt.setPlaceholderText(tr('Beschreibe, was Lumen für dich erledigen soll …'));self.prompt.setFixedHeight(130);fields.addWidget(self.prompt)
        from code_blocks_editor import BlockEditor
        self.flow_editor=BlockEditor(self);self.flow_editor.changed.connect(self.flow_changed);self.flow_editor.hide();fields.addWidget(self.flow_editor)
        self.idea_help=label('','codeMuted');self.idea_help.setMinimumHeight(22);fields.addWidget(self.idea_help)
        self.example=button(tr('Ausprobierbares Beispiel öffnen'),self.open_example,'media-playback-start');self.example.hide();fields.addWidget(self.example,0)
        self.prompt.textChanged.connect(self.update_example)
        self.directory_box=QWidget();directory_layout=QVBoxLayout(self.directory_box);directory_layout.setContentsMargins(0,0,0,0);directory_layout.setSpacing(8)
        directory_layout.addWidget(label(tr('Projektordner')));directory_row=QHBoxLayout()
        self.directory=QLineEdit();self.directory.setAccessibleName(tr('Projektordner'));self.directory.setPlaceholderText(tr('Ausdrücklich ausgewählter Projektordner'))
        directory_row.addWidget(self.directory,1);directory_row.addWidget(button(tr('Ordner wählen'),self.choose_directory,'folder-open'));directory_layout.addLayout(directory_row);fields.addWidget(self.directory_box)
        self.context_toggle=button(tr('Name und Lumen-Projekt'),lambda:self.context.setVisible(self.context_toggle.isChecked()));self.context_toggle.setCheckable(True);self.context_toggle.setObjectName('codeLink');fields.addWidget(self.context_toggle)
        self.context=QWidget();context_layout=QVBoxLayout(self.context);context_layout.setContentsMargins(0,0,0,0);context_layout.setSpacing(8)
        context_layout.addWidget(label(tr('Name')));self.name=QLineEdit();self.name.setMaxLength(160);self.name.setAccessibleName(tr('Name'));self.name.setPlaceholderText(tr('Name – später änderbar'));context_layout.addWidget(self.name)
        context_layout.addWidget(label(tr('Zu einem Lumen-Projekt hinzufügen')));self.project=QComboBox();self.project.setAccessibleName(tr('Lumen-Projekt'));self.project.addItem(tr('Ohne Projekt'),'')
        for key,title in (projects or {}).items():self.project.addItem(title,key)
        context_layout.addWidget(self.project);fields.addWidget(self.context);self.context.hide();fields.addStretch()
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);layout.addWidget(scroll,1)
        self.error=label('','codeError');layout.addWidget(self.error)
        actions=QHBoxLayout();actions.addWidget(button(tr('Zur Auswahl'),self.back));actions.addStretch();actions.addWidget(button(tr('Weiter zur Prüfung'),self.review,primary=True));layout.addLayout(actions);self.pages.addWidget(edit)
        review=QWidget();layout=QVBoxLayout(review);layout.setContentsMargins(0,0,0,0);layout.setSpacing(16)
        layout.addWidget(label(tr('① Beschreiben     ② Prüfen     ③ Anlegen'),'codeMuted'));layout.addWidget(label(tr('Passt der Auftrag so?'),'codeTitle'))
        layout.addWidget(label(tr('Beim Anlegen werden noch keine Aufträge ausgeführt.'),'codeSubtitle'))
        self.summary=QTextBrowser();self.summary.setObjectName('codeReview');layout.addWidget(self.summary,1)
        actions=QHBoxLayout();actions.addWidget(button(tr('Bearbeiten'),lambda:self.pages.setCurrentIndex(1)));actions.addStretch();actions.addWidget(button(tr('Entwurf anlegen'),self.create,primary=True));layout.addLayout(actions);self.pages.addWidget(review)
        goal=QWidget();goal_box=QVBoxLayout(goal);goal_box.setContentsMargins(0,0,0,0);goal_box.setSpacing(14)
        goal_box.addWidget(label(tr('Was möchtest du erreichen?'),'codeTitle'))
        goal_box.addWidget(label(tr('Beschreibe dein Ziel. Lumen schlägt dir den passenden Helfer vor.'),'codeSubtitle'))
        goal_box.addWidget(label(tr('Dein Ziel')));self.goal=QPlainTextEdit();self.goal.setAccessibleName(tr('Dein Ziel'));self.goal.setMaximumHeight(180);goal_box.addWidget(self.goal)
        self.goal_error=label('','codeError');goal_box.addWidget(self.goal_error)
        self.goal_status=label('','codeMuted');goal_box.addWidget(self.goal_status)
        actions=QHBoxLayout();self.goal_button=button(tr('Vorschlag erstellen'),self.suggest_goal,primary=True);actions.addWidget(self.goal_button)
        actions.addWidget(button(tr('Selbst auswählen'),lambda:self.pages.setCurrentIndex(0)));actions.addStretch();goal_box.addLayout(actions)
        goal_box.addWidget(label(tr('Nur dein Ziel geht an deine eingerichtete KI. Dieser Vorschlag führt nichts aus und erteilt keine Zugriffsrechte.'),'codeMuted'))
        self.goal_result=QTextBrowser();self.goal_result.hide();goal_box.addWidget(self.goal_result,1)
        self.goal_accept=button(tr('Vorschlag bearbeiten'),self.accept_goal,primary=True);self.goal_accept.hide();goal_box.addWidget(self.goal_accept)
        goal_box.addStretch();self.pages.addWidget(goal)
        choose.layout().insertWidget(2,button(tr('Zur Zielbeschreibung'),lambda:self.pages.setCurrentIndex(3)))
        self.pages.currentChanged.connect(self.update_navigation);self.pages.setCurrentIndex(3);self.update_navigation()

    def update_navigation(self,*_):
        editing=self.pages.currentIndex() in (1,2)
        self.findChild(QWidget,'codeRail').setVisible(self.pages.currentIndex()!=3)
        for key,control in self.nav.items():control.setChecked(editing and key==self.kind)
        self.footer.setText(tr('Meine Sammlung')+' / '+(tr(KINDS[self.kind][0]) if editing else tr('Neu erstellen')))

    def suggest_goal(self):
        from code_goal import proposal
        try:
            prompt=proposal(self.goal.toPlainText())
            if self.goal_engine is None:
                import tempfile
                from assistant_backend import OpenCodeBackend
                self.goal_directory=tempfile.TemporaryDirectory(prefix='lumen-code-plan-')
                self.goal_engine=OpenCodeBackend(Path(self.goal_directory.name),self,project_config=False)
                self.goal_engine.completed.connect(self.goal_generated)
            self.goal_submitted=self.goal.toPlainText();self.goal_error.clear();self.goal_result.hide();self.goal_accept.hide()
            self.goal_button.setEnabled(False);self.goal.setReadOnly(True)
            self.goal_status.setText(tr('Lumen sucht die passende Form für dein Ziel …'))
            self.goal_engine.send(prompt,proposal=True,title='Lumen Code')
        except (ValueError,OSError,RuntimeError) as error:
            self.goal_error.setText(tr(str(error)));self.goal_button.setEnabled(True);self.goal.setReadOnly(False)

    def goal_generated(self,success,result):
        if self.closed:return
        from code_goal import parse
        from html import escape
        self.goal_button.setEnabled(True);self.goal.setReadOnly(False);self.goal_status.clear()
        try:
            if not success:raise ValueError('Kein Vorschlag erstellt. Dein Ziel bleibt erhalten.')
            p=parse(result);self.recommendation=p
            self.goal_result.setHtml('<h2>'+escape(p['title'])+'</h2><p>'+escape(tr(KINDS[p['kind']][0]))+'</p><p>'+escape(p['reason'])+'</p><h3>'+escape(tr('Daran prüfen wir das Ergebnis'))+'</h3><ul>'+''.join('<li>'+escape(c)+'</li>' for c in p['checks'])+'</ul>')
            self.goal_result.show();self.goal_accept.show()
        except ValueError as error:self.goal_error.setText(tr(str(error)))

    def accept_goal(self):
        p=self.recommendation
        if not p:return
        if self.goal.toPlainText()!=self.goal_submitted:
            self.goal_error.setText(tr('Dein Ziel wurde geändert. Bitte einen neuen Vorschlag erstellen.'));return
        if self.drafts.get(p['kind']) and QMessageBox.question(self,tr('Lumen · Vorschlag'),tr('Den bisherigen Auftrag durch diesen Vorschlag ersetzen?'))!=QMessageBox.Yes:return
        prompt=p['prompt']+'\n\n'+tr('Daran prüfen wir das Ergebnis')+':\n'+'\n'.join('• '+c for c in p['checks'])
        from code_blocks import starter
        plan=starter()
        for n in plan['nodes']:
            if n['kind']=='ai':n['config']=p['prompt']
        self.drafts[p['kind']]={'title':p['title'],'prompt':prompt,'flow':plan}
        self.select_kind(p['kind'])

    def flow_changed(self):self.flow_dirty=True

    def capture(self):
        self.drafts[self.kind]={'title':self.name.text(),'prompt':self.prompt.toPlainText(),
                                'project_id':self.project.currentData(),'directory':self.directory.text(),'flow':self.flow_editor.plan(False),'flow_dirty':self.flow_dirty,'idea':self.selected_idea['id'] if self.selected_idea else ''}

    def select_kind(self,kind):
        if self.pages.currentIndex()==1:self.capture()
        self.kind=kind;draft=self.drafts.get(kind,{})
        if not draft and self.goal.toPlainText().strip():
            from code_blocks import starter
            plan=starter()
            for n in plan['nodes']:
                if n['kind']=='ai':n['config']=self.goal.toPlainText()
            draft={'prompt':self.goal.toPlainText(),'flow':plan}
        self.selected_idea=next((i for i in IDEAS if i['id']==draft.get('idea') and i['kind']==kind),None)
        self.flow_editor.set_plan(draft.get('flow'));self.flow_dirty=draft.get('flow_dirty',False);self.flow_editor.setVisible(kind=='automation');self.prompt.setVisible(kind!='automation')
        self.heading.setText(tr(KINDS[kind][0]));self.subtitle.setText(tr(KINDS[kind][1]));self.prompt_label.setVisible(kind!='automation');self.prompt.setPlainText(draft.get('prompt',''));self.name.setText(draft.get('title',''))
        self.project.setCurrentIndex(max(0,self.project.findData(draft.get('project_id',''))));self.directory.setText(draft.get('directory',''))
        self.idea_buttons={}
        while self.ideas_layout.count():self.ideas_layout.takeAt(0).widget().deleteLater()
        for idea in IDEAS:
            if idea['kind']==kind:
                control=button(tr(idea['title']),lambda _=False,i=idea:self.use_idea(i));control.setToolTip(tr(idea['description']));control.setCheckable(True);self.idea_buttons[idea['id']]=control;self.ideas_layout.addWidget(control)
        self.ideas_box.setVisible(kind in ('app','tool'));self.directory_box.setVisible(kind=='code');self.idea_help.clear();self.error.clear();self.pages.setCurrentIndex(1);self.update_navigation();self.update_example()

    def use_idea(self,idea):
        if self.prompt.toPlainText().strip() and self.prompt.toPlainText()!=tr(idea['prompt']):
            answer=QMessageBox.question(self,tr('Lumen · Startidee'),tr('Den bisherigen Auftrag durch diese Startidee ersetzen?'))
            if answer!=QMessageBox.Yes:return
        self.selected_idea=idea
        self.name.setText(tr(idea['title']));self.prompt.setPlainText(tr(idea['prompt']))
        self.idea_help.setText(tr(idea['input'])+' → '+tr('Dein gespeicherter Auftrag')+' → '+tr(idea['output']) if idea['kind']=='tool' else tr(idea['description']))

    def update_example(self):
        idea=self.selected_idea
        matches=bool(idea and self.prompt.toPlainText()==tr(idea['prompt']))
        for key,control in self.idea_buttons.items():control.setChecked(bool(matches and key==idea['id']))
        self.example.setVisible(matches and self.kind=='app')
        self.idea_help.setText((tr(idea['input'])+' → '+tr('Dein gespeicherter Auftrag')+' → '+tr(idea['output']) if idea['kind']=='tool' else tr(idea['description'])) if matches else '')

    def open_example(self):
        import tempfile
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from code_library_contract import app_document
        idea=self.selected_idea
        if not idea or self.prompt.toPlainText()!=tr(idea['prompt']):return
        examples=json.loads(Path(__file__).with_name('code_creation_examples.json').read_text())
        with tempfile.NamedTemporaryFile(mode='w',suffix='.html',prefix='lumen-example-',delete=False) as output:
            output.write(app_document(examples[idea['id']+('-en' if language()=='en' else '')]))
        # Kept while the external browser uses it; removed when this creation dialog closes.
        self.example_files=getattr(self,'example_files',[])+[Path(output.name)]
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(output.name)):self.error.setText(tr('App-Vorschau konnte nicht geöffnet werden.'))

    def done(self,value):
        self.closed=True
        if self.goal_engine:self.goal_engine.shutdown()
        if self.goal_directory:self.goal_directory.cleanup()
        self.flow_editor.shutdown()
        for path in getattr(self,'example_files',[]):path.unlink(missing_ok=True)
        super().done(value)

    def choose_directory(self):
        path=QFileDialog.getExistingDirectory(self,tr('Lumen · Projektordner auswählen'))
        if path:self.directory.setText(path)

    def back(self):self.capture();self.pages.setCurrentIndex(0)

    def review(self):
        from html import escape
        try:
            from code_flow import encode,prompt as flow_prompt
            plan=self.flow_editor.plan() if self.kind=='automation' else None
            prompt=flow_prompt(plan) if plan else self.prompt.toPlainText()
            if not prompt.strip():raise ValueError(tr('Beschreibe kurz, was Lumen für dich erledigen soll.'))
            if self.kind=='code' and not self.directory.text().strip():raise ValueError(tr('Bitte einen Projektordner auswählen.'))
            value={'prompt':prompt}
            if plan:value['flow']=encode(plan)
            if self.kind=='code':
                path=Path(self.directory.text()).expanduser().resolve(strict=True)
                if not path.is_dir():raise ValueError(tr('Der Projektordner ist nicht verfügbar.'))
                value['directory']=str(path)
            item=definition(self.kind,self.name.text().strip() or tr(KINDS[self.kind][0]),value=value)
            self.value={**item,'project_id':self.project.currentData()};self.capture()
            summary='<h2>'+escape(item['title'])+'</h2><p>'+escape(tr(KINDS[self.kind][0]))+'</p>'
            if plan:
                from code_blocks import CATALOG
                summary+='<h3>'+escape(tr('Bausteine'))+'</h3><ol>'
                for n in plan['nodes']:
                    summary+='<li><b>'+escape(n['title'])+'</b><p>'+escape(tr(CATALOG[n['kind']][2]))+'</p><p>'+escape(n['config']).replace('\n','<br>')+'</p></li>'
                summary+='</ol><p>'+escape(tr('Manueller Desktop-Ablauf. Quellen und Aktionen werden vor jedem Durchlauf geprüft.'))+'</p>'
            else:summary+='<p>'+escape(prompt).replace('\n','<br>')+'</p>'
            self.summary.setHtml(summary+'<p>'+escape(self.project.currentText())+'</p><p>'+escape(value.get('directory',''))+'</p>')
            self.pages.setCurrentIndex(2);self.error.clear()
        except (ValueError,OSError) as error:self.error.setText(str(error))

    def create(self):self.accept()

    def reject(self):
        if self.pages.currentIndex()==1:self.capture()
        if self.goal.toPlainText().strip() or any(draft.get('prompt','').strip() or draft.get('title','').strip() or draft.get('flow_dirty') or any(n.get('config') for n in draft.get('flow',{}).get('nodes',[]) if n.get('kind') in ('read_file','save_file','save_note','create_task')) for draft in self.drafts.values()):
            if QMessageBox.question(self,tr('Lumen · Entwurf verwerfen'),tr('Erstellung schließen und den ungespeicherten Entwurf verwerfen?'))!=QMessageBox.Yes:return
        super().reject()
