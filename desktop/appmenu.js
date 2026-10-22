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
        var right = panels().find(function(p) {
            return p.screen === left.screen && p.id !== left.id && p.location === "top"
                && p.widgets().some(function(w) { return w.type === "org.lumen.control"; });
        });
        // Let menus use the free desktop width; search remains a separate island at the right.
        var rightSpace = right ? right.length + right.offset + 16 : 16;
        var originalSearch = search ? {panel:search.id, length:search.length, minimumLength:search.minimumLength,
            maximumLength:search.maximumLength, lengthMode:search.lengthMode, alignment:search.alignment,
            offset:search.offset, widgets:search.widgets().filter(function(w) { return w.type === "org.lumen.search"; }).map(function(w) {
                w.currentConfigGroup = ["General"]; return {id:w.id, panelWidth:w.readConfig("panelWidth",460)};
            })} : null;
        var existing = left.widgets().find(function(w) { return w.type === "org.lumen.appmenu"; });
        if (existing) existing.currentConfigGroup = ["General"];
        // Fit-content panels may report a screen-wide minimum instead of their visible width.
        var baseLength = existing ? existing.readConfig("baseLength", left.length) : left.length;
        var searchLength = existing ? existing.readConfig("searchLength", search ? search.length : 0) : search ? search.length : 0;
        var required = existing ? Math.max(0, existing.readConfig("requiredWidth", 0)) : 0;
        if (search) {
            var available = width - left.offset - rightSpace - baseLength - 40;
            var searchWidth = required > available - searchLength ? 68 : searchLength;
            if (available < searchLength) searchWidth = 68;
            search.alignment = "right"; search.offset = rightSpace;
            search.minimumLength = searchWidth; search.maximumLength = searchWidth;
            search.lengthMode = "custom"; search.length = searchWidth;
            search.widgets().filter(function(w) { return w.type === "org.lumen.search"; }).forEach(function(w) {
                w.currentConfigGroup = ["General"]; w.writeConfig("panelWidth", searchWidth - 28); w.reloadConfig();
            });
        }
        var limit = width - left.offset - rightSpace - (search ? search.length + 16 : 0);
        var original = {panel:left.id, length:left.length, minimumLength:left.minimumLength,
            maximumLength:left.maximumLength, lengthMode:left.lengthMode, menus:[], search:originalSearch};
        if (limit > baseLength) {
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
            if (!menu) menu = left.addWidget("org.lumen.appmenu");
            menu.currentConfigGroup = ["General"];
            menu.writeConfig("compactView", compact);
            menu.writeConfig("baseLength", baseLength);
            menu.writeConfig("searchLength", searchLength);
            menu.writeConfig("widthBudget", Math.max(40, Math.floor(limit - baseLength - 24)));
            menu.reloadConfig();
            original.menus.push(menu.id);
        });
        var ordinary = left.widgets().filter(function(w) { return w.type !== "org.lumen.appmenu"; });
        var insertion = ordinary.findIndex(function(w) { return w.id === home.id; }) + 1;
        var order = ordinary.slice(0, insertion).concat(original.menus.map(function(id) {
            return left.widgets().find(function(w) { return w.id === id; });
        }), ordinary.slice(insertion));
        // KDE 6.8 cannot append with Widget.index; prepending in reverse preserves the exact order.
        order.slice().reverse().forEach(function(w) { w.index = 0; });
        changed.push(original);
    });
    return changed;
}
