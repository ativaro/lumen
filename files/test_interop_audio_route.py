import json
import unittest
from PySide6.QtCore import QProcessEnvironment
from interop_audio import playback_environment
from interop_audio_route import route, snapshot, strict_reason


class RoutingTest(unittest.TestCase):
    def state(self):
        return dict(server='PulseAudio (on PipeWire 1.6.9)', manager='0.5.18',
            sinks=[dict(name='usb-headset', description='USB Headset', properties={'device.bus':'usb'}, ports=[dict(name='analog-output-headphones', type='headphones')])])

    def test_strict_route_is_opt_in_and_applies_server_and_sdl_guards(self):
        prefs = route(self.state(), dict(sink='usb-headset', strict_routing=True))
        env = playback_environment(QProcessEnvironment(), 'reader', prefs)
        self.assertEqual(env.value('SDL_AUDIODRIVER'), 'pulseaudio')
        self.assertEqual(env.value('SDL_AUDIO_DEVICE_NAME'), 'USB Headset')
        self.assertEqual(env.value('PULSE_SINK'), 'usb-headset')
        for key in ('node.dont-fallback', 'node.dont-reconnect', 'node.dont-move'):
            self.assertEqual(env.value('PULSE_PROP_'+key), 'true')
        env = playback_environment(QProcessEnvironment(), 'reader', dict(prefs, strict_routing=False))
        self.assertFalse(env.contains('PULSE_PROP_node.dont-fallback'))

    def test_unverified_stack_analog_switch_missing_and_ambiguous_target_fail_closed(self):
        state = self.state()
        prefs = dict(sink='usb-headset', strict_routing=True)
        for changes in (dict(server='pulseaudio 17'), dict(manager=''), dict(server='PulseAudio (on PipeWire 1.7.0)')):
            with self.assertRaises(ValueError): route(dict(state, **changes), prefs)
        self.assertEqual(route(dict(state, server='pulseaudio 17'), dict(prefs, strict_routing=False))['sink_description'], 'USB Headset')
        for sink in (dict(state['sinks'][0], properties={'device.bus':'pci'}), dict(state['sinks'][0], ports=[dict(name='analog-output-speaker')])):
            self.assertTrue(strict_reason(state, sink))
        with self.assertRaises(ValueError): route(dict(state, sinks=[]), prefs)
        other = dict(state['sinks'][0], name='other-device')
        with self.assertRaises(ValueError): route(dict(state, sinks=state['sinks']+[other]), prefs)

    def test_preflight_only_reads_server_sinks_and_manager_metadata(self):
        state = self.state()
        calls = []
        class Job:
            def command(self, args, **kwargs):
                calls.append(args)
                if args[-1]=='info': return json.dumps(dict(server_name=state['server'])).encode()
                if args[-1]=='sinks': return json.dumps(state['sinks']).encode()
                return json.dumps([dict(type='PipeWire:Interface:Client',info=dict(props={'application.name':'WirePlumber','application.version':'0.5.18'}))]).encode()
        self.assertEqual(snapshot(Job()), state)
        self.assertEqual(calls, [['pactl','-f','json','info'],['pactl','-f','json','list','sinks'],['pw-dump']])


if __name__ == '__main__': unittest.main()
