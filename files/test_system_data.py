"""Counter semantics, availability and privacy of System measurements."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from system_data import Sampler, History, cpu_usage, process_stat, add_gpu_sensors


class SystemDataTest(unittest.TestCase):
    def test_cpu_excludes_double_counted_guest_and_handles_reset(self):
        self.assertEqual(cpu_usage([10,0,0,90,0,0,0,0,5], [20,0,0,100,0,0,0,0,10]),50)
        self.assertIsNone(cpu_usage(None, [1]*8))
        self.assertIsNone(cpu_usage([20]*8, [10]*8))
        self.assertIsNone(cpu_usage([1]*8, [1]*8))

    def stat(self, pid=12, start=100, ticks=10, name='worker (one)'):
        fields=['S']+['0']*21
        fields[11]=str(ticks); fields[12]='0'; fields[19]=str(start); fields[21]='32'
        return f'{pid} ({name}) '+ ' '.join(fields)

    def test_process_parentheses_and_pid_reuse(self):
        self.assertEqual(process_stat(self.stat())['name'],'worker (one)')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'12').mkdir(); (root/'12/stat').write_text(self.stat())
            sampler=Sampler(root,root)
            with patch('system_data.time.monotonic', side_effect=[1,3,5]):
                first=sampler.sample(); self.assertIsNone(first['processes'][0]['cpu'])
                (root/'12/stat').write_text(self.stat(ticks=10+sampler.hz))
                second=sampler.sample(); self.assertEqual(second['processes'][0]['cpu'],50)
                (root/'12/stat').write_text(self.stat(start=999,ticks=200))
                third=sampler.sample(); self.assertIsNone(third['processes'][0]['cpu'])
            sampler=Sampler(root,root,uid=os.getuid()+1)
            self.assertEqual(sampler.sample()['processes'],[])
            self.assertNotIn('argv',str(first)); self.assertNotIn('environ',str(first))

    def test_memory_and_network_delta_reset_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'net').mkdir()
            (root/'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 300 kB\n')
            def net(receive,send):
                (root/'net/dev').write_text('header\nheader\neth0: '+str(receive)+' 0 0 0 0 0 0 0 '+str(send)+'\nlo: 999999 0 0 0 0 0 0 0 99999\n')
            sampler=Sampler(root,root); net(100,100)
            with patch('system_data.time.monotonic',side_effect=[1,3,5]):
                self.assertIsNone(sampler.sample()['network']); net(500,300)
                second=sampler.sample(); self.assertEqual(second['network'],dict(receive=200,send=100))
                self.assertEqual(second['memory']['percent'],70)
                net(1,1); (root/'meminfo').unlink()
                third=sampler.sample(); self.assertIsNone(third['network']); self.assertIsNone(third['memory']['percent'])

    def test_history_is_bounded_and_events_are_crossings(self):
        history=History()
        def point(at,cpu):return dict(measured=at,cpu=cpu,memory=dict(percent=10),network=None,gpus=[])
        for at,cpu in [(1,10),(3,90),(5,95),(7,None),(9,95)]:history.append(point(at,cpu))
        self.assertEqual(len(history.events),1); self.assertEqual(history.events[0]['time'],3)
        for at in range(11,8000,2):history.append(point(at,10))
        self.assertLessEqual(len(history.points),1801); self.assertFalse(history.events)
        self.assertLessEqual(len(history.series(60)),31)

    def test_stale_gpu_reading_is_not_live(self):
        from lumen_i18n import tr
        import time
        row=dict(name=tr('Auslastung'),unit='%',device='NVIDIA',value=42)
        sample=dict(gpus=[dict(name='card0',usage=0)],hardware=dict(measured=0,sensors=[row]))
        add_gpu_sensors(sample); self.assertEqual(len(sample['gpus']),1)
        sample['hardware']['measured']=time.time(); add_gpu_sensors(sample)
        self.assertEqual(sample['gpus'][0]['usage'],42)

    def test_mcp_is_readonly_and_uses_shared_measurements(self):
        from lumen_mcp_tools import invoke, DEFINITIONS
        self.assertTrue(DEFINITIONS['lumen_system_snapshot']['annotations']['readOnlyHint'])
        with patch('system_data.snapshot',return_value={'cpu':12}) as snapshot:
            self.assertEqual(invoke('lumen_system_snapshot',{}),{'cpu':12}); snapshot.assert_called_once()

if __name__=='__main__': unittest.main()
