import unittest
from code_conditions import evaluate, validate, generated

class Conditions(unittest.TestCase):
    def test_typed_groups_and_missing_values(self):
        a={'field':'subject','op':'contains','value':'Rechnung'}
        b={'field':'has_attachment','op':'equals','value':True}
        self.assertTrue(evaluate({'all':[a,b]}, {'subject':'RECHNUNG Oktober','has_attachment':True}))
        self.assertFalse(evaluate({'all':[a,b]}, {'subject':'Rechnung'}))
        self.assertTrue(evaluate({'not':a},{'subject':'Termin'}))
        self.assertFalse(evaluate({'field':'size','op':'greater','value':10},{'size':'500'}))
        self.assertFalse(evaluate(b,{'has_attachment':1}))

    def test_no_unavailable_or_executable_conditions(self):
        for condition in ({'field':'matched','op':'equals','value':True},{'python':'open("secret")'},
                          {'field':'size','op':'greater','value':float('nan')}):
            with self.assertRaises(ValueError): validate(condition, {'text','size'})
        with self.assertRaises(ValueError): generated('{"condition":{"field":"matched","op":"equals","value":true},"explanation":"x"}',{'text'})

if __name__=='__main__':unittest.main()
