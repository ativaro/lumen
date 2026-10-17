import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from code_project import inspect_project,source_text


class ProjectInspectionTest(unittest.TestCase):
    def test_inspection_is_scoped_and_does_not_run_repository_diff_programs(self):
        def command(args,**_):
            r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if r.returncode:raise ValueError('git unavailable')
            return r.stdout
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sub=root/'sub';sub.mkdir();(sub/'code.py').write_text('before\n');(root/'outside.py').write_text('outside\n')
            command(['git','init','-q',str(root)]);command(['git','-C',str(root),'add','.'])
            command(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@invalid','commit','-qm','initial'])
            (sub/'code.py').write_text('after\n');(root/'outside.py').write_text('private change\n')
            command(['git','-C',str(root),'config','diff.external','must-not-run'])
            value=inspect_project(sub,command)
            self.assertEqual(value['files'],['code.py']);self.assertIn('+after',value['diff']);self.assertNotIn('private change',value['diff'])
            self.assertEqual(source_text(sub,'code.py'),'after\n')
            (sub/'escape').symlink_to(root/'outside.py')
            for path in ('../outside.py',str(root/'outside.py'),'escape'):
                with self.assertRaises((ValueError,OSError)):source_text(sub,path)
            (sub/'pipe').write_bytes(b'\0binary')
            with self.assertRaises(ValueError):source_text(sub,'pipe')

    def test_new_repository_before_first_commit(self):
        def command(args,**_):
            r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if r.returncode:raise ValueError('git unavailable')
            return r.stdout
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);command(['git','init','-q',str(root)])
            (root/'new.txt').write_text('new project\n');command(['git','-C',str(root),'add','.'])
            value=inspect_project(root,command)
            self.assertTrue(value['git']);self.assertTrue(value['branch'])
            self.assertEqual(value['files'],['new.txt']);self.assertIn('+new project',value['diff'])


if __name__=='__main__':unittest.main()
