import unittest
from notes_structure import targets, anchor_position, split_target


class StructureTest(unittest.TestCase):
    def test_heading_alias_slug_unicode_and_code(self):
        text='---\ntags: [a]\n---\n# Main\n\n## Grüße **Welt** 🌍\nText\n```md\n# Not a heading\n```\n'
        self.assertEqual([value['title'] for value in targets(text)],['Main','Grüße Welt 🌍'])
        self.assertEqual(anchor_position(text,'grüße-welt'),text.index('## Grüße'))
        self.assertIsNone(anchor_position(text,'Not a heading'))
        self.assertEqual(split_target('Plan%23draft.md#Gr%C3%BC%C3%9Fe|Alias'),('Plan%23draft.md','Grüße'))

    def test_inline_and_standalone_blocks_and_duplicates(self):
        text='# Main\n\nA paragraph 🌍 ^first\n\nNext paragraph\ncontinued\n\n^second\n'
        self.assertEqual(anchor_position(text,'^first'),text.index('A paragraph'))
        self.assertEqual(anchor_position(text,'^second'),text.index('Next paragraph'))
        self.assertIsNone(anchor_position(text+'\nDuplicate ^first','^first'))

    def test_setext_and_fenced_blocks(self):
        text='Title\n=====\n\n~~~\nFake ^hidden\n~~~\n\nSub\n---\n'
        self.assertEqual([value['title'] for value in targets(text)],['Title','Sub'])
        self.assertIsNone(anchor_position(text,'^hidden'))

    def test_document_title_never_comes_from_code_or_yaml(self):
        from notes_structure import document_parts
        from wissen_data import parse
        for text in ['---\n# YAML comment\ntags: [x]\n---\nBody', '```markdown\n# Example only\n```\nBody']:
            note=parse('Original.md',text.encode())
            self.assertEqual(note['title'],'Original')
            prefix,title,separator,body,heading=document_parts(text,note['title'])
            self.assertFalse(heading);self.assertEqual(prefix+body,text)
        text='```\n# Fake\n```\n# Real\n\nBody'
        prefix,title,separator,body,heading=document_parts(text,'fallback')
        self.assertTrue(heading);self.assertEqual(title,'Real')
        self.assertEqual(prefix+'# '+title+separator+body,text)

    def test_frontmatter_separator_without_title_is_preserved(self):
        from notes_structure import document_parts
        prefix='---\ncategory: projekt\n---\n\n'
        parts=document_parts(prefix+'Body','Original')
        self.assertEqual(parts,(prefix,'Original','\n\n','Body',False))
