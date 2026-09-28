// Paths.js — resolves repository locations relative to this file.
// Works no matter where the repo/install dir lives (no hardcoded absolute paths).
.pragma library

// this file lives in  <root>/agent-app/ui/
var ui      = Qt.resolvedUrl(".")
var agentApp = Qt.resolvedUrl("..")          // <root>/agent-app
var root    = Qt.resolvedUrl("../..")        // <root>
var bin     = Qt.resolvedUrl("../../bin")    // <root>/bin
var workdir = Qt.resolvedUrl("../../")       // fallback, overridden by HOME below

// Convenience: strip the "file://" scheme for shell usage.
function p(url) {
    return ("" + url).replace(/^file:\/\//, "");
}

var binDir = p(bin);
