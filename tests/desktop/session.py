from pathlib import Path
import json
import os
import subprocess
import time

root=Path('/profile');processes=[]
def start(command,name,env=None):
    process=subprocess.Popen(command,env=env,stdout=(root/(name+'.log')).open('w'),stderr=subprocess.STDOUT)
    processes.append(process);return process
try:
    kwin=start(['kwin_wayland','--virtual','--width',os.environ['LUMEN_QA_WIDTH'],'--height','800','--output-count','2',
                '--no-lockscreen','--no-global-shortcuts','--no-kactivities','--socket','wayland-test'],
               'kwin',dict(os.environ,QT_QPA_PLATFORM='offscreen'))
    for _ in range(80):
        if (root/'runtime/wayland-test').exists():break
        assert kwin.poll() is None,(root/'kwin.log').read_text()[-1200:]
        time.sleep(.1)
    os.environ['WAYLAND_DISPLAY']='wayland-test'
    outputs=sorted(json.loads(subprocess.check_output(['kscreen-doctor','-j'],text=True))['outputs'],key=lambda output:output['name'])
    logical=round(int(os.environ['LUMEN_QA_WIDTH'])/float(os.environ['LUMEN_QA_SCALE']))
    subprocess.run(['kscreen-doctor','output.'+str(outputs[0]['id'])+'.scale.'+os.environ['LUMEN_QA_SCALE'],'output.'+str(outputs[1]['id'])+'.scale.'+os.environ['LUMEN_QA_SCALE'],'output.'+str(outputs[0]['id'])+'.position.0,0',
                    'output.'+str(outputs[1]['id'])+'.position.'+str(logical)+',0'],check=True,capture_output=True)
    input_device=subprocess.Popen(['/build/topbar-input'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                  stderr=(root/'input.log').open('w'),text=True)
    processes.append(input_device)
    start(['/usr/lib/kactivitymanagerd'],'activities')
    start(['kded6'],'kded');time.sleep(1)
    subprocess.run(['qdbus6','org.kde.kded6','/kded','unloadModule','bluedevil'],capture_output=True,timeout=5)
    check=subprocess.run(['qdbus6','org.kde.kded6','/kded','loadModule','appmenu'],capture_output=True,timeout=5,text=True)
    (root/'module.json').write_text(json.dumps(dict(code=check.returncode,out=check.stdout,error=check.stderr)))
    start(['python3','/qa/view-marker.py'],'view-marker');time.sleep(.5)
    (root/'bus-names.txt').write_text(subprocess.check_output(['qdbus6'],text=True))
    start(['python3','/qa/tray-fixture.py'],'tray-fixture')
    fixture=start(['python3','/qa/fixture.py','A'],'fixture')
    time.sleep(1)
    script=root/'activate.js';script.write_text('const w=workspace.windowList().find(w=>w.caption==="Lumen Menütest A");if(w)workspace.activeWindow=w;')
    identity=subprocess.check_output(['qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script)],text=True).strip()
    subprocess.run(['qdbus6','org.kde.KWin','/Scripting/Script'+identity,'org.kde.kwin.Script.run'],check=True,capture_output=True)
    ui=start(['/build/topbar-ui-test'],'ui-test')
    result=ui.wait(timeout=40)
    assert result==0,(root/'ui-test.log').read_text()[-4000:]
    bar=start(['/build/lumen-topbar'],'topbar');time.sleep(2)
    (root/'smoke.json').write_text(json.dumps({'topbar_running':bar.poll() is None,'fixture_running':fixture.poll() is None}))
    assert bar.poll() is None,(root/'topbar.log').read_text()[-3000:]
    subprocess.run(['qdbus6','org.lumen.MenuTestA','/Control','command','maximize'],check=True,capture_output=True)
    time.sleep(.2)
    area_script=root/'area.js'
    area_script.write_text('const w=workspace.windowList().find(w=>w.caption==="Lumen Menütest A");if(w){const r=w.frameGeometry;callDBus("org.lumen.MenuTestA","/Control","","record",JSON.stringify({x:r.x,y:r.y,width:r.width,height:r.height}));}')
    script_id=subprocess.check_output(['qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(area_script)],text=True).strip()
    subprocess.run(['qdbus6','org.kde.KWin','/Scripting/Script'+script_id,'org.kde.kwin.Script.run'],check=True,capture_output=True)
    for attempt in range(30):
        if (root/'kwin-geometry.json').exists():break
        time.sleep(.1)
    area=json.loads((root/'kwin-geometry.json').read_text())
    (root/'work-area.json').write_text(json.dumps(area))
    assert area['y']=={'classic':56,'band':68,'deck':118,'context':60}[os.environ['LUMEN_QA_LAYOUT']] and area['width']==logical,area
    if not os.environ.get('LUMEN_QA_SURFACE_ONLY'):
        plasma=start(['plasmashell','--no-respawn'],'plasma');time.sleep(2)
        def evaluate(script):
            result=subprocess.run(['qdbus6','org.kde.plasmashell','/PlasmaShell','org.kde.PlasmaShell.evaluateScript',script],capture_output=True,text=True,timeout=10)
            assert result.returncode==0,(result.stdout,result.stderr)
            return result.stdout.strip()
        if os.environ.get('LUMEN_QA_HOT_HOST'):
            assert evaluate('print(knownWidgetTypes.indexOf("org.lumen.notificationhost"));')=='-1'
            result=subprocess.run(['kpackagetool6','--type','Plasma/Applet','--install','/profile/host-stage'],capture_output=True,text=True,timeout=15)
            (root/'hot-package.json').write_text(json.dumps(dict(code=result.returncode,out=result.stdout,error=result.stderr)))
            assert result.returncode==0,(result.stdout,result.stderr)
        setup=Path('/source/desktop/topbar.js').read_text()
        first=evaluate(setup+'\nprint(installLumenNotificationHost("qa-ready"));')
        second=evaluate(setup+'\nprint(installLumenNotificationHost());')
        assert first==second,(first,second)
        for attempt in range(50):
            if evaluate(setup+'\nprint(lumenNotificationHostReady("qa-ready"));')=='true':break
            time.sleep(.1)
        else:raise AssertionError('Notification host was not ready')
        subprocess.run(['notify-send','--app-name=LumenQA','Synthetic notification','Private test history'],check=True)
        time.sleep(1)
        snapshot=evaluate('print(JSON.stringify(desktops().reduce((all,d)=>all.concat(d.widgets()),[]).filter(w=>w.type==="org.lumen.notificationhost").map(w=>{w.currentConfigGroup=["General"];return {id:w.id,unread:w.readConfig("unread",-1)};})));')
        (root/'notification-host.json').write_text(snapshot)
        assert json.loads(snapshot)[0]['unread']>=1,snapshot
        panel_snapshot='print(JSON.stringify(panels().map(p=>({id:p.id,screen:p.screen,location:p.location,height:p.height,widgets:p.widgets().map(w=>w.type)}))));'
        original=json.loads(evaluate(panel_snapshot))
        layout=setup+'\nvar options={wallpaper:""};\n'+Path('/source/desktop/layout.js').read_text()
        evaluate(layout);evaluate(setup+"\nactivateLumenNotificationHost();");first_panels=json.loads(evaluate(panel_snapshot))
        evaluate(layout);second_panels=json.loads(evaluate(panel_snapshot))
        assert first_panels==second_panels,(first_panels,second_panels)
        assert all(row in second_panels for row in original if row['location']=='bottom')
        for screen in (0,1):
            assert any(row['screen']==screen and row['location']=='bottom' and 'org.kde.plasma.icontasks' in row['widgets'] for row in second_panels),second_panels
        (root/'layout.json').write_text(json.dumps(dict(idempotent=True,original_panels_preserved=True,panels=second_panels)))
        def popup_count():
            probe=root/'popups.js';answer=root/'kwin-geometry.json';answer.unlink(missing_ok=True)
            probe.write_text('callDBus("org.lumen.MenuTestA","/Control","","record",JSON.stringify({count:workspace.windowList().filter(w=>w.caption==="Lumen Notification").length}));')
            identity=subprocess.check_output(['qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(probe)],text=True).strip()
            subprocess.run(['qdbus6','org.kde.KWin','/Scripting/Script'+identity,'org.kde.kwin.Script.run'],check=True,capture_output=True)
            for attempt in range(30):
                if answer.exists():return json.loads(answer.read_text())['count']
                time.sleep(.05)
            raise AssertionError('No popup count from private compositor')
        time.sleep(1)
        subprocess.run(['notify-send','--app-name=LumenQA','After cutover','Exactly one Lumen popup'],check=True)
        time.sleep(.4);assert popup_count()==1,'Expected one native popup'
        def popups(enabled):
            subprocess.run(['python3','-c','import sys;sys.path.insert(0,"/source/files");from lumen_notifications import notification_options;notification_options({"native_popups":'+str(enabled)+'})'],check=True)
            time.sleep(5.2)
        popups(False)
        subprocess.run(['notify-send','--app-name=LumenQA','Popup disabled','Keep this in the center'],check=True)
        time.sleep(.3);assert popup_count()==0,'Disabled popups must not switch to another presenter'
        popups(True)
        assert popup_count()==0,"Re-enabling must not replay notifications received while disabled"
        subprocess.run(['notify-send','--app-name=LumenQA','Popup enabled again','Exactly one Lumen popup'],check=True)
        time.sleep(.4);assert popup_count()==1,'Expected one restored popup'
        (root/'popup-toggle.json').write_text(json.dumps(dict(enabled=1,disabled=0,reenabled=1)))
        subprocess.run(['python3','/source/files/lumen_notifications.py'],check=True,timeout=10)
        time.sleep(.5)
        assert plasma.poll() is None,(root/'plasma.log').read_text()[-2000:]
        (root/'notification-pass.json').write_text(json.dumps({'idempotent':True,'system_history_retained':True,'center_opened':True}))

finally:
    for process in reversed(processes):
        if process.poll() is None:process.terminate()
    for process in reversed(processes):
        try:process.wait(timeout=4)
        except subprocess.TimeoutExpired:process.kill();process.wait()
