from types import SimpleNamespace
import importlib.util
import unittest
from unittest.mock import patch
import inbox_data

class RepeatingEventTest(unittest.TestCase):
    def values(self):return dict(title='Listening',start='2026-10-03T09:00:00+02:00',end='2026-10-03T09:30:00+02:00',description='lumen://object/'+'a'*32,repeat='weekly',repeat_count=12,timezone='Europe/Zurich')
    @unittest.skipUnless(importlib.util.find_spec('icalendar'),'Requires existing Inbox calendar runtime')
    def test_serialized_series_keeps_wall_clock_across_daylight_change(self):
        from icalendar import Calendar
        import recurring_ical_events
        bodies=[]
        class Client:
            def calendar(self,**kwargs):return SimpleNamespace(url='https://calendar.invalid/events/')
            def request(self,url,method,body,headers):
                bodies.append((body,headers));return SimpleNamespace(status=201)
            def close(self):pass
        with patch('inbox_data.calendar_client',return_value=Client()):
            inbox_data.calendar_operation(dict(kind='caldav',calendar='https://calendar.invalid/events/'),'save',self.values())
        self.assertEqual(bodies[0][1]['If-None-Match'],'*')
        body=Calendar.from_ical(bodies[0][0]);events=recurring_ical_events.of(body).between('20261001','20261231')
        self.assertEqual(len(events),12)
        self.assertEqual({e.decoded('dtstart').hour for e in events},{9})
        self.assertEqual(len({e.decoded('dtstart').utcoffset() for e in events}),2)
        self.assertIn('lumen://object/',str(events[0]['description']))
if __name__=='__main__':unittest.main()
