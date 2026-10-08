.pragma library
// One presenter for all Lumen panels in this Plasma process.
var hosts = [];
function join(host) { hosts.push(host); hosts[0].primary = true; }
function leave(host) {
    hosts = hosts.filter(value => value !== host);
    if (hosts.length) hosts[0].primary = true;
}
