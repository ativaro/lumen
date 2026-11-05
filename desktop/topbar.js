// System notification history stays in Plasma; the actual bar is an independent process.
function installLumenNotificationHost(token) {
    var hosts=[];
    desktops().forEach(function(d) { d.widgets().forEach(function(w) {
        if(w.type === "org.lumen.notificationhost") hosts.push(w);
    }); });
    if(hosts.length) {
        if(token){hosts[0].currentConfigGroup=["General"];hosts[0].writeConfig("ping",token);hosts[0].reloadConfig();}
        return hosts[0].id;
    }
    var desktop=desktops().find(function(d) {return d.screen===0;}) || desktops()[0];
    if(!desktop) throw Error("No desktop available");
    var host=desktop.addWidget("org.lumen.notificationhost");
    if(!host) throw Error("Lumen notification host could not be created");
    if(token){host.currentConfigGroup=["General"];host.writeConfig("ping",token);host.reloadConfig();}
    return host.id;
}
function removeLumenTopPanels() {
    var legacy=["org.lumen.agent","org.lumen.islands","org.lumen.system","org.lumen.search","org.lumen.control","org.lumen.appmenu","org.lumen.topbarcontext"];
    var ids=[];
    panels().filter(function(p) {return p.location==="top" && p.widgets().some(function(w) {return legacy.indexOf(w.type)>=0;});}).forEach(function(p){ids.push(p.id);p.remove();});
    return ids;
}

function lumenNotificationHostReady(token) {
    var ready=false;
    desktops().forEach(function(d){d.widgets().forEach(function(w){
        if(w.type!=="org.lumen.notificationhost")return;
        w.currentConfigGroup=["General"];
        if(w.readConfig("readyStamp","")===token)ready=true;
    });});
    return ready;
}

function activateLumenNotificationHost() {
    var chosen=false;
    desktops().forEach(function(d){d.widgets().forEach(function(w){
        if(w.type!=="org.lumen.notificationhost")return;
        w.currentConfigGroup=["General"];w.writeConfig("presenterEnabled",!chosen);w.reloadConfig();chosen=true;
    });});
    if(!chosen)throw Error("Lumen notification host missing");
}
