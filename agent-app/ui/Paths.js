// Paths.js — resolves repository/install locations for the Lumen app.
// Works from a source checkout AND from a system install (/usr/share/...).
.pragma library

// Resolve relative to this file:  <root>/agent-app/ui/  →  <root>/bin
var ui       = Qt.resolvedUrl(".")
var agentApp = Qt.resolvedUrl("..")
var root     = Qt.resolvedUrl("../..")
var bin      = Qt.resolvedUrl("../../bin")

function stripScheme(url) {
    return ("" + url).replace(/^file:\/\//, "");
}

// The launcher may pass "--bindir <dir>" (used for a system install where the
// QML lives in /usr/share but the helper scripts live in /usr/bin).
function findBindir() {
    var args = Qt.application.arguments || [];
    for (var i = 0; i < args.length; i++) {
        if (args[i] === "--bindir" && i + 1 < args.length) {
            return args[i + 1];
        }
    }
    return stripScheme(bin);
}

var binDir = findBindir();
