// Keep native menus first; context and search occupy separate, non-overlapping islands.
function installLumenAppMenus(candidates) {
    if (knownWidgetTypes.indexOf("org.lumen.appmenu") < 0) return [];
    var changed = [];
    candidates.filter(function(p) { return p.location === "top"; }).forEach(function(left) {
        var home = left.widgets().find(function(w) { return w.type === "org.lumen.system"; });
        if (!home) return;
        var width = screenGeometry(left.screen).width;
        var peers = panels().filter(function(p) { return p.screen === left.screen && p.id !== left.id && p.location === "top"; });
        function withWidget(type) { return peers.find(function(p) { return p.widgets().some(function(w) { return w.type === type; }); }); }
        var search = withWidget("org.lumen.search"), right = withWidget("org.lumen.control");
        var context = withWidget("org.lumen.topbarcontext");
        var original = {panel:left.id, length:left.length, minimumLength:left.minimumLength, maximumLength:left.maximumLength,
            lengthMode:left.lengthMode, menus:[], search:search ? {panel:search.id, length:search.length, minimumLength:search.minimumLength,
            maximumLength:search.maximumLength, lengthMode:search.lengthMode, alignment:search.alignment, offset:search.offset, widgets:search.widgets().filter(function(w) {return w.type === "org.lumen.search";}).map(function(w) {w.currentConfigGroup=["General"];return {id:w.id,panelWidth:w.readConfig("panelWidth",460)};})} : null};
        var existing = left.widgets().find(function(w) { return w.type === "org.lumen.appmenu"; });
        if (existing) existing.currentConfigGroup = ["General"];
        var baseLength = existing ? existing.readConfig("baseLength", left.length) : left.length;
        var required = existing ? Math.max(0, existing.readConfig("requiredWidth", 0)) : 0;
        home.currentConfigGroup = ["General"];
        var homeWidth = home.readConfig("panelWidth",Math.max(154,baseLength-68));
        original.home = {id:home.id,panelWidth:homeWidth};
        if (homeWidth > 220) { baseLength -= homeWidth - 220; home.writeConfig("panelWidth",220); home.reloadConfig(); }
        var rightSpace = right ? right.length + right.offset + 16 : 16;
        var searchWidth = search ? Math.min(350, Math.max(68, width - left.offset - rightSpace - baseLength - required - 40)) : 0;
        var centered = !!search && width >= 2000;
        if (centered && required > width / 2 - searchWidth / 2 - left.offset - baseLength - 32) {
            searchWidth = 68;
            centered = required <= width / 2 - searchWidth / 2 - left.offset - baseLength - 32;
        }
        if (search) {
            search.alignment = centered ? "center" : "right"; search.offset = centered ? 0 : rightSpace;
            search.minimumLength = searchWidth; search.maximumLength = searchWidth;
            search.lengthMode = "custom"; search.length = searchWidth;
            search.widgets().filter(function(w) { return w.type === "org.lumen.search"; }).forEach(function(w) {
                w.currentConfigGroup = ["General"]; w.writeConfig("panelWidth", searchWidth - 28); w.reloadConfig();
            });
        }
        var limit = centered ? width / 2 - searchWidth / 2 - 16 : width - rightSpace - (search ? searchWidth + 16 : 0);
        var contextSpace = centered ? width - rightSpace - (width / 2 + searchWidth / 2 + 16)
            : limit - left.offset - baseLength - required - 40;
        var contextWidth = Math.min(468, Math.max(0, Math.floor(contextSpace)));
        if (contextWidth < 108) contextWidth = 0;
        if (!context && knownWidgetTypes.indexOf("org.lumen.topbarcontext") >= 0) {
            context = new Panel(); context.screen = left.screen; context.location = "top"; context.height = left.height;
            context.floating = true; context.hiding = "none";
            context.currentConfigGroup = ["General"]; context.writeConfig("lumenTopbarContext", "1");
            context.addWidget("org.lumen.topbarcontext");
            original.createdContext = context.id;
        }
        if (context) {
            context.alignment = "right"; context.offset = rightSpace + (centered ? 0 : searchWidth + 16);
            context.minimumLength = Math.max(1, contextWidth); context.maximumLength = Math.max(1, contextWidth);
            context.lengthMode = "custom"; context.length = Math.max(1, contextWidth);
            context.widgets().forEach(function(w) {
                if (w.type !== "org.lumen.topbarcontext") return;
                w.currentConfigGroup = ["General"]; w.writeConfig("widthBudget", Math.max(0, contextWidth - 28)); w.reloadConfig();
            });
            if (!centered && contextWidth) limit -= contextWidth + 16;
        }
        original.context = context ? {panel:context.id,width:contextWidth,centeredSearch:centered} : null;
        left.minimumLength = baseLength; left.maximumLength = Math.max(baseLength, Math.floor(limit - left.offset)); left.lengthMode = "fit";
        [false, true].forEach(function(compact) {
            var menu = left.widgets().find(function(w) {
                if (w.type !== "org.lumen.appmenu") return false;
                w.currentConfigGroup = ["General"]; return w.readConfig("compactView", false) === compact;
            });
            if (!menu) menu = left.addWidget("org.lumen.appmenu");
            menu.currentConfigGroup = ["General"]; menu.writeConfig("compactView",compact);
            menu.writeConfig("baseLength",baseLength); menu.writeConfig("searchLength",350);
            menu.writeConfig("widthBudget", Math.max(40, left.maximumLength - baseLength - 24)); menu.reloadConfig();
            original.menus.push(menu.id);
        });
        var ordinary = left.widgets().filter(function(w) { return w.type !== "org.lumen.appmenu"; });
        var insertion = ordinary.findIndex(function(w) { return w.id === home.id; }) + 1;
        var order = ordinary.slice(0,insertion).concat(original.menus.map(function(id) { return left.widgets().find(function(w) { return w.id === id; }); }),ordinary.slice(insertion));
        // KDE 6.8 cannot append with Widget.index; prepend in reverse to preserve order.
        order.slice().reverse().forEach(function(w) { w.index = 0; });
        changed.push(original);
    });
    return changed;
}
