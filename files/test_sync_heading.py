import unittest
from wissen_sync import remote_text


class SyncHeadingTest(unittest.TestCase):
    def test_code_comments_are_preserved_before_actual_heading(self):
        prefix = '```sh\n# keep this comment\nprintf hello\n```\n\n'
        self.assertEqual(remote_text(dict(title='New title', body=prefix+'# Old title\n\nBody')),
                         prefix+'# New title\n\nBody')

    def test_front_matter_and_code_only_note_are_preserved(self):
        prefix = '---\ntags: [demo]\n---\n\n'
        body = '```sh\n# keep this comment\n```'
        self.assertEqual(remote_text(dict(title='Title', body=prefix+body)), prefix+'# Title\n\n'+body)
