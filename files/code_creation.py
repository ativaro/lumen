"""One reviewed creation path per kind; existing small apps remain in the collection."""
import json
import tempfile
from pathlib import Path
from html import escape
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QStackedWidget,QScrollArea,QLineEdit,QComboBox,QPlainTextEdit,QTextBrowser,QMessageBox,QSizePolicy,QInputDialog
from tools_ui import button,label,row
from lumen_i18n import tr
from code_library_contract import definition
from code_creation_forms import ToolForm,RoutineForm,CodeForm

IDEAS=json.loads(Path(__file__).with_name('code_creation_ideas.json').read_text())
KINDS={'tool':('Werkzeug','Eingabe, Ergebnis und feste Regeln für einen wiederverwendbaren Helfer.'),
       'routine':('Zeitpläne & Routinen','Mehrere feste Schritte, die manuell oder nach Zeitplan starten.'),
       'automation':('Automation','Auslöser, optionale Bedingungen und Aktionen in einem gemeinsamen Editor.'),
       'code':('Code im Projekt','Einen Projektordner öffnen, ein Repository klonen oder neu beginnen.')}


class CreationDialog(QDialog):
    def __init__(self,parent=None,projects=None,tools=None,kind=None):
        super().__init__(parent);self.setWindowTitle(tr('Lumen · Neu erstellen'));self.resize(1120,850)
        self.kind='tool';self.value=None;self.drafts={};self.goal_engine=None;self.goal_directory=None;self.recommendation=None;self.goal_submitted='';self.closed=False;self.job=None;self.closing=False;self.test_engine=None;self.test_directory=None;self.goal_seeded=set()
        from code_design import editor_shell,card
        main,self.header,self.footer=editor_shell(self,tr('Lumen · Neu erstellen'),tr('Wähle den passenden Weg für deine Aufgabe.'))
        box=QVBoxLayout(main);box.setContentsMargins(0,0,0,0);box.setSpacing(16)
        goal_link=button(tr('Ziel beschreiben'),self.show_goal);self.header.actions.addWidget(goal_link)
        close_button=button(tr('Schließen'),self.reject);self.header.actions.addWidget(close_button)
        self.pages=QStackedWidget();box.addWidget(self.pages,1)
        choose=QWidget();layout=QVBoxLayout(choose);layout.setContentsMargins(0,0,0,0)
        grid=QGridLayout();grid.setSpacing(16);layout.addLayout(grid)
        examples={'tool':'Eingabe → Regeln → Ergebnis','routine':'Schritte → Zeitplan → prüfen','automation':'Lumen soll … · Aktion wählen','code':'Projekt → erster Auftrag → Gespräch'}
        for index,(key,(title,description)) in enumerate(KINDS.items()):grid.addWidget(card(tr(title),tr(description),tr(examples[key]),lambda _=False,k=key:self.select_kind(k),key),index//2,index%2)
        self.creation_grid=grid;self.creation_cards=[grid.itemAt(i).widget() for i in range(grid.count())];layout.addStretch();choose_scroll=QScrollArea();choose_scroll.setWidgetResizable(True);choose_scroll.setWidget(choose);self.pages.addWidget(choose_scroll)
        edit=QWidget();layout=QVBoxLayout(edit);layout.setContentsMargins(0,0,0,0);layout.setSpacing(16);self.heading=self.header.title;self.subtitle=self.header.subtitle
        self.automation_title=label(tr('Unbenannte Automation'),'codeTitle');layout.addWidget(self.automation_title)
        self.rename_automation=button(tr('Umbenennen'),self.rename_sentence);self.header.actions.addWidget(self.rename_automation)
        self.template_button=button(tr('Beschreibungs-Vorlage öffnen …'),self.import_description,'document-import');self.header.actions.addWidget(self.template_button)
        from code_collection_view import QUIET_STYLE
        for control in (goal_link,close_button,self.rename_automation,self.template_button):
            control.setObjectName('codeCollectionQuiet');control.setStyleSheet(QUIET_STYLE)
        self.name_caption=label(tr('Name'));layout.addWidget(self.name_caption);self.name=QLineEdit();self.name.setAccessibleName(tr('Name'));self.name.setMaxLength(160);layout.addWidget(self.name)
        self.name.textChanged.connect(self.automation_title.setText)
        project_row=QHBoxLayout();self.project=QComboBox();self.project.setAccessibleName(tr('Lumen-Projekt'));self.project.addItem(tr('Ohne Projekt'),'')
        for key,title in (projects or {}).items():self.project.addItem(title,key)
        project_row.addWidget(self.project,1);project_box=QWidget();project_box.setLayout(project_row);project_row.setContentsMargins(0,0,0,0);project_box.hide();project_toggle=button(tr('Zu einem Lumen-Projekt hinzufügen · optional'),lambda:project_box.setVisible(not project_box.isVisible()));project_toggle.setObjectName('codeLink');self.project_toggle=project_toggle;layout.addWidget(project_toggle);layout.addWidget(project_box)
        self.code_name_toggle=button(tr('Bezeichnung anpassen · optional'),lambda checked:(self.name.setVisible(checked),self.name_caption.setVisible(checked)));self.code_name_toggle.setCheckable(True);self.code_name_toggle.setObjectName('codeLink');layout.addWidget(self.code_name_toggle)
        store=getattr(parent,'store',None)
        from code_triggers import project_choices
        automation_projects=project_choices(store) if store is not None else projects
        from code_sections_editor import SectionsEditor
        self.forms={'tool':ToolForm(self),'routine':RoutineForm(self,tools,store),'automation':SectionsEditor(self,projects=automation_projects,tools=tools),'code':CodeForm(self)}
        self.form_stack=QStackedWidget();self.form_stack.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored);self.form_stack.setMinimumHeight(140);self.form_keys=list(self.forms)
        for form in self.forms.values():
            if isinstance(form,SectionsEditor):self.form_stack.addWidget(form)
            else:
                scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(form);self.form_stack.addWidget(scroll)
        layout.addWidget(self.form_stack,1);self.flow_editor=self.forms['automation'];self.directory=self.forms['code'].directory
        self.error=label('','codeError');self.error.hide();layout.addWidget(self.error)
        self.flow_editor.changed.connect(self.automation_changed)
        test_box=self.forms['tool'].test_box
        self.test_button=button(tr('Beispiel mit KI prüfen'),self.test_tool,primary=True);test_box.addWidget(self.test_button)
        self.test_status=label('','codeMuted');self.test_status.hide();test_box.addWidget(self.test_status)
        self.test_result=QPlainTextEdit();self.test_result.setReadOnly(True);self.test_result.setMinimumHeight(160);self.test_result.setAccessibleName(tr('Tatsächliches Testergebnis'));self.test_result.setPlaceholderText(tr('Hier erscheint das tatsächliche Ergebnis deines Tests.'));test_box.addWidget(self.test_result,1)
        actions=QHBoxLayout();actions.addWidget(button(tr('Andere Art wählen'),self.back));actions.addStretch();self.review_button=button(tr('Weiter zur Prüfung'),self.review,primary=True);actions.addWidget(self.review_button);layout.addLayout(actions);self.pages.addWidget(edit)
        review=QWidget();layout=QVBoxLayout(review);layout.setContentsMargins(0,0,0,0);layout.addWidget(label(tr('Entwurf prüfen'),'codeTitle'));self.summary=QTextBrowser();self.summary.setObjectName('codeReview');self.summary.setOpenExternalLinks(False);layout.addWidget(self.summary,1)
        self.create_button=button(tr('Entwurf anlegen'),self.create,primary=True);layout.addWidget(row(button(tr('Bearbeiten'),lambda:self.pages.setCurrentIndex(1)),self.create_button));self.pages.addWidget(review)
        goal=QWidget();layout=QVBoxLayout(goal);layout.addWidget(label(tr('Was möchtest du erreichen?'),'codeTitle'));self.goal=QPlainTextEdit();self.goal.setAccessibleName(tr('Dein Ziel'));layout.addWidget(self.goal);self.goal_error=label('','codeError');layout.addWidget(self.goal_error);self.goal_status=label('','codeMuted');layout.addWidget(self.goal_status)
        self.goal_button=button(tr('Vorschlag erstellen'),self.suggest_goal,primary=True);layout.addWidget(row(self.goal_button,button(tr('Selbst auswählen'),lambda:self.pages.setCurrentIndex(0))));self.goal_result=QTextBrowser();layout.addWidget(self.goal_result);self.goal_accept=button(tr('Vorschlag bearbeiten'),self.accept_goal);self.goal_accept.hide();layout.addWidget(self.goal_accept)
        goal_scroll=QScrollArea();goal_scroll.setWidgetResizable(True);goal_scroll.setWidget(goal);self.pages.addWidget(goal_scroll)
        self.pages.currentChanged.connect(self.update_navigation);self.update_navigation()
        if kind in KINDS:self.select_kind(kind)
        self.baseline=self.fingerprint()

    def fingerprint(self):
        from PySide6.QtWidgets import QCheckBox
        widgets=[(type(w).__name__,w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text() if isinstance(w,QLineEdit) else w.currentIndex() if isinstance(w,QComboBox) else w.isChecked()) for w in self.findChildren(QWidget) if isinstance(w,(QLineEdit,QPlainTextEdit,QComboBox,QCheckBox)) and not any(self.forms[k].isAncestorOf(w) for k in ('automation','routine'))]
        return widgets+[(json.dumps(self.forms[k].plan(False),sort_keys=True),self.forms[k].full_description.toPlainText(),self.forms[k].description.toPlainText()) for k in ('automation','routine')]

    @property
    def prompt(self):return self.forms['tool'].request if self.kind=='tool' else self.forms['code'].task if self.kind=='code' else self.forms['routine'].full_description if self.kind=='routine' else self.flow_editor.description

    def capture(self):self.drafts[self.kind]={'title':self.name.text(),'project_id':self.project.currentData()}

    def select_kind(self,kind):
        if kind not in KINDS:return
        if self.pages.currentIndex()==1:self.capture()
        self.kind=kind;draft=self.drafts.get(kind,{});self.name.setText(draft.get('title',tr('Unbenannte Automation') if kind=='automation' else ''));self.project.setCurrentIndex(max(0,self.project.findData(draft.get('project_id',''))));self.form_stack.setCurrentIndex(self.form_keys.index(kind));self.error.clear();self.error.hide();self.pages.setCurrentIndex(1);self.update_navigation()
        if self.goal.toPlainText().strip() and kind not in self.goal_seeded:
            if kind in ('automation','routine'):
                target=next((n for n in self.forms[self.kind].items if n['kind']=='ai'),None)
                if target:target['config']=self.goal.toPlainText();self.forms[kind].refresh()
                self.forms[kind].full_description.setPlainText(self.goal.toPlainText())
            elif not self.prompt.toPlainText().strip():self.prompt.setPlainText(self.goal.toPlainText())
            self.goal_seeded.add(kind)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'creation_cards'):
            columns=1 if self.width()<800 else 2
            for i,card in enumerate(self.creation_cards):self.creation_grid.addWidget(card,i//columns,i%columns)

    def update_navigation(self,*_):
        editing=self.pages.currentIndex() in (1,2)
        titles={'tool':'Lumen · Werkzeug erstellen','routine':'Lumen · Routine zusammenstellen','automation':'Lumen · Automation erstellen','code':'Lumen · Code-Projekt öffnen'}
        self.header.title.setText(tr(titles[self.kind]) if editing else tr('Lumen · Dein Ziel') if self.pages.currentIndex()==3 else tr('Lumen · Neu erstellen'))
        self.header.subtitle.setText(tr(KINDS[self.kind][1]) if editing else tr('Beschreibe deine Aufgabe oder wähle selbst den passenden Weg.'))
        if self.kind=='automation' and editing:self.header.title.setText(tr('Lumen Automation'));self.header.subtitle.setText(tr('Ein Ablauf, den du lesen kannst.'))
        self.setWindowTitle(self.header.title.text())
        self.code_name_toggle.setVisible(self.kind=='code')
        self.name.setVisible(self.kind not in ('code','automation') or (self.kind=='code' and self.code_name_toggle.isChecked()));self.name_caption.setVisible(not self.name.isHidden())
        sentence=self.kind=='automation' and editing;self.automation_title.setVisible(sentence);self.automation_title.setText(self.name.text());self.rename_automation.setVisible(sentence);self.project_toggle.setVisible(self.kind!='automation')
        self.template_button.setVisible(sentence)
        self.review_button.setText(tr('Speichern' if self.kind=='automation' else 'Weiter zur Prüfung'))
        self.footer.setText(tr('Meine Sammlung')+' / '+tr(KINDS[self.kind][0] if self.pages.currentIndex() in (1,2) else 'Neu erstellen'))

    def rename_sentence(self):
        title,ok=QInputDialog.getText(self,tr('Lumen · Automation umbenennen'),tr('Name'),text=self.name.text())
        if ok and title.strip():self.name.setText(title.strip()[:160]);self.automation_title.setText(self.name.text())

    def automation_changed(self):
        if self.kind!='automation' or self.error.isHidden():return
        try:self.flow_editor.plan()
        except ValueError as error:self.error.setText(tr(str(error)));return
        self.error.clear();self.error.hide()

    def load_description(self,value):
        editor=self.flow_editor
        if editor.locked or (editor.engine and editor.engine.busy):raise ValueError(tr('Den laufenden KI-Vorschlag zuerst abwarten.'))
        source=json.loads(editor.items[0]['config']) if editor.version==3 else None
        if len(editor.items)>1 or editor.gate_enabled or source!={'kind':'text','text':''} or editor.full_description.toPlainText() or editor.description.toPlainText() or self.name.text() not in ('',tr('Unbenannte Automation')):
            if QMessageBox.question(self,tr('Lumen · Entwurf ersetzen'),tr('Den aktuellen Entwurf durch diese Beschreibung ersetzen? Aktionen, Quellen und bisherige Vorschläge werden verworfen.'),QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return False
        self.select_kind('automation');self.name.setText(value['title']);self.automation_title.setText(value['title'])
        self.project.setCurrentIndex(0);editor.set_plan();editor.description.clear();editor.proposal_condition=None;editor.accept_proposal.hide();editor.description_status.clear()
        while editor.proposal_layout.count():editor.proposal_layout.takeAt(0).widget().deleteLater()
        editor.full_candidate=None;editor.full_preview.clear();editor.full_accept.hide();editor.full_signature='';editor.full_text=''
        editor.full_description.setPlainText(value['definition'].get('prompt',''));editor.full_status.setText(tr('Importierte Beschreibung · keine Strukturkopie, Quellenbindung oder Freigabe. Bearbeite sie oder lege die gewünschten Aktionen selbst an.'));editor.tabs.setCurrentIndex(2);return True

    def import_description(self):
        from PySide6.QtWidgets import QFileDialog
        from code_library_contract import import_template
        path,_=QFileDialog.getOpenFileName(self,tr('Lumen · Beschreibungs-Vorlage öffnen'),'','Lumen (*.json)')
        if not path:return
        try:
            source=Path(path)
            if source.stat().st_size>2000000:raise ValueError(tr('Vorlage ist zu groß.'))
            value=import_template(source.read_text(encoding='utf-8'))
            if value['kind']!='automation':raise ValueError(tr('Eine Vorlage für Automation wählen.'))
            self.load_description(value)
        except (ValueError,OSError) as error:self.error.setText(tr(str(error)));self.error.show()

    def back(self):self.capture();self.pages.setCurrentIndex(0)

    def show_goal(self):
        if self.pages.currentIndex()==1:self.capture()
        self.pages.setCurrentIndex(3)

    def review(self):
        try:
            if self.kind=='automation':
                from code_flow import encode,prompt
                plan=self.flow_editor.plan();value={'flow':encode(plan),'prompt':prompt(plan)}
            else:value=self.forms[self.kind].value()
            storage_kind='automation' if self.kind=='routine' else self.kind
            title=self.name.text().strip() or (Path(value['directory']).name if self.kind=='code' else tr(KINDS[self.kind][0]))
            self.value={**definition(storage_kind,title,value=value),'project_id':self.project.currentData()}
            if self.kind=='automation':self.create();return
            text='<h2>'+escape(self.value['title'])+'</h2><p>'+escape(tr(KINDS[self.kind][0]))+'</p>'
            if self.kind=='automation':
                from code_conditions import describe
                from code_block_paths import tree,config
                def summary(items):
                    result='<ul>'
                    for n in items:
                        if n['kind']=='manual':
                            from code_triggers import describe as trigger_description
                            description=trigger_description(config(n))
                        elif n['kind']=='condition':description=describe(config(n))
                        else:description=n['title']
                        result+='<li>'+escape(description)
                        if n['kind'] not in ('manual','choose','for_each','condition','end_each') and n['config']:result+='<p>'+escape(n['config']).replace('\n','<br>')+'</p>'
                        if n['kind']=='for_each':result+=summary(n['steps'])
                        if n['kind']=='choose':
                            for case in n['cases']:result+='<p>'+escape(describe(case['when']))+'</p>'+summary(case['steps'])
                            result+='<p>'+tr('Sonst')+'</p>'+summary(n['otherwise'])
                        result+='</li>'
                    return result+'</ul>'
                text+=summary(tree(plan))
            else:text+='<p>'+escape(value.get('prompt','')).replace('\n','<br>')+'</p>'
            if self.kind=='routine':
                from code_triggers import describe as trigger_description
                from code_block_paths import config
                text+='<p>'+escape(trigger_description(config(self.forms['routine'].plan()['nodes'][0])))+'</p>'
            if self.kind=='code':
                self.project_setup=self.forms['code'].setup();text+='<p>'+escape(value['directory'])+'</p><p>'+escape(self.project_setup['url'])+'</p>'
                self.create_button.setText(tr({'folder':'Projektgespräch öffnen','repo':'Klonen und Projekt öffnen','new':'Projekt anlegen und öffnen'}[self.project_setup['source']]))
            else:self.create_button.setText(tr('Entwurf anlegen'))
            text+='<p>'+escape(tr('Noch keine Ausführung. Automationen und Routinen bleiben bis zur ausdrücklichen Freigabe pausiert.'))+'</p>'
            self.summary.setHtml(text);self.error.clear();self.capture();self.pages.setCurrentIndex(2)
        except (ValueError,OSError) as error:self.error.setText(tr(str(error)));self.error.show();self.value=None

    def create(self):
        if not self.value:return
        if self.kind!='code':self.accept();return
        if self.job:return
        from code_project_setup import prepare
        from lumen_jobs import Job
        self.pages.setEnabled(False);self.job=Job(lambda job:prepare(self.project_setup,job),self);self.job.result.connect(self.project_ready);self.job.failed.connect(self.project_failed);self.job.finished.connect(self.project_finished);self.job.start()

    def project_ready(self,path):
        if not self.closing:self.value['definition']['directory']=path;self.project_prepared=True

    def project_failed(self,text):self.error.setText(text);self.error.show();self.pages.setCurrentIndex(1)

    def project_finished(self):
        job,self.job=self.job,None;job.deleteLater();self.pages.setEnabled(True)
        if self.closing:self.done(QDialog.Rejected)
        elif getattr(self,'project_prepared',False):self.accept()

    def use_idea(self,idea):
        if idea['kind']=='tool':self.forms['tool'].request.setPlainText(tr(idea['prompt']));self.name.setText(tr(idea['title']))

    def suggest_goal(self):
        try:
            from code_goal import proposal
            prompt=proposal(self.goal.toPlainText())
            if self.goal_engine is None:
                from assistant_backend import OpenCodeBackend
                self.goal_directory=tempfile.TemporaryDirectory(prefix='lumen-code-plan-');self.goal_engine=OpenCodeBackend(Path(self.goal_directory.name),self,project_config=False);self.goal_engine.completed.connect(self.goal_generated)
            self.goal_submitted=self.goal.toPlainText();self.goal_button.setEnabled(False);self.goal.setReadOnly(True);self.goal_engine.send(prompt,proposal=True,title='Lumen Code')
        except (ValueError,OSError,RuntimeError) as error:self.goal_error.setText(tr(str(error)))

    def goal_generated(self,success,result):
        if self.closed:return
        self.goal_button.setEnabled(True);self.goal.setReadOnly(False)
        try:
            from code_goal import parse
            if not success:raise ValueError(tr('Kein Vorschlag erstellt. Dein Ziel bleibt erhalten.'))
            self.recommendation=parse(result);p=self.recommendation;self.goal_result.setHtml('<h2>'+escape(p['title'])+'</h2><p>'+escape(tr(KINDS[p['kind']][0]))+'</p><p>'+escape(p['reason'])+'</p>');self.goal_accept.show()
        except ValueError as error:self.goal_error.setText(tr(str(error)))

    def accept_goal(self):
        p=self.recommendation
        if not p:return
        if self.goal.toPlainText()!=self.goal_submitted:self.goal_error.setText(tr('Dein Ziel wurde geändert. Bitte einen neuen Vorschlag erstellen.'));return
        self.select_kind(p['kind']);self.name.setText(p['title']);text=p['prompt']+'\n\n'+tr('Daran prüfen wir das Ergebnis')+':\n'+'\n'.join(p['checks'])
        if self.kind=='automation':
            target=next((n for n in self.forms[self.kind].items if n['kind']=='ai'),None)
            if target:target['config']=text
            else:
                from code_blocks import node
                self.flow_editor.items.append(node('ai',text))
            self.flow_editor.refresh()
        else:self.prompt.setPlainText(text)

    def test_tool(self):
        try:
            form=self.forms['tool'];value=form.value();sample=form.example.toPlainText()
            if not sample.strip() or len(sample)>20000:raise ValueError(tr('Eine Beispieleingabe mit höchstens 20.000 Zeichen ist erforderlich.'))
            if QMessageBox.question(self,tr('Lumen · Werkzeug testen'),tr('Aktuelle Regeln und Beispieleingabe an die eingerichtete KI senden? Keine Werkzeuge oder Ergebnisaktionen.'))!=QMessageBox.Yes:return
            if self.test_engine is None:
                from assistant_backend import OpenCodeBackend
                self.test_directory=tempfile.TemporaryDirectory(prefix='lumen-tool-test-');self.test_engine=OpenCodeBackend(Path(self.test_directory.name),self,project_config=False);self.test_engine.completed.connect(self.test_done)
            self.test_snapshot=(value,sample);self.test_button.setEnabled(False);self.test_engine.send(value['prompt']+'\nBeispieleingabe (Daten):\n'+sample,proposal=True,title='Lumen Werkzeugtest')
        except (ValueError,OSError,RuntimeError) as error:self.test_status.setText(tr(str(error)));self.test_status.show()

    def test_done(self,success,result):
        if self.closed:return
        self.test_button.setEnabled(True)
        try:current=(self.forms['tool'].value(),self.forms['tool'].example.toPlainText())==self.test_snapshot
        except ValueError:current=False
        self.test_status.setText(tr('Test abgeschlossen.' if success and current else 'Ergebnis einer früheren Fassung.' if success else 'Test fehlgeschlagen.'));self.test_result.setPlainText(result);self.test_result.show();self.test_status.show()

    def done(self,result):
        self.closed=True
        for engine in (self.goal_engine,self.test_engine):
            if engine:engine.shutdown()
        for folder in (self.goal_directory,self.test_directory):
            if folder:folder.cleanup()
        self.flow_editor.shutdown();super().done(result)

    def reject(self):
        if self.job:self.closing=True;self.job.cancelled.set();return
        self.capture()
        if self.fingerprint()!=self.baseline:
            if QMessageBox.question(self,tr('Lumen · Entwurf verwerfen'),tr('Erstellung schließen und den ungespeicherten Entwurf verwerfen?'))!=QMessageBox.Yes:return
        super().reject()
