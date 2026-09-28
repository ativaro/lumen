// Process backend for the opencode agent app.
//
// - run(cmd): one-shot; emits finished(cmd, rc, out, err)
// - stream(cmd, tag): runs cmd in the background into a temp file and emits
//   streamData(tag, text) as it grows, then streamDone(tag, rc).
//
// Uses org.kde.plasma.plasma5support (no PyQt needed).
import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: exec

    signal finished(string command, int exitCode, string stdout, string stderr)
    signal streamData(string tag, string text)
    signal streamDone(string tag, int exitCode)

    // currently running stream tag ("" = idle)
    property string busyTag: ""

    // tag -> { file, last, rc }
    property var _streams: ({})

    function run(command) {
        ds.connectSource(command);
    }

    function stream(command, tag) {
        var file = "/tmp/opencode-agent-" + tag + ".out";
        _streams[tag] = { file: file, last: "" };
        busyTag = tag;
        // launch in background; append exit code sentinel
        var wrapped = "bash -c " + shq(": > " + shq(file) + "; ( " + command + " ) >> " + shq(file) + " 2>&1; echo \"__EXIT__$?\" >> " + shq(file)) ;
        launch.connectSource(wrapped);
        // small delay before polling starts
        starter.interval = 300;
        starter.tag = tag;
        starter.restart();
    }

    function _poll(tag) {
        var st = _streams[tag];
        if (!st) return;
        poller.tag = tag;
        poller.connectSource("cat " + shq(st.file) + " 2>/dev/null; true");
    }

    function shq(s) {
        // single-quote shell escaping
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    // one-shot command runner
    P5Support.DataSource {
        id: ds
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            var out = data["stdout"] || "";
            var err = data["stderr"] || "";
            var code = data["exit code"] !== undefined ? data["exit code"] : 0;
            disconnectSource(source);
            exec.finished(source, code, out, err);
        }
    }

    // background launcher (fire and forget)
    P5Support.DataSource {
        id: launch
        engine: "executable"
        connectedSources: []
        onNewData: (s, d) => disconnectSource(s)
    }

    // polling reader
    P5Support.DataSource {
        id: poller
        engine: "executable"
        property string tag: ""
        connectedSources: []
        onNewData: (s, d) => {
            var txt = d["stdout"] || "";
            var tag = poller.tag;
            var st = exec._streams[tag];
            disconnectSource(s);
            if (!st) return;

            var exitIdx = txt.indexOf("__EXIT__");
            if (exitIdx !== -1) {
                var body = txt.substring(0, exitIdx);
                if (body.length > st.last.length) {
                    exec.streamData(tag, body.substring(st.last.length));
                }
                var tail = txt.substring(exitIdx);
                var m = tail.match(/__EXIT__(\d+)/);
                var rc = m ? parseInt(m[1]) : 0;
                delete exec._streams[tag];
                if (exec.busyTag === tag) exec.busyTag = "";
                exec.streamDone(tag, rc);
                return;
            }

            if (txt.length > st.last.length) {
                exec.streamData(tag, txt.substring(st.last.length));
                st.last = txt;
            }
            // keep polling
            pollTimer.interval = 500;
            pollTimer.tag = tag;
            pollTimer.restart();
        }
    }

    Timer {
        id: starter
        property string tag: ""
        interval: 300
        onTriggered: exec._poll(tag)
    }

    Timer {
        id: pollTimer
        property string tag: ""
        interval: 500
        repeat: false
        onTriggered: exec._poll(tag)
    }
}
