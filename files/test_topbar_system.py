import json
import contextlib
import io
import sys
import unittest
from unittest.mock import patch

import topbar_system as system


class SystemTest(unittest.TestCase):
    def test_nmcli_escaping_keeps_network_names_and_ipv6_intact(self):
        self.assertEqual(system.fields(r'a\:b:c\\d:2001\:db8\:\:1:'), ['a:b', 'c\\d', '2001:db8::1', ''])

    def test_network_snapshot_preserves_profiles_and_partial_failure(self):
        replies = dict(general=('connected:full', ''), radio=('enabled', ''),
                       devices=('GENERAL.DEVICE:eth0\nGENERAL.TYPE:ethernet\nGENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Home\nIP6.ADDRESS[1]:2001\\:db8\\:\\:1/64', ''),
                       profiles=(r'Office\: secure:00000000-0000-0000-0000-000000000001:wireguard:wg0:yes', ''),
                       networks=('', 'Nicht verfügbar'))
        with patch.object(system, '_parallel', return_value=replies):
            result = system.network_snapshot()
        self.assertTrue(result['available'])
        self.assertEqual(result['profiles'][0]['name'], 'Office: secure')
        self.assertEqual(result['devices'][0]['details'][-1], dict(label='IPv6', value='2001:db8::1/64'))
        self.assertEqual(result['errors'], [dict(area='networks', message='Nicht verfügbar')])

    def test_missing_system_services_are_explicit(self):
        with patch.object(system, 'run', side_effect=FileNotFoundError):
            self.assertFalse(system.network_snapshot()['available'])
            audio = system.audio_snapshot()
        self.assertFalse(audio['available'])
        self.assertFalse(audio['bluetooth']['available'])
        self.assertEqual(audio['outputs'], [])

    def test_audio_snapshot_excludes_monitor_sources_and_reports_stream_routing(self):
        device = dict(index=7, name='usb-speaker', description='USB speaker', volume={'front-left': {'value': 32768}}, mute=False, ports=[], state='RUNNING')
        replies = {k: (json.dumps(v), '') for k, v in dict(sinks=[device], sources=[dict(device, monitor_of_sink=7), dict(device, index=8, name='usb-mic', monitor_of_sink=None)],
                   **{'sink-inputs': [dict(device, index=12, sink=7, properties={'application.name': 'Audio Studio'})], 'source-outputs': [], 'cards': []},
                   info={'default_sink_name': 'usb-speaker', 'default_source_name': 'usb-mic', 'server_name': 'PipeWire'}).items()}
        with patch.object(system, '_parallel', return_value=replies), patch.object(system, '_bluez', return_value={}):
            result = system.audio_snapshot()
        self.assertEqual(result['outputs'][0]['volume'], 50)
        self.assertTrue(result['outputs'][0]['default'])
        self.assertEqual([d['id'] for d in result['inputs']], ['8'])
        self.assertEqual(result['playback'][0]['device'], '7')

    def test_actions_only_accept_live_targets_and_bounded_values(self):
        current = dict(outputs=[dict(id='7', volume=50)], inputs=[], playback=[dict(id='12', volume=50)])
        with patch.object(system, 'snapshot', return_value=current), patch.object(system, 'run') as run:
            for request in [dict(action='volume:output', target='7', value=101), dict(action='volume:output', target='7', value=True),
                            dict(action='mute:output', target='7; touch /tmp/test'), dict(action='other', target='7'),
                            dict(action='mute:output', target='7', password='never accepted')]:
                with self.assertRaises(ValueError):
                    system.act('audio', request)
            run.assert_not_called()
            system.act('audio', dict(action='volume:output', target='7', value=42))
            run.assert_called_once_with(['pactl', 'set-sink-volume', '7', '42%'])

    def test_app_routing_resolves_both_stream_and_destination(self):
        current = dict(playback=[dict(id='12')], outputs=[dict(id='7')])
        with patch.object(system, 'snapshot', return_value=current), patch.object(system, 'run') as run:
            with self.assertRaises(ValueError):
                system.act('audio', dict(action='route:playback', target='12', value=99))
            run.assert_not_called()
            system.act('audio', dict(action='route:playback', target='12', value=7))
            run.assert_called_once_with(['pactl', 'move-sink-input', '12', '7'])

    def test_network_connect_never_writes_secrets_or_interpolates_a_shell(self):
        current = dict(profiles=[dict(id='00000000-0000-0000-0000-000000000001')])
        with patch.object(system, 'snapshot', return_value=current), patch.object(system, 'nm') as nm:
            system.act('network', dict(action='connect', target=current['profiles'][0]['id']))
            nm.assert_called_once_with('connection', 'up', 'uuid', current['profiles'][0]['id'])

    def test_device_disappears_between_open_and_action(self):
        with patch.object(system, 'snapshot', return_value=dict(inputs=[])), patch.object(system, 'run') as run:
            with self.assertRaises(ValueError):
                system.act('audio', dict(action='mute:input', target='8'))
            run.assert_not_called()

    def test_bluetooth_only_lists_audio_devices_and_keeps_battery_state(self):
        variant=lambda value: dict(data=value)
        objects={'/org/bluez/hci0': {'org.bluez.Adapter1': {'Alias': variant('Radio'), 'Powered': variant(True)}},
                 '/org/bluez/hci0/dev_audio': {'org.bluez.Device1': {'Address': variant('00:00:00:00:00:02'), 'Alias': variant('Headset'), 'Icon': variant('audio-headset'), 'Connected': variant(True)}, 'org.bluez.Battery1': {'Percentage': variant(82)}},
                 '/org/bluez/hci0/dev_keyboard': {'org.bluez.Device1': {'Address': variant('00:00:00:00:00:03'), 'Icon': variant('input-keyboard')}}}
        with patch.object(system, 'run', return_value=json.dumps(dict(data=[objects]))):
            result=system._bluez()
        self.assertTrue(result['available'])
        self.assertEqual([d['name'] for d in result['devices']], ['Headset'])
        self.assertEqual(result['devices'][0]['battery'], 82)

    def test_real_helper_protocol_uses_stdin_and_returns_topic_data(self):
        import lumen_panel
        from types import SimpleNamespace
        output=io.StringIO()
        payload=dict(action='mute:input',target='9',value=0)
        with patch.object(sys,'argv',['lumen-panel','--system-topic','audio','--system-action']), \
             patch.object(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))), \
             patch.object(system,'act',return_value=dict(available=True)) as act,contextlib.redirect_stdout(output):
            lumen_panel.main()
        act.assert_called_once_with('audio',payload)
        self.assertEqual(json.loads(output.getvalue())['details'],dict(available=True))

    def test_bad_helper_payload_is_reported_without_echoing_input(self):
        import lumen_panel
        from types import SimpleNamespace
        output=io.StringIO()
        with patch.object(sys,'argv',['lumen-panel','--system-topic','network','--system-action']), \
             patch.object(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(b'private invalid input'))),contextlib.redirect_stdout(output):
            lumen_panel.main()
        result=json.loads(output.getvalue())
        self.assertTrue(result['error'])
        self.assertNotIn('private invalid input',output.getvalue())


if __name__ == '__main__':
    unittest.main()
