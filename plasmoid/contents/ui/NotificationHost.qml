pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Window
import org.kde.notificationmanager as N
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import org.kde.plasma.workspace.dbus as DBus
import "Translations.js" as I18n

Item {
    id: host
    property string helper: "/usr/bin/lumen-panel"
    property string uiLanguage: "de"
    property bool panelOpen: false
    property var popupAnchor: null
    property bool primary: false
    property bool ownsPopups: false
    property bool presenterConfigured: false
    property bool gaming: false
    property bool locked: true
    property double startedAt: Date.now()
    property var presented: ({})
    property string toastIdentity: ""
    property var themeColors: null
    property var localItems: []
    property var systemItems: []
    property string error: ""
    property string pending: ""
    property var queuedActions: []
    property var discussion: null
    property int discussionAttempts: 0
    property date now: new Date()
    readonly property bool inhibited: gaming || locked || settings.notificationsInhibitedUntil > now || settings.notificationsInhibitedByApplication || (settings.inhibitNotificationsWhenFullscreen && settings.fullscreenFocused) || (settings.inhibitNotificationsWhenScreensMirrored && settings.screensMirrored)
    onInhibitedChanged: { if(primary) N.Server.inhibited=inhibited; if(inhibited) popup.dismiss(); }
    onPrimaryChanged: {if(primary){startedAt=Date.now();Qt.callLater(refresh);}else{ownsPopups=false;popup.dismiss();}}
    onOwnsPopupsChanged:if(ownsPopups){startedAt=Date.now();rebuildTimer.restart()}
    function checkLock() {
        DBus.SessionBus.asyncCall({service:"org.freedesktop.ScreenSaver",path:"/ScreenSaver",iface:"org.freedesktop.ScreenSaver",member:"GetActive"},
            result=>{host.locked=result.value!==false;}, ()=>{host.locked=true;});
    }
    DBus.SignalWatcher {
        service: "org.freedesktop.ScreenSaver"; path: "/ScreenSaver"; iface: "org.freedesktop.ScreenSaver"
        function dbusActiveChanged(active) { host.locked=active; }
    }
    readonly property var items: systemItems.concat(localItems).sort((a,b) => b.updated-a.updated)
    readonly property int unread: items.filter(row => !row.read && !row.archived && !row.resolved && row.snoozed*1000<=now.getTime()).length
    function tr(text) { return I18n.tr(text, uiLanguage); }
    function refresh() {
        if (pending) return;
        pending=helper+(primary && !presenterConfigured ? " --notification-own-popups" : " --notification-snapshot");
        runner.connectSource(pending);
    }
    function toggleDnd() {
        settings.notificationsInhibitedUntil = inhibited ? new Date(0) : new Date(Date.now()+3600000);
        settings.save(); now=new Date();
    }
    function preferences() { runner.connectSource(helper+" --notification-settings"); }
    function showAll() { fullWindow.show(); fullWindow.raise(); fullWindow.requestActivate(); messages.lastRead=new Date(); refresh(); rebuild(); }
    function displayNotice(row) {
        if(inhibited || !row.localIdentity) return row;
        const local=localItems.find(item=>item.id===row.localIdentity);
        return local ? Object.assign({},local,{system:false}) : row;
    }
    onLocalItemsChanged: {
        if(popup.visible && popup.notice && popup.notice.localIdentity && !inhibited)
            popup.notice=displayNotice(popup.notice);
    }
    function rebuild() {
        const rows=[];
        const retained={}; let popupValid=false; let presentedNew=false;
        for (let i=0; i<messages.rowCount(); i++) {
            const idx=messages.index(i,0);
            const value=role=>messages.data(idx,role);
            const hints=value(N.Notifications.HintsRole) || {};
            const actions=[];
            if (value(N.Notifications.HasDefaultActionRole)) actions.push({key:"default", label:tr("Öffnen")});
            const names=value(N.Notifications.ActionNamesRole) || [], labels=value(N.Notifications.ActionLabelsRole) || [];
            for(let a=0; a<Math.min(names.length,6); a++) actions.push({key:names[a],label:String(labels[a] || names[a]).slice(0,100)});
            let body=String(value(N.Notifications.BodyRole) || "");
            // Never render notification HTML, links or remote images in Lumen.
            body=body.replace(/<[^>]*>/g," ").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"').replace(/&amp;/g,"&");
            const date=value(N.Notifications.UpdatedRole) || value(N.Notifications.CreatedRole);
            const row={id:String(value(N.Notifications.IdRole)), system:true, localIdentity:String(hints["x-lumen-id"]||""),
                source:String(value(N.Notifications.ApplicationNameRole) || tr("System")),
                icon:/^[a-zA-Z0-9_.-]+$/.test(value(N.Notifications.ApplicationIconNameRole)||"") ? value(N.Notifications.ApplicationIconNameRole) : "notifications", title:String(value(N.Notifications.SummaryRole) || "").slice(0,300),
                body:body.slice(0,2000), updated:new Date(date).getTime()/1000,
                read:!!value(N.Notifications.ReadRole), archived:false, snoozed:0,
                attention:value(N.Notifications.UrgencyRole)===N.Notifications.CriticalUrgency, actions:actions};
            const stamp=row.id+":"+row.updated;
            if(presented[stamp]) retained[stamp]=true;
            if(row.id===toastIdentity && !value(N.Notifications.ExpiredRole) && !value(N.Notifications.DismissedRole)) popupValid=true;
            if(primary && ownsPopups && !presented[stamp]) {
                retained[stamp]=true;
                const app=value(N.Notifications.DesktopEntryRole)||"", service=value(N.Notifications.NotifyRcNameRole)||"";
                const allowed=settings.popupBlacklistedApplications.indexOf(app)<0 && settings.popupBlacklistedServices.indexOf(service)<0;
                const priority=value(N.Notifications.UrgencyRole)!==N.Notifications.LowUrgency || settings.lowPriorityPopups;
                if(!presentedNew && row.updated*1000>=startedAt && !inhibited && allowed && priority && !value(N.Notifications.ExpiredRole) && !value(N.Notifications.DismissedRole)) {
                    popup.present(displayNotice(row)); if(row.localIdentity)host.refresh(); toastIdentity=row.id; popupValid=true; messages.playSoundHint(idx);
                    presentedNew=true;
                }
            }
            if (!hints["x-lumen-id"] && settings.historyBlacklistedApplications.indexOf(value(N.Notifications.DesktopEntryRole)||"")<0 && settings.historyBlacklistedServices.indexOf(value(N.Notifications.NotifyRcNameRole)||"")<0) rows.push(row);
        }
        presented=retained;
        if(!popupValid) popup.dismiss();
        if(JSON.stringify(systemItems)!==JSON.stringify(rows)) systemItems=rows;
    }
    function act(identity, system, operation) {
        if(operation==="discuss" && !items.some(row=>row.id===identity && row.scope && row.scope!=="local")) {
            const row=items.find(value=>value.id===identity && value.system===system);
            if(!row || discussion) return;
            discussion={source:row.source.slice(0,100),title:row.title.slice(0,300),body:row.body.slice(0,2000)};
            discussionAttempts=0; error="";
            runner.connectSource(helper+" --open-page chat");
            discussionTimer.start();
            return;
        }
        if (system) {
            for(let i=0; i<messages.rowCount(); i++) {
                const idx=messages.index(i,0);
                if(String(messages.data(idx,N.Notifications.IdRole))!==identity) continue;
                if(operation==="archive") messages.close(idx);
                else if(operation==="default" && messages.data(idx,N.Notifications.HasDefaultActionRole)) messages.invokeDefaultAction(idx);
                else if((messages.data(idx,N.Notifications.ActionNamesRole)||[]).indexOf(operation)>=0) messages.invokeAction(idx,operation);
                else {error=tr("Diese Aktion ist nicht mehr verfügbar.");return;}
                rebuild();return;
            }
            error=tr("Diese Meldung ist nicht mehr verfügbar.");return;
        }
        if (!/^[a-f0-9]{64}$/.test(identity) || ["open","discuss","read","unread","archive","restore","later","now","resolve","reopen"].indexOf(operation)<0) return;
        if (pending) { queuedActions=queuedActions.concat([{id:identity,operation:operation}]); return; }
        pending=helper+" --notification-action "+operation+" --notification-id "+identity;
        runner.connectSource(pending);
    }
    N.Notifications {
        id: messages
        window: popup
        showExpired: true; showDismissed: true; showJobs: false; showAddedDuringInhibition: true
        groupMode: N.Notifications.GroupDisabled; sortOrder: Qt.DescendingOrder; limit: 500
        onCountChanged: rebuildTimer.restart()
    }
    N.Settings { id: settings; live: true }
    Timer {
        id: discussionTimer; interval: 500
        onTriggered: {
            const row=host.discussion;
            if(!row) return;
            function retry() {
                if(++host.discussionAttempts<40) discussionTimer.start();
                else {host.discussion=null;host.error=host.tr("Lumen antwortet nicht. Bitte Lumen neu öffnen und erneut versuchen.");}
            }
            DBus.SessionBus.asyncCall({service:"org.lumen.Desktop",path:"/Lumen",iface:"org.lumen.Desktop",member:"DiscussNotification",arguments:[row.source,row.title,row.body]},
                result=>{if(result.value===true) host.discussion=null;else retry();},retry);
        }
    }
    Connections {
        target: messages
        function onDataChanged() { rebuildTimer.restart(); }
        function onModelReset() { rebuildTimer.restart(); }
        function onRowsInserted() { rebuildTimer.restart(); }
        function onRowsRemoved() { rebuildTimer.restart(); }
    }
    Timer { id: rebuildTimer; interval: 50; onTriggered: host.rebuild() }
    Timer {
        interval: 50; running: host.queuedActions.length>0 && !host.pending
        onTriggered: {
            const next=host.queuedActions[0]; host.queuedActions=host.queuedActions.slice(1);
            host.act(next.id,false,next.operation);
        }
    }
    Timer { interval: host.panelOpen || fullWindow.visible ? 2000 : 5000; repeat: true; running: true; triggeredOnStart: true; onTriggered: { host.now=new Date(); host.refresh(); } }
    onPanelOpenChanged: if(panelOpen) {messages.lastRead=new Date();refresh();rebuild();}
    Component.onCompleted: { checkLock(); rebuild(); }
    P5Support.DataSource {
        id: runner; engine: "executable"; connectedSources: []
        onNewData: (source,data) => {
            disconnectSource(source);
            if(source!==host.pending) return;
            host.pending="";
            try {
                if(data["exit code"]!==0) throw new Error();
                const result=JSON.parse(data.stdout);
                if(result.error) {host.error=result.error;return;}
                if(result.context) {
                    if(JSON.stringify(host.themeColors)!==JSON.stringify(result.context.palette||null))host.themeColors=result.context.palette||null;
                    if(source.endsWith(" --notification-own-popups")) host.presenterConfigured=true;
                    host.gaming=!!result.context.gaming;
                    host.ownsPopups=!!result.context.native && host.presenterConfigured;
                    if(host.primary) N.Server.inhibited=host.inhibited;
                    if(!host.ownsPopups) popup.dismiss();
                }
                const next=result.items.map(row=>Object.assign({},row,{system:false,icon:"lumen",actions:row.target?[{key:"open",label:host.tr(({question:"Antworten",decision:"Anfrage prüfen",problem:"Ursache prüfen",result:"Ergebnis ansehen",suggestion:"Vorschlag ansehen"})[row.kind]||"Öffnen")}]:[]}));
                if(JSON.stringify(host.localItems)!==JSON.stringify(next)) host.localItems=next;
                host.error="";
                if(host.primary && !host.presenterConfigured)Qt.callLater(host.refresh);
            } catch(e) {host.error=host.tr("Meldungen gerade nicht erreichbar.");}
        }
    }
    NotificationToast {
        id: popup; uiLanguage: host.uiLanguage; anchorItem: host.popupAnchor
        onAction: (identity,operation)=>host.act(identity,popup.notice ? !!popup.notice.system : true,operation)
        onCenterRequested: host.showAll()
    }
    Window {
        id: fullWindow
        title: "Lumen Notification"; width: 1040; height: 780; minimumWidth: 420; minimumHeight: 420
        color: host.themeColors ? host.themeColors.window : Kirigami.Theme.backgroundColor
        NotificationCenter {
            anchors.fill: parent; themeColors: host.themeColors; uiLanguage: host.uiLanguage; items: host.items; inhibited: host.inhibited; gaming: host.gaming; error: host.error
            onAction: (identity,system,operation)=>host.act(identity,system,operation)
            onToggleDnd: host.toggleDnd(); onPreferences: host.preferences()
        }
    }
}
