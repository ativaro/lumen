import copy
import os
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from tools_data import Library
import sound_data as sound


class SoundTest(unittest.TestCase):
    def test_rules_duck_restore_manual_override_disconnect_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            library=Library('sound',tmp);config=sound.settings(library)
            music=dict(index=1,token='epoch:1:1',app='music',title='Music',levels=[50000,25000],sink=10,mute=False,properties={})
            other=dict(index=3,token='epoch:3:3',app='music',title='Music',levels=[30000,15000],sink=10,mute=False,properties={})
            call=dict(index=2,token='epoch:2:2',app='call',corked=False,mute=False,source=20,properties={})
            state=dict(streams=[music,other],recordings=[],sinks=[dict(index=10,name='speakers'),dict(index=11,name='headset')],sources=[dict(index=20,name='mic',properties={})])
            commands=[]
            def command(args):
                commands.append(args)
                if args[1]=='set-sink-input-volume':next(v for v in state['streams'] if str(v['index'])==args[2])['levels']=list(map(int,args[3:]))
                elif args[1]=='move-sink-input':next(v for v in state['streams'] if str(v['index'])==args[2])['sink']=next(v['index'] for v in state['sinks'] if v['name']==args[3])
                return ''
            with patch('sound_data.snapshot',side_effect=lambda:copy.deepcopy(state)),patch('sound_data.run',side_effect=command):
                sound.cycle(library);self.assertEqual(commands,[])
                sound.save_rule(library,'music','Music',80,'speakers',False,'music');sound.save_rule(library,'call','Calls',100,'headset',False,'call')
                library.update(config['id'],mode='session',duck=True);sound.cycle(library)
                baseline=[list(s['levels']) for s in state['streams']];self.assertEqual(baseline[0],[52429,26214])
                state['recordings']=[call];sound.cycle(library)
                self.assertEqual(music['levels'],[round(v*.25) for v in baseline[0]])
                library.update(config['id'],level=50);sound.cycle(library);self.assertEqual(music['levels'],[round(v*.5) for v in baseline[0]])
                # Changing one app's rule must retain all other restore entries.
                other['app']='other';rules=sound.settings(library)['rules'];rules['other']=dict(rules['music'],title='Other');library.update(config['id'],rules=rules)
                sound.cycle(library);self.assertEqual(len(sound.settings(library)['ducked']),2)
                sound.change(library,music['token'],'volume',33);manual=music['levels'][:];sound.cycle(library);self.assertEqual(music['levels'],manual)
                state['recordings']=[];sound.cycle(library);self.assertEqual(music['levels'],manual);self.assertEqual(other['levels'],baseline[1])
                sound.change(library,music['token'],'sink','headset');self.assertEqual(music['sink'],11)
                state['sinks'].pop()
                with self.assertRaises(ValueError):sound.change(library,music['token'],'sink','headset')
                state['recordings']=[call];sound.cycle(library);self.assertTrue(sound.settings(library)['ducked'])
                old=music['levels'][:];music['token']='new-epoch:1:1';sound.cycle(library,stop=True);self.assertEqual(music['levels'],old)
                self.assertEqual(sound.settings(library)['ducked'],{})
                with self.assertRaises(ValueError):sound.change(library,'gone','mute',True)

    def test_channel_balance_limits_and_stable_application_key(self):
        self.assertEqual(sound.scaled([65536,32768],50),[32768,16384])
        self.assertEqual(sound.scaled([0,0],25),[16384,16384])
        self.assertEqual(sound.app_key({'application.id':'app.id','application.name':'Session name'}),'application.id:app.id')
        for value in [-1,101,'50',False]:
            with self.assertRaises(ValueError):sound.scaled([1],value)

    def test_failed_autostart_restores_disabled_mode(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'XDG_CONFIG_HOME':tmp}):
            library=Library('sound',tmp);calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if '--now' in args:raise subprocess.CalledProcessError(1,args)
                return ''
            with patch('sound_data.run',side_effect=run),patch('sound_data.cycle') as restore:
                with self.assertRaises(subprocess.CalledProcessError):sound.service(library,'login')
                self.assertEqual(sound.settings(library)['mode'],'off')
                self.assertIn(['systemctl','--user','disable','lumen-sound.service'],calls)
                self.assertIn(['systemctl','--user','stop','lumen-sound.service'],calls)
                restore.assert_called_once_with(library,stop=True)
                self.assertIn('ExecStart="'+sound.sys.executable+'" ', (Path(tmp)/'systemd/user/lumen-sound.service').read_text())


if __name__=='__main__':unittest.main()
