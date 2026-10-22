// Add menus to existing Lumen islands; preserve launchers, other widgets and the other panels.
function installLumenAppMenus(candidates) {
    if (knownWidgetTypes.indexOf("org.lumen.appmenu") < 0) return [];
    var changed = [];
    candidates.filter(function(p) { return p.location === "top"; }).forEach(function(left) {
        var home = left.widgets().find(function(w) { return w.type === "org.lumen.system"; });
        if (!home) return;
        var width = screenGeometry(left.screen).width;
        var search = panels().find(function(p) {
            return p.screen === left.screen && p.id !== left.id && p.location === "top"
                && p.widgets().some(function(w) { return w.type === "org.lumen.search"; });
        });
        var boundary = search ? (width - search.length) / 2 + search.offset : width;
        var limit = search ? boundary - left.offset - 24 : left.length;
        var existing = left.widgets().find(function(w) { return w.type === "org.lumen.appmenu"; });
        if (existing) existing.currentConfigGroup = ["General"];
        // Fit-content panels may report a screen-wide minimum instead of their visible width.
        var baseLength = existing ? existing.readConfig("baseLength", left.length) : left.length;
        var original = {panel:left.id, length:left.length, minimumLength:left.minimumLength,
            maximumLength:left.maximumLength, lengthMode:left.lengthMode, menus:[]};
        if (search && limit > baseLength) {
            left.minimumLength = baseLength;
            left.maximumLength = limit;
            left.lengthMode = "fit";
        }
        [false, true].forEach(function(compact, index) {
            var menu = left.widgets().find(function(w) {
                if (w.type !== "org.lumen.appmenu") return false;
                w.currentConfigGroup = ["General"];
                return w.readConfig("compactView", false) === compact;
            });
            if (!menu) { menu = left.addWidget("org.lumen.appmenu"); menu.index = home.index + 1 + index; }
            menu.currentConfigGroup = ["General"];
            menu.writeConfig("compactView", compact);
            menu.writeConfig("baseLength", baseLength);
            menu.writeConfig("widthBudget", search ? Math.max(40, Math.floor(limit - baseLength - 24)) : 40);
            menu.reloadConfig();
            original.menus.push(menu.id);
        });
        changed.push(original);
    });
    return changed;
}
