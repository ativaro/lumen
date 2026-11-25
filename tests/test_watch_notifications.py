"""Run the actual watcher/notifier against synthetic commands and private reports."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class WatchNotificationTests(unittest.TestCase):
    def test_unchanged_findings_stay_quiet_but_changed_and_recurring_findings_notify(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);commands=base/'bin';commands.mkdir();state=base/'system';log=base/'calls'
            watcher=commands/'lumen-watch';watcher.write_text((ROOT/'system/lumen-watch').read_text().replace('STATE_DIR="/var/lib/lumen"','STATE_DIR="'+str(state)+'"'))
            notifier=commands/'lumen-notify';notifier.write_text((ROOT/'system/lumen-notify').read_text().replace('FINDINGS="/var/lib/lumen/findings.md"','FINDINGS="'+str(state/'findings.md')+'"'))
            scripts={
                'systemctl':'case "$*" in *--user*) exit 0;; esac\n[ -z "$LUMEN_TEST_FAILED" ] || printf "%s loaded failed failed Synthetic\\n" "$LUMEN_TEST_FAILED"',
                'df':'printf "Use%%\\n10%%\\n"',
                'date':'if [ "${1:-}" = +%s ]; then echo "$LUMEN_TEST_TIME"; else echo "time-$LUMEN_TEST_TIME"; fi',
                'notify-send':'echo notify >> "$LUMEN_TEST_LOG"',
                'lumen-run':'echo analysis >> "$LUMEN_TEST_LOG"\necho "Synthetic analysis"',
                'opencode':'exit 0', 'logger':'exit 0','journalctl':'exit 0','nvidia-smi':'exit 0',
            }
            for name,script in scripts.items():
                path=commands/name;path.write_text('#!/bin/bash\n'+script+'\n');path.chmod(0o755)
            env={'PATH':str(commands)+':/usr/bin:/bin','HOME':str(base),'LUMEN_STATE':str(base/'user'),
                 'LUMEN_OPENCODE_BIN':str(commands/'opencode'),'LUMEN_TEST_LOG':str(log),'LANG':'C.UTF-8'}
            def check(stamp,unit,notify=True):
                current={**env,'LUMEN_TEST_TIME':str(stamp),'LUMEN_TEST_FAILED':unit}
                subprocess.run(['bash',str(watcher)],env=current,check=True,capture_output=True,timeout=5)
                if notify:subprocess.run(['bash',str(notifier)],env=current,check=True,capture_output=True,timeout=5)
            check(1000,'alpha.service');original=(state/'findings.md').read_bytes()
            check(2000,'alpha.service')
            self.assertEqual((state/'findings.md').read_bytes(),original)
            self.assertTrue((state/'heartbeat').read_text().startswith('2000 '))
            self.assertEqual(log.read_text().splitlines(),['analysis','notify'])
            check(3000,'beta.service')
            self.assertEqual(log.read_text().splitlines(),['analysis','notify']*2)
            check(4000,'',notify=False)
            self.assertFalse((state/'findings.md').exists())
            check(5000,'beta.service')
            self.assertEqual(log.read_text().splitlines(),['analysis','notify']*3)
