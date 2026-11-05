// Plasma 6 scripting API. No screen IDs, application lists or user paths from a saved desktop.
var required = ["org.kde.plasma.icontasks", "org.kde.plasma.pager"];
required.forEach(function(id) {
    if (knownWidgetTypes.indexOf(id) < 0) throw new Error("Desktop-Komponente fehlt: " + id);
});
if (screenCount < 1) throw new Error("Kein Bildschirm vorhanden");
var old = panels(), created = [];
function panel(screen, edge, alignment, width, offset) {
    var p = new Panel();
    created.push(p.id);
    p.screen = screen; p.location = edge; p.alignment = alignment;
    p.height = 56; p.floating = true; p.offset = offset;
    p.lengthMode = "custom"; p.minimumLength = width; p.maximumLength = width; p.length = width;
    p.hiding = edge === "bottom" ? "dodgewindows" : "none";
    p.currentConfigGroup = ["General"]; p.writeConfig("lumenLayout", "1");
    return p;
}
function widget(p, type, settings) {
    var w = p.addWidget(type);
    if (!w) throw new Error("Widget konnte nicht angelegt werden: " + type);
    w.currentConfigGroup = ["General"];
    Object.keys(settings || {}).forEach(function(key) { w.writeConfig(key, settings[key]); });
    w.reloadConfig();
    return w;
}
try {
    for (var screen = 0; screen < screenCount; screen++) {
        if(old.some(function(p){return p.screen===screen && p.location==="bottom" && p.widgets().some(function(w){return w.type==="org.kde.plasma.icontasks";});}))continue;
        var width=screenGeometry(screen).width;
        var dockWidth = Math.min(640, Math.floor(width * 0.5));
        var dock = panel(screen, "bottom", "center", dockWidth, -82);
        widget(dock, "org.kde.plasma.icontasks", {
            launchers: ["applications:lumen-files.desktop", "applications:lumen.desktop"],
            showOnlyCurrentScreen: true
        });
        var pager = panel(screen, "bottom", "center", 140, Math.floor(dockWidth / 2) + 12);
        widget(pager, "org.kde.plasma.pager", {displayedText: 1});
    }
    installLumenNotificationHost();
    removeLumenTopPanels();
} catch (error) {
    created.forEach(function(id) { var p = panelById(id); if (p) p.remove(); });
    throw error;
}
desktops().forEach(function(d) {
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", options.wallpaper);
});
print(JSON.stringify(created));
