"""A conversation survives questions that select different server notes."""
import unittest
from assistant_backend import session_memory_changed, session_notes


class SessionMemoryTest(unittest.TestCase):
    def stamp(self, notes, account='a1', local=(True, 1, 'x')):
        return dict(local=list(local), account=account, notes=[dict(remote_id=i, revision=r) for i, r in notes])

    def test_other_notes_for_the_next_question_keep_the_conversation(self):
        saved = self.stamp([('n1', 3), ('n2', 1)])
        for following in ([], [('n3', 7)], [('n1', 3)], [('n2', 1), ('n4', 2)]):
            self.assertFalse(session_memory_changed(saved, self.stamp(following)), following)

    def test_changed_memory_starts_a_new_conversation(self):
        saved = self.stamp([('n1', 3)])
        self.assertTrue(session_memory_changed(saved, self.stamp([('n1', 4)])))
        self.assertTrue(session_memory_changed(saved, self.stamp([], account='a2')))
        self.assertTrue(session_memory_changed(saved, self.stamp([], local=(True, 2, 'x'))))
        self.assertTrue(session_memory_changed([True, 1, 'x'], self.stamp([])))  # stamp written by an older version

    def test_used_notes_accumulate_at_their_latest_revision(self):
        merged = session_notes(self.stamp([('n1', 3), ('n2', 1)]), self.stamp([('n2', 1), ('n3', 5)]))
        self.assertEqual({n['remote_id']: n['revision'] for n in merged}, {'n1': 3, 'n2': 1, 'n3': 5})
        self.assertTrue(session_memory_changed(dict(self.stamp([]), notes=merged), self.stamp([('n1', 9)])))


if __name__ == '__main__': unittest.main()
