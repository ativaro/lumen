"""Live native application mixer, backed by the existing Pulse-compatible server."""
import time
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QTabWidget, QSlider, QComboBox, QCheckBox, QSpinBox, QTreeWidget, QTreeWidgetItem,
    QDialog, QDialogButtonBox, QFormLayout, QInputDialog, QMessageBox)
from tools_ui import ToolWindow, Job, button, label, row
import sound_data as sound


class Sound(ToolWindow):
    def __init__(self,root=None):
        super().__init__('sound','Lumen Sound','Jede Anwendung am richtigen Ort. Musik und Gespräche im Gleichgewicht.','lumen-sound',root)
        self.current=sound.settings(self.library)['id'];self.sidebar.hide();self.poller=None;self.data=None;self.cards={};self.closing=False
        self.content.setContentsMargins(0,0,0,0)
        self.summary=label('Audiogeräte werden gelesen …','heading');self.content.addWidget(self.summary)
        self.tabs=QTabWidget();self.content.addWidget(self.tabs,1)
        mixer=QWidget();ml=QVBoxLayout(mixer);ml.setContentsMargins(0,16,0,0)
        self.empty=label('Starte Musik oder ein Video. Aktive Anwendungen erscheinen hier automatisch.','muted');ml.addWidget(self.empty)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame)
        self.streams=QWidget();self.stream_layout=QVBoxLayout(self.streams);self.stream_layout.setContentsMargins(0,0,8,0);self.stream_layout.setSpacing(12);self.stream_layout.addStretch()
        scroll.setWidget(self.streams);ml.addWidget(scroll,1);self.tabs.addTab(mixer,'Anwendungen')
        automation=QWidget();al=QVBoxLayout(automation);al.setContentsMargins(0,16,0,0);al.setSpacing(14)
        al.addWidget(label('Deine App-Regeln','heading'));al.addWidget(label('Gespeicherte Regeln gelten für neue Streams derselben App. Bei Browsern umfasst eine App mehrere Tabs. Änderungen an laufenden Streams bleiben bis zum nächsten Start erhalten.','muted'))
        self.rules=QTreeWidget();self.rules.setHeaderLabels(['Anwendung','Lautstärke','Ausgabe','Rolle']);self.rules.setRootIsDecorated(False);self.rules.setAccessibleName('Gespeicherte Audioregeln');al.addWidget(self.rules,1)
        al.addWidget(row(button('App-Regel hinzufügen',lambda:self.safe(self.choose_rule),'list-add'),button('Bearbeiten',lambda:self.safe(self.edit_rule),'configure'),button('Entfernen',lambda:self.safe(self.remove_rule),'list-remove')))
        self.duck=QCheckBox('Musik während eines Gesprächs automatisch absenken');self.duck.setAccessibleName(self.duck.text());al.addWidget(self.duck)
        self.level=QSpinBox();self.level.setRange(5,100);self.level.setSuffix(' %');self.level.setAccessibleName('Verbleibender Musikpegel während Gesprächen')
        al.addWidget(row(label('Währenddessen auf'),self.level,label('des vorherigen Pegels'),button('Absenkung speichern',lambda:self.safe(self.save_duck),'document-save')))
        al.addWidget(label('Rollen „Musik“ und „Gespräch“ in den App-Regeln wählen. Auslöser ist eine aktive Mikrofonverbindung oder ein als Gespräch gemeldeter Audiostream. Es wird kein Ton aufgenommen. Manuelle Lautstärkeänderungen haben Vorrang.','muted'))
        self.autostart=QComboBox();self.autostart.setAccessibleName('Automatik und Start bei Anmeldung')
        for title,value in [('Automatik aus','off'),('Für diese Anmeldung aktiv','session'),('Bei jeder Anmeldung starten','login')]:self.autostart.addItem(title,value)
        al.addWidget(row(self.autostart,button('Übernehmen',lambda:self.safe(self.set_mode),'dialog-ok-apply',True)))
        self.activity=label('','muted');al.addWidget(self.activity);self.tabs.addTab(automation,'Regeln & Gespräche')
        devices=QWidget();dl=QVBoxLayout(devices);dl.setContentsMargins(0,16,0,0)
        dl.addWidget(label('Verfügbare Ausgänge','heading'));dl.addWidget(label('Die Ausgabe wird pro Anwendung gewählt. Standardgerät und Hardwareprofile bleiben in den Systemeinstellungen.','muted'))
        self.outputs=QTreeWidget();self.outputs.setHeaderLabels(['Gerät','Status']);self.outputs.setRootIsDecorated(False);self.outputs.setAccessibleName('Verbundene Audioausgänge');dl.addWidget(self.outputs,1);self.tabs.addTab(devices,'Geräte')
        self.content.addWidget(row(label('Lokal · PipeWire / PulseAudio','muted'),button('Aktualisieren',self.poll,'view-refresh')))
        self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.poll);self.timer.start()
        self.load_rules();QTimer.singleShot(0,self.poll)

    def focus_record(self,key):self.current=key;self.load_rules()
    def create(self):pass
    def load(self,record):self.load_rules()

    def poll(self):
        if self.poller or self.job or self.closing:return
        self.poller=Job(lambda _:sound.snapshot(),self);self.poller.result.connect(self.update_audio)
        self.poller.failed.connect(lambda _:self.status.setText('Audioserver nicht erreichbar. PipeWire/PulseAudio und libpulse prüfen.'))
        self.poller.finished.connect(self.poll_finished);self.poller.start()

    def poll_finished(self):
        self.poller.deleteLater();self.poller=None
        if self.closing:QTimer.singleShot(0,self.close)

    def update_audio(self,data):
        self.data=data;tokens={s['token'] for s in data['streams']}
        if any(card['slider'].isSliderDown() or card['sink'].view().isVisible() for card in self.cards.values()):return
        for token in set(self.cards)-tokens:
            card=self.cards.pop(token);self.stream_layout.removeWidget(card['frame']);card['frame'].deleteLater()
        names={s['index']:s['name'] for s in data['sinks']}
        for stream in data['streams']:
            token=stream['token']
            if token not in self.cards:self.cards[token]=self.make_card(stream)
            card=self.cards[token];card['title'].setText(stream['title']);card['percent'].setText(str(stream['percent'])+' %')
            card['slider'].blockSignals(True);card['slider'].setValue(min(100,stream['percent']));card['slider'].blockSignals(False)
            card['mute'].blockSignals(True);card['mute'].setChecked(stream.get('mute',False));card['mute'].blockSignals(False)
            choices=[(s.get('description',s['name']),s['name']) for s in data['sinks']]
            if card['choices']!=choices:
                card['sink'].blockSignals(True);card['sink'].clear()
                for title,name in choices:card['sink'].addItem(title,name)
                card['choices']=choices;card['sink'].blockSignals(False)
            card['sink'].setCurrentIndex(card['sink'].findData(names.get(stream.get('sink'))))
            card['detail'].setText('Pausiert' if stream.get('corked',False) else 'Wiedergabe verbunden')
        self.empty.setVisible(not tokens);self.summary.setText(f"{len(data['streams'])} Wiedergaben · {len(data['sinks'])} Ausgänge · {len(data['recordings'])} Aufnahmeverbindungen")
        self.outputs.clear()
        for sink in data['sinks']:self.outputs.addTopLevelItem(QTreeWidgetItem([sink.get('description',sink['name']),{'RUNNING':'Aktiv','IDLE':'Bereit','SUSPENDED':'Ruht'}.get(sink.get('state'),sink.get('state',''))]))
        config=sound.settings(self.library);self.activity.setText(config.get('last_error') or config.get('activity','Automatik aus'))
        if config['mode']!='off' and time.time()-config.get('heartbeat',0)>10:self.activity.setText('Automatik ist gespeichert, meldet sich aber gerade nicht. Erneut übernehmen oder Dienst prüfen.')
        if not self.job:self.status.setText('Live-Ansicht · Änderungen betreffen nur den gewählten Audiostream')

    def make_card(self,stream):
        token=stream['token'];frame=QFrame();frame.setObjectName('toolAudio');frame.setStyleSheet('QFrame#toolAudio { background: palette(base); border: 1px solid palette(mid); border-radius: 12px; }')
        layout=QVBoxLayout(frame);layout.setContentsMargins(18,14,18,14);layout.setSpacing(10)
        title=label(stream['title'],'heading');detail=label('','muted');layout.addWidget(row(title,detail))
        slider=QSlider(Qt.Horizontal);slider.setRange(0,100);slider.setAccessibleName('Lautstärke '+stream['title']);percent=label('');percent.setMinimumWidth(60)
        slider.valueChanged.connect(lambda value:percent.setText(str(value)+' %'))
        slider.sliderReleased.connect(lambda:self.apply(token,'volume',slider.value()))
        # Keyboard changes do not emit sliderReleased.
        slider.actionTriggered.connect(lambda _:QTimer.singleShot(120,lambda:self.keyboard_volume(token,slider)))
        mute=QCheckBox('Stumm');mute.setAccessibleName('Stummschalten '+stream['title']);mute.clicked.connect(lambda value:self.apply(token,'mute',value))
        layout.addWidget(row(slider,percent,mute))
        sink=QComboBox();sink.setAccessibleName('Ausgabegerät '+stream['title']);sink.activated.connect(lambda _:self.apply(token,'sink',sink.currentData()))
        layout.addWidget(row(label('Ausgabe'),sink,button('Für App merken',lambda:self.safe(self.rule_dialog,stream['app']),'document-save')))
        self.stream_layout.insertWidget(self.stream_layout.count()-1,frame)
        return dict(frame=frame,title=title,detail=detail,slider=slider,percent=percent,mute=mute,sink=sink,choices=[])

    def keyboard_volume(self,token,slider):
        if token in self.cards and not slider.isSliderDown() and slider.hasFocus():self.apply(token,'volume',slider.value())

    def apply(self,token,action,value):
        if value is None:return
        self.work('Audioeinstellung übernehmen …',lambda _:sound.change(self.library,token,action,value),lambda _:self.status.setText('Audioeinstellung übernommen.'))

    def load_rules(self):
        config=sound.settings(self.library);self.rules.clear();names={s['name']:s.get('description',s['name']) for s in self.data['sinks']} if self.data else {}
        for key,rule in config['rules'].items():
            item=QTreeWidgetItem([rule['title'],str(rule['volume'])+' %'+(' · stumm' if rule['mute'] else ''),names.get(rule['sink'],rule['sink']) or 'Aktuelle Ausgabe',{'none':'Keine','music':'Musik','call':'Gespräch'}[rule['role']]]);item.setData(0,Qt.UserRole,key);self.rules.addTopLevelItem(item)
        self.duck.setChecked(config.get('duck',False));self.level.setValue(config.get('level',25));self.autostart.setCurrentIndex(self.autostart.findData(config['mode']))

    def choose_rule(self):
        if not self.data:raise ValueError('Zuerst den Audioserver verbinden.')
        apps={s['app']:s['title'] for s in self.data['streams']+self.data['recordings'] if s['app']}
        if not apps:raise ValueError('Die gewünschte App zuerst mit Musik oder einem Gespräch starten.')
        keys=list(apps);names=[apps[k]+' · '+k.split(':',1)[-1] for k in keys];name,ok=QInputDialog.getItem(self,'App-Regel hinzufügen','Aktive Anwendung',names,0,False)
        if ok:self.rule_dialog(keys[names.index(name)])

    def edit_rule(self):
        item=self.rules.currentItem()
        if item:self.rule_dialog(item.data(0,Qt.UserRole))

    def rule_dialog(self,key):
        if not key:raise ValueError('Diese Anwendung liefert keine stabile App-Kennung.')
        config=sound.settings(self.library);old=config['rules'].get(key,{})
        live=next((s for s in self.data['streams']+self.data['recordings'] if s['app']==key),{}) if self.data else {}
        title=old.get('title') or live.get('title') or key;dialog=QDialog(self);dialog.setWindowTitle('Audioregel · '+title);dialog.resize(580,350);form=QFormLayout(dialog)
        volume=QSpinBox();volume.setRange(0,100);volume.setSuffix(' %');volume.setValue(old.get('volume',min(100,live.get('percent',100))));form.addRow('Lautstärke',volume)
        output=QComboBox();output.addItem('Aktuelle Ausgabe beibehalten','')
        for sink in self.data['sinks'] if self.data else []:output.addItem(sink.get('description',sink['name']),sink['name'])
        target=old['sink'] if 'sink' in old else next((s['name'] for s in self.data['sinks'] if s['index']==live.get('sink')),'') if self.data else ''
        if target and output.findData(target)<0:output.addItem('Nicht verbunden · '+target,target)
        output.setCurrentIndex(max(0,output.findData(target)));form.addRow('Ausgabegerät',output)
        mute=QCheckBox('Stumm starten');mute.setChecked(old.get('mute',live.get('mute',False)));form.addRow(mute)
        role=QComboBox()
        for name,value in [('Keine besondere Rolle','none'),('Musik – während Gesprächen absenken','music'),('Gespräch – löst Absenkung aus','call')]:role.addItem(name,value)
        role.setCurrentIndex(role.findData(old.get('role','none')));form.addRow('Rolle',role)
        form.addRow(label('Gilt für alle Wiedergaben dieser App. Regeln werden erst nach Aktivierung der Automatik angewandt.','muted'))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec_()!=QDialog.Accepted:return
        values=(key,title,volume.value(),output.currentData(),mute.isChecked(),role.currentData())
        self.work('App-Regel speichern …',lambda _:sound.save_rule(self.library,*values),lambda _:self.load_rules())

    def remove_rule(self):
        item=self.rules.currentItem()
        if item:
            key=item.data(0,Qt.UserRole)
            self.work('Regel entfernen …',lambda _:sound.remove_rule(self.library,key),lambda _:self.load_rules())

    def save_duck(self):
        config=sound.settings(self.library);self.library.update(config['id'],duck=self.duck.isChecked(),level=self.level.value());self.status.setText('Gesprächsabsenkung gespeichert. Sie gilt bei aktiver Automatik.')

    def set_mode(self):
        mode=self.autostart.currentData()
        self.work('Automatik übernehmen …',lambda _:sound.service(self.library,mode),lambda _:self.load_rules())

    def closeEvent(self,event):
        self.closing=True;self.timer.stop()
        if self.poller:event.ignore();return
        super().closeEvent(event)
        if not event.isAccepted():self.closing=False;self.timer.start()
