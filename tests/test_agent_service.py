"""Exercise the real D-Bus methods without a system bus or privileged processes."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


class AgentServiceTests(unittest.TestCase):
    def setUp(self):
        dbus = ModuleType('dbus')
        dbus.service = ModuleType('dbus.service')
        dbus.service.Object = object
        dbus.service.method = lambda *_a, **_k: lambda method: method
        dbus.DBusException = type('DBusException', (Exception,), {})
        dbus.SystemBus = Mock()
        self.manager = Mock()
        dbus.Interface = Mock(return_value=self.manager)
        mainloop = ModuleType('dbus.mainloop')
        mainloop.glib = ModuleType('dbus.mainloop.glib')
        gi = ModuleType('gi'); gi.repository = ModuleType('gi.repository')
        gi.repository.GLib = Mock()
        modules = {'dbus': dbus, 'dbus.service': dbus.service, 'dbus.mainloop': mainloop,
                   'dbus.mainloop.glib': mainloop.glib, 'gi': gi, 'gi.repository': gi.repository}
        spec = importlib.util.spec_from_file_location('test_agentd', Path(__file__).parents[1] / 'system/lumen-agentd.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.module)
        self.service = self.module.AgentService.__new__(self.module.AgentService)
        self.service._watch_requested_at = None

    def test_burst_coalesces_without_spawning_processes(self):
        with patch.object(self.module.time, 'monotonic', return_value=1), patch.object(self.module.subprocess, 'Popen') as spawn:
            self.assertTrue(all(self.service.RefreshWatch() for _ in range(100)))
        self.manager.StartUnit.assert_called_once_with('lumen-watch.service', 'replace')
        self.assertEqual(spawn.call_count, 0)

    def test_later_refresh_uses_the_same_system_unit(self):
        with patch.object(self.module.time, 'monotonic', side_effect=[1, 12]):
            self.assertTrue(self.service.RefreshWatch()); self.assertTrue(self.service.RefreshWatch())
        self.assertEqual(self.manager.StartUnit.call_count, 2)
        self.assertTrue(all(c.args == ('lumen-watch.service', 'replace') for c in self.manager.StartUnit.call_args_list))

    def test_failure_does_not_suppress_retry(self):
        self.manager.StartUnit.side_effect = [self.module.dbus.DBusException(), '/job/1']
        with patch.object(self.module.time, 'monotonic', return_value=1):
            self.assertFalse(self.service.RefreshWatch()); self.assertTrue(self.service.RefreshWatch())
        self.assertEqual(self.manager.StartUnit.call_count, 2)


if __name__ == '__main__':
    unittest.main()
