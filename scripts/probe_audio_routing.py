"""Optional live routing check: own PipeWire/WirePlumber, no hardware or audio.

Run with /usr/bin/python3 scripts/probe_audio_routing.py on the supported stack.
Uses packaged configuration, an isolated runtime and temporary silent sinks.
"""
import json, os, subprocess, tempfile, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'files'))

if '--sdl' in sys.argv:
    import ctypes, ctypes.util, sys
    sdl=ctypes.CDLL(ctypes.util.find_library('SDL2-2.0'))
    class Spec(ctypes.Structure):
        _fields_=[('freq',ctypes.c_int),('format',ctypes.c_uint16),('channels',ctypes.c_uint8),('silence',ctypes.c_uint8),('samples',ctypes.c_uint16),('padding',ctypes.c_uint16),('size',ctypes.c_uint32),('callback',ctypes.c_void_p),('userdata',ctypes.c_void_p)]
    sdl.SDL_GetError.restype=ctypes.c_char_p
    sdl.SDL_OpenAudioDevice.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.POINTER(Spec),ctypes.POINTER(Spec),ctypes.c_int]
    sdl.SDL_OpenAudioDevice.restype=ctypes.c_uint32
    assert sdl.SDL_Init(0x10)==0,sdl.SDL_GetError()
    desired=Spec(freq=48000,format=0x8010,channels=2,samples=1024)
    obtained=Spec()
    device=sdl.SDL_OpenAudioDevice(None,0,ctypes.byref(desired),ctypes.byref(obtained),0)
    assert device,sdl.SDL_GetError()
    assert sdl.SDL_GetAudioDeviceStatus(device)==2
    print('OPEN_PAUSED',flush=True)
    sys.stdin.read(1)
    sdl.SDL_CloseAudioDevice(device)
    sdl.SDL_Quit()
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix='lumen-routing-probe-') as directory:
    root=Path(directory)
    for name in ('run','config','data','state','cache','pw'):
        (root/name).mkdir(mode=0o700)
    for name in ('pipewire.conf','pipewire-pulse.conf','client.conf'):
        (root/'pw'/name).write_bytes((Path('/usr/share/pipewire')/name).read_bytes())
    env=dict(os.environ, XDG_RUNTIME_DIR=str(root/'run'), XDG_CONFIG_HOME=str(root/'config'),
             XDG_DATA_HOME=str(root/'data'), XDG_STATE_HOME=str(root/'state'), XDG_CACHE_HOME=str(root/'cache'),
             PIPEWIRE_CONFIG_DIR=str(root/'pw'), PIPEWIRE_REMOTE='pipewire-0', PIPEWIRE_RUNTIME_DIR=str(root/'run'), WIREPLUMBER_CONFIG_DIR='/usr/share/wireplumber',
             PULSE_SERVER='unix:'+str(root/'run/pulse/native'), DBUS_SESSION_BUS_ADDRESS='unix:path='+str(root/'run/no-bus'))
    logs=[]; processes=[]
    def start(args):
        log=tempfile.TemporaryFile(); logs.append((args[0],log))
        p=subprocess.Popen(args,env=env,stdout=log,stderr=log);processes.append(p);return p
    def run(args, check=True):
        p=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
        if check and p.returncode: raise RuntimeError(str(args)+': '+p.stderr)
        return p.stdout.strip()
    def pactl(*args): return run(['pactl',*args])
    def listing(name):return json.loads(pactl('-f','json','list',name))
    def until(fn):
        for _ in range(60):
            try:
                value=fn()
                if value:return value
            except (RuntimeError,FileNotFoundError,json.JSONDecodeError):pass
            time.sleep(.05)
        raise AssertionError('Timed out')
    try:
        start(['pipewire'])
        until(lambda:(root/'run/pipewire-0').exists())
        start(['pipewire-pulse'])
        start(['wireplumber','--profile=policy'])
        until(lambda:pactl('info'))
        devices=[x for x in json.loads(run(['pw-dump'])) if x['type']=='PipeWire:Interface:Device']
        assert not devices, 'Private test must have no real hardware'
        fallback=pactl('load-module','module-null-sink','sink_name=lumen_test_default',"sink_properties='device.description=LumenTestDefault priority.session=1000'")
        until(lambda:any(x['name']=='lumen_test_default' for x in listing('sinks')))
        before=pactl('get-default-sink')
        assert before=='lumen_test_default', before
        source=pactl('load-module','module-null-sink','sink_name=lumen_test_private',"sink_properties='device.description=LumenTestPrivate priority.session=-10000'")
        target=pactl('load-module','module-null-sink','sink_name=lumen_test_headphone',"sink_properties='device.description=LumenTestHeadphone priority.session=-10000'")
        loop=pactl('load-module','module-loopback','source=lumen_test_private.monitor','sink=lumen_test_headphone',
                   'source_dont_move=true','sink_dont_move=true',
                   "source_output_properties='node.dont-fallback=true node.dont-move=true'",
                   "sink_input_properties='node.dont-fallback=true node.dont-move=true'")
        rows=until(lambda:[x for x in listing('sink-inputs') if str(x.get('owner_module'))==loop and x['sink'] != 4294967295])
        target_id=next(x['index'] for x in listing('sinks') if x['name']=='lumen_test_headphone')
        assert rows[0]['sink']==target_id, rows
        print(json.dumps({'stage':'connected','hardware_devices':len(devices),'sink':rows[0]['sink'],'flags':{k:v for k,v in rows[0]['properties'].items() if k.startswith('node.dont')}}))
        pactl('unload-module',target)
        until(lambda:not [x for x in listing('sink-inputs') if str(x.get('owner_module'))==loop])
        time.sleep(.3)
        assert pactl('get-default-sink')==before
        assert not [x for x in listing('sink-inputs') if str(x.get('owner_module'))==loop]
        print(json.dumps({'stage':'target_removed','loopback_output_destroyed':True,'default_unchanged':True,'private_sink_survives':any(x['name']=='lumen_test_private' for x in listing('sinks'))}))
        # Initial missing target: strict loopback must not acquire fallback.
        missing=pactl('load-module','module-loopback','source=lumen_test_private.monitor','sink=lumen_test_absent',
                   'source_dont_move=true','sink_dont_move=true',
                   "source_output_properties='node.dont-fallback=true node.dont-move=true'",
                   "sink_input_properties='node.dont-fallback=true node.dont-move=true'")
        time.sleep(.3)
        inputs=[x for x in listing('sink-inputs') if str(x.get('owner_module'))==missing]
        sinks={x['index']:x['name'] for x in listing('sinks')}
        assert not any(sinks.get(x['sink'])=='lumen_test_default' for x in inputs),inputs
        print(json.dumps({'stage':'target_absent_at_start','no_fallback_link':True,'stream_count':len(inputs)}))
        target=pactl('load-module','module-null-sink','sink_name=lumen_test_sdl',"sink_properties='device.description=LumenTestSDL priority.session=-10000 device.bus=usb'")
        from interop_audio_route import route, snapshot
        from interop_audio import playback_environment
        from PySide6.QtCore import QProcessEnvironment
        class ReadJob:
            def command(self,args,**kwargs):return run(args).encode()
        state=snapshot(ReadJob())
        prefs=route(state,dict(sink='lumen_test_sdl',strict_routing=True))
        qenv=QProcessEnvironment()
        for key,value in env.items():qenv.insert(key,value)
        qenv=playback_environment(qenv,'reader',prefs)
        sdl_env={key:qenv.value(key) for key in qenv.keys()}
        print(json.dumps({'stage':'production_preflight','server':state['server'],'manager':state['manager']}))
        child=subprocess.Popen(['python3',str(Path(__file__).resolve()), '--sdl'],env=sdl_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        processes.append(child)
        assert child.stdout.readline().strip()=='OPEN_PAUSED'
        rows=until(lambda:[x for x in listing('sink-inputs') if x['properties'].get('application.id')=='org.lumen.reader' and x['sink']!=4294967295])
        print(json.dumps({'stage':'sdl_paused_connected','corked':rows[0]['corked'],'flags':{k:v for k,v in rows[0]['properties'].items() if k.startswith('node.dont')},'sink':rows[0]['sink']}))

        assert rows[0]['sink']==next(x['index'] for x in listing('sinks') if x['name']=='lumen_test_sdl')
        pactl('unload-module',target)
        time.sleep(.3)
        rows=[x for x in listing('sink-inputs') if x['properties'].get('application.id')=='org.lumen.reader']
        assert not rows,rows
        print(json.dumps({'stage':'sdl_target_removed','stream_destroyed':True,'default_unchanged':pactl('get-default-sink')==before}))
        child.communicate('x',timeout=2)
        absent=subprocess.run(['python3',str(Path(__file__).resolve()), '--sdl'],env=sdl_env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=3)
        assert absent.returncode and 'No such device' in absent.stderr,absent.stderr
        assert not [x for x in listing('sink-inputs') if x['properties'].get('application.id')=='org.lumen.reader']
        print(json.dumps({'stage':'sdl_absent_at_start','fails_without_fallback':True}))
        print('PROBE PASSED: isolated virtual devices only; no audio player, no host routing changes.')
    except BaseException:
        for name,log in logs:
            log.seek(0);print(name,log.read().decode(errors='replace')[-4000:])
        raise
    finally:
        for process in reversed(processes):process.terminate()
        for process in reversed(processes):
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for _,log in logs:log.close()
