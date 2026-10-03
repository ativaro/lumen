#!/usr/bin/python3
"""Exercise routing and ducking in a private PipeWire server with silent streams."""
import json,os,signal,subprocess,sys,tempfile,time,wave
from pathlib import Path
repo=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(repo/'files'))
from tools_data import Library
import sound_data as sound


def wait_for(predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            result=predicate()
            if result:return result
        except (OSError,subprocess.SubprocessError,ValueError):pass
        time.sleep(.1)
    raise AssertionError('Private audio session did not reach expected state')


with tempfile.TemporaryDirectory(prefix='lumen-sound-test-') as tmp:
    root=Path(tmp);runtime=root/'run';runtime.mkdir(mode=0o700);processes=[];logs=[]
    for key in list(os.environ):
        if key.startswith(('PIPEWIRE_','PULSE_','LUMEN_')) or key in ('DISPLAY','WAYLAND_DISPLAY'):os.environ.pop(key)
    os.environ.update(HOME=tmp,XDG_RUNTIME_DIR=str(runtime),PIPEWIRE_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),PULSE_RUNTIME_PATH=str(runtime/'pulse'),PULSE_SERVER='unix:'+str(runtime/'pulse/native'),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'no-bus'))
    def start(args):
        log=tempfile.TemporaryFile();logs.append(log);proc=subprocess.Popen(args,stdout=log,stderr=log,start_new_session=True);processes.append(proc);return proc
    try:
        start(['pipewire']);wait_for(lambda:(runtime/'pipewire-0').exists());start(['pipewire-pulse']);wait_for(lambda:sound.snapshot())
        # The policy-only profile links our virtual streams, without hardware monitors.
        start(['dbus-run-session','--','wireplumber','--profile','policy'])
        sound.run(['pactl','load-module','module-null-sink','sink_name=lumen_test_speakers','sink_properties=device.description=Lumen-Test-Speakers'])
        sound.run(['pactl','load-module','module-null-sink','sink_name=lumen_test_headset','sink_properties=device.description=Lumen-Test-Headset'])
        file=root/'silence.wav'
        with wave.open(str(file),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0'*(8000*4*180))
        music=start(['paplay','--device=lumen_test_speakers','--property=application.id=lumen.test.music','--property=application.name=Test-Music',str(file)])
        def stream():return next((s for s in sound.snapshot()['streams'] if s['app']=='application.id:lumen.test.music'),None)
        current=wait_for(stream);library=Library('sound');config=sound.settings(library)
        sound.change(library,current['token'],'volume',70);wait_for(lambda:stream()['percent']==70)
        sound.change(library,current['token'],'sink','lumen_test_headset')
        wait_for(lambda:next(s['name'] for s in sound.snapshot()['sinks'] if s['index']==stream()['sink'])=='lumen_test_headset')
        sound.change(library,current['token'],'mute',True);assert stream()['mute'];sound.change(library,current['token'],'mute',False)
        sound.save_rule(library,current['app'],'Test music',80,'lumen_test_speakers',False,'music')
        sound.save_rule(library,'application.id:lumen.test.call','Test call',50,'lumen_test_headset',False,'call')
        library.update(config['id'],mode='session',duck=True,level=25);sound.cycle(library);baseline=stream()['levels']
        call=start(['paplay','--device=lumen_test_headset','--property=application.id=lumen.test.call','--property=media.role=phone',str(file)])
        wait_for(lambda:len(sound.snapshot()['streams'])==2);sound.cycle(library)
        expected=[round(v*.25) for v in baseline];wait_for(lambda:stream()['levels']==expected)
        # Stop/restart recovery never needs a real microphone or hardware sink.
        sound.cycle(library,stop=True);assert stream()['levels']==baseline
        worker=start([sys.executable,str(repo/'files/sound_data.py'),'--run']);wait_for(lambda:stream()['levels']==expected)
        worker.terminate();worker.wait(timeout=15);wait_for(lambda:stream()['levels']==baseline)
        sound.cycle(library);sound.change(library,current['token'],'volume',33);sound.cycle(library);assert stream()['percent']==33
        call.terminate();call.wait(timeout=5);wait_for(lambda:len(sound.snapshot()['streams'])==1);sound.cycle(library);assert stream()['percent']==33
        print('Private PipeWire: routing, mute, rules, ducking, recovery and manual override passed')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
