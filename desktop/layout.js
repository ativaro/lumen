// Plasma 6 scripting API. No screen IDs, application lists or user paths from a saved desktop.
var required = ["org.lumen.system", "org.lumen.search", "org.lumen.control",
    "org.kde.plasma.kickoff", "org.kde.plasma.systemtray", "org.kde.plasma.digitalclock",
    "org.kde.plasma.icontasks", "org.kde.plasma.pager", "org.kde.plasma.panelspacer"];
required.forEach(function(id) {
    if (knownWidgetTypes.indexOf(id) < 0) throw new Error("Desktop-Komponente fehlt: " + id);
});
if (screenCount < 1) throw new Error("Kein Bildschirm vorhanden");
var old = panels(), created = [];
function owned(panel) {
    panel.currentConfigGroup = ["General"];
    return panel.readConfig("lumenLayout", "") === "1";
}
function panel(screen, edge, alignment, width, offset) {
    var p = new Panel();
    created.push(p.id);
    p.screen = screen; p.location = edge; p.alignment = alignment;
    p.height = 56; p.floating = true; p.offset = offset;
    p.lengthMode = "custom"; p.minimumLength = width; p.maximumLength = width; p.length = width;
    p.hiding = edge === "bottom" ? "dodgewindows" : "none";
    p.currentConfigGroup = ["General"]; p.writeConfig("lumenLayout", "1");
    p.writeConfig("lumenLayoutVersion", "2");
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
        var existing = old.filter(function(p) { return p.screen === screen && owned(p); });
        if (existing.length && existing.every(function(p) {
            p.currentConfigGroup = ["General"];
            return p.readConfig("lumenLayoutVersion", "") === "2";
        })) continue;
        var width = screenGeometry(screen).width;
        var left, search, right;
        if (width >= 960) {
            var leftWidth = width >= 1400 ? 334 : 224;
            var rightWidth = width >= 1400 ? 410 : 320;
            var searchWidth = Math.min(480, width - leftWidth - rightWidth - 64);
            left = panel(screen, "top", "left", leftWidth, 16);
            // Center within the free space, accounting for unequal side islands.
            search = panel(screen, "top", "center", searchWidth, (leftWidth - rightWidth) / 2);
            right = panel(screen, "top", "right", rightWidth, 16);
        } else {
            left = panel(screen, "top", "center", width - 24, 0);
            search = left; right = left;
        }
        var launcher = widget(left, "org.kde.plasma.kickoff", {icon: "view-grid"});
        if (screen === 0) launcher.globalShortcut = "Meta+F1";
        widget(left, "org.lumen.system", {surface: "home", panelWidth: search !== left ? leftWidth - 68 : 154});
        if (search === left) widget(left, "org.kde.plasma.panelspacer", {expanding: true});
        widget(search, "org.lumen.search", {surface: "search", panelWidth: search !== left ? searchWidth - 28 : 220});
        if (search === left) widget(left, "org.kde.plasma.panelspacer", {expanding: true});
        widget(right, "org.lumen.control", {surface: "control"});
        widget(right, "org.kde.plasma.systemtray");
        widget(right, "org.kde.plasma.digitalclock", {showDate: false});
        var dockWidth = Math.min(640, Math.floor(width * 0.5));
        var dock = panel(screen, "bottom", "center", dockWidth, -82);
        widget(dock, "org.kde.plasma.icontasks", {
            launchers: ["applications:lumen-files.desktop", "applications:lumen.desktop"],
            showOnlyCurrentScreen: true
        });
        var pager = panel(screen, "bottom", "center", 140, Math.floor(dockWidth / 2) + 12);
        widget(pager, "org.kde.plasma.pager", {displayedText: 1});
    }
} catch (error) {
    created.forEach(function(id) { var p = panelById(id); if (p) p.remove(); });
    throw error;
}
// Upgrade only Lumen-owned panels after their replacements succeeded.
old.filter(function(p) {
    if (!owned(p)) return options.replacePanels;
    p.currentConfigGroup = ["General"];
    return p.readConfig("lumenLayoutVersion", "") !== "2";
}).forEach(function(p) { p.remove(); });
desktops().forEach(function(d) {
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", options.wallpaper);
});
print(JSON.stringify(created));
