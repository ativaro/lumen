import tempfile
from pathlib import Path
import unittest
from code_project_setup import validate,prepare

class Job:
    def check(self):pass
    def command(self,args,**kwargs):self.args=args

class Setup(unittest.TestCase):
    def test_new_folder_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'new';value=dict(source='new',directory=str(target))
            self.assertEqual(prepare(value,Job()),str(target));self.assertTrue(target.is_dir())
            with self.assertRaises(ValueError):prepare(value,Job())
            self.assertFalse(list(Path(tmp).glob('.lumen-project-*')))
            link=Path(tmp)/'link';link.symlink_to(Path(tmp)/'missing')
            with self.assertRaises(ValueError):prepare(dict(source='new',directory=str(link)),Job())
            self.assertFalse((Path(tmp)/'missing').exists())

    def test_git_argv_and_source_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for url in ('file:///private/repo','ext::sh -c attack','--upload-pack=sh','https://u:password@example.test/repo'):
                with self.assertRaises(ValueError):validate(dict(source='repo',directory=tmp+'/new',url=url))
            job=Job();prepare(dict(source='repo',directory=tmp+'/new',url='git@example.test:team/repo.git',branch='feature/fix'),job)
            self.assertIn('--no-recurse-submodules',job.args);self.assertIn('--',job.args)
            self.assertEqual(job.args[-2],'git@example.test:team/repo.git')

if __name__=='__main__':unittest.main()
