pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import "Translations.js" as I18n

Item {
    id: center
    property string uiLanguage: "de"
    property var themeColors: null
    SystemPalette { id: nativeColors }
    Kirigami.Theme.inherit: false
    Kirigami.Theme.backgroundColor: themeColors ? themeColors.window : nativeColors.window
    Kirigami.Theme.textColor: themeColors ? themeColors.text : nativeColors.text
    Kirigami.Theme.disabledTextColor: themeColors ? themeColors.muted : Qt.alpha(nativeColors.text,0.68)
    Kirigami.Theme.alternateBackgroundColor: themeColors ? themeColors.hover : nativeColors.alternateBase
    Kirigami.Theme.highlightColor: themeColors ? themeColors.accent : nativeColors.highlight
    Kirigami.Theme.highlightedTextColor: themeColors ? themeColors.onAccent : nativeColors.highlightedText
    property var items: []
    property bool inhibited: false
    property bool gaming: false
    property string error: ""
    property int pageSize: 30
    property string filter: "all"
    property bool grouped: false
    property date now: new Date()
    property string selectedKey: ""
    readonly property bool wide: width>=820
    readonly property int unread: items.filter(row=>!row.read && !row.archived && !row.resolved && row.snoozed*1000<=center.now.getTime()).length
    readonly property var selected: filtered.find(row=>key(row)===selectedKey) || null
    signal action(string identity, bool system, string operation)
    signal toggleDnd()
    signal preferences()
    function tr(text) { return I18n.tr(text,uiLanguage); }
    function key(row) { return (row.system ? "system:" : "lumen:")+row.id; }
    function selectNotice(identity) {
        search.clear();filter="all";grouped=false;pageSize=30;
        selectedKey=filtered.some(row=>key(row)===identity)?identity:"";
    }
    function choose(row) { selectedKey=key(row); }
    readonly property var filtered: items.filter(function(row) {
        const matches=!search.text || (row.title+" "+row.body+" "+row.source).toLowerCase().indexOf(search.text.toLowerCase())>=0;
        const later=row.snoozed*1000>center.now.getTime();
        return matches && (center.filter==="history" ? row.archived : !row.archived &&
            (center.filter==="done" ? !!row.resolved : !row.resolved && (center.filter==="later" ? later : !later &&
            (center.filter!=="unread" || !row.read) && (center.filter!=="attention" || row.attention || ["question","decision","problem"].indexOf(row.kind)>=0))));
    }).sort((a,b)=>center.grouped ? a.source.localeCompare(b.source) || b.updated-a.updated : b.updated-a.updated)
    readonly property var closable: filtered.filter(row=>!row.archived)
    onFilteredChanged: if(selectedKey && !selected) selectedKey=""
    function closeAll() { for(const row of closable.slice()) action(row.id,!!row.system,"archive"); }
    Timer { interval: 30000; repeat: true; running: center.visible; onTriggered: center.now=new Date() }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 24; spacing: 16
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            ColumnLayout {
                Layout.fillWidth: true; spacing: 4
                Kirigami.Heading { text: center.tr("Benachrichtigungen"); level: 1; font.pixelSize: 26; font.weight: Font.Medium; Layout.fillWidth: true; wrapMode: Text.Wrap }
                PC.Label { text: center.unread ? center.unread+" "+center.tr("ungelesen") : center.tr("Alles Wichtige an einem Ort"); color: Kirigami.Theme.disabledTextColor; font.pixelSize: 12 }
            }
            LumenButton { objectName: "notificationDnd"; flat: true; checkable: true; checked: center.inhibited; icon.name: center.inhibited ? "notifications-disabled" : "notifications"; Accessible.name: center.tr("Nicht stören"); PC.ToolTip.text: Accessible.name; PC.ToolTip.visible: hovered; onClicked: center.toggleDnd() }
            LumenButton { flat: true; icon.name: "configure"; Accessible.name: center.tr("Benachrichtigungen einstellen"); PC.ToolTip.text: Accessible.name; PC.ToolTip.visible: hovered; onClicked: center.preferences() }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            PC.TextField {
                Kirigami.Theme.inherit: true
                background: Rectangle { radius: 8; color: center.themeColors ? center.themeColors.content : nativeColors.base; border.width: search.activeFocus ? 2 : 1; border.color: search.activeFocus ? Kirigami.Theme.highlightColor : center.themeColors ? center.themeColors.border : Qt.alpha(Kirigami.Theme.textColor,0.24) }
                color: Kirigami.Theme.textColor; placeholderTextColor: Kirigami.Theme.disabledTextColor; implicitHeight: 44; leftPadding: 12; rightPadding: 12; topPadding: 10; bottomPadding: 10; font.pixelSize: 14
                id: search; objectName: "notificationSearch"; Layout.fillWidth: true; placeholderText: center.tr("Meldungen durchsuchen …"); Accessible.name: placeholderText; onTextChanged: center.pageSize=30 }
            LumenButton { objectName: "notificationGroup"; flat: true; checkable: true; checked: center.grouped; icon.name: "view-list-tree"; Accessible.name: center.tr("Nach App gruppieren"); PC.ToolTip.text: Accessible.name; PC.ToolTip.visible: hovered; onClicked: center.grouped=!center.grouped }
            LumenButton { objectName: "notificationCloseAll"; flat: true; icon.name: "edit-clear-all"; Accessible.name: center.tr("Alle schließen"); enabled: center.closable.length>0; PC.ToolTip.text: Accessible.name; PC.ToolTip.visible: hovered; onClicked: center.closeAll() }
        }
        Flow {
            Layout.fillWidth: true; spacing: 4
            Repeater {
                model: [{key:"all",label:"Offen"},{key:"unread",label:"Ungelesen"},{key:"attention",label:"Braucht dich"},{key:"later",label:"Später"},{key:"done",label:"Erledigt"},{key:"history",label:"Verlauf"}]
                delegate: LumenButton {
                    required property var modelData
                    flat: true; text: center.tr(modelData.label); checkable: true; checked: center.filter===modelData.key
                    onClicked: {center.selectedKey="";center.filter=modelData.key;center.pageSize=30;}
                }
            }
        }
        PC.Label { visible: center.error!==""; text: center.error; textFormat: Text.PlainText; wrapMode: Text.Wrap; Layout.fillWidth: true; color: Kirigami.Theme.negativeTextColor }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Item {
                visible: center.wide || !center.selected
                Layout.fillWidth: !center.wide; Layout.preferredWidth: center.wide ? 320 : -1; Layout.fillHeight: true
                ListView {
                    id: list; objectName: "notificationList"; anchors.fill: parent; clip: true; spacing: 8; reuseItems: true
                    model: center.filtered.slice(0,center.pageSize)
                    PC.ScrollBar.vertical: PC.ScrollBar {}
                    delegate: Rectangle {
                        id: card
                        required property var modelData
                        x: 4; width: list.width-12; height: content.implicitHeight+32; radius: 10
                        color: center.selectedKey===center.key(modelData) ? Kirigami.Theme.alternateBackgroundColor : tap.hovered ? Qt.alpha(Kirigami.Theme.textColor,0.04) : "transparent"
                        border.width: activeFocus ? 2 : 0; border.color: Kirigami.Theme.highlightColor
                        activeFocusOnTab: true; Accessible.role: Accessible.ListItem; Accessible.name: modelData.source+": "+modelData.title
                        Keys.onReturnPressed: center.choose(modelData)
                        Keys.onSpacePressed: center.choose(modelData)
                        TapHandler { onTapped: center.choose(card.modelData) }
                        HoverHandler { id: tap }
                        ColumnLayout {
                            id: content; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 8
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Kirigami.Icon { visible: !!card.modelData.system; source: card.modelData.icon || "notifications"; Layout.preferredWidth: 18; Layout.preferredHeight: 18 }
                                LumenIcon { visible: !card.modelData.system; name: "lumen"; color: Kirigami.Theme.highlightColor; Layout.preferredWidth: 18; Layout.preferredHeight: 18 }
                                PC.Label { text: card.modelData.source; textFormat: Text.PlainText; elide: Text.ElideRight; Layout.fillWidth: true; font.pixelSize: 12; color: Kirigami.Theme.disabledTextColor }
                                PC.Label { text: Qt.formatDateTime(new Date(card.modelData.updated*1000),"hh:mm"); font.pixelSize: 12; color: Kirigami.Theme.disabledTextColor }
                                Rectangle { visible: !card.modelData.read; implicitWidth: 6; implicitHeight: 6; radius: 3; color: Kirigami.Theme.highlightColor }
                            }
                            PC.Label { text: card.modelData.title; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; font.pixelSize: 15; font.weight: card.modelData.read ? Font.Normal : Font.DemiBold; Layout.fillWidth: true }
                            PC.Label { visible: text!==""; text: card.modelData.body; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; font.pixelSize: 13; color: Kirigami.Theme.disabledTextColor; Layout.fillWidth: true }
                        }
                    }
                    footer: LumenButton { visible: center.filtered.length>center.pageSize; text: center.tr("Weitere laden"); onClicked: center.pageSize+=30 }
                    ColumnLayout {
                        anchors.centerIn: parent; visible: list.count===0; width: parent.width-32; spacing: 12
                        Kirigami.Icon { source: "notifications"; Layout.preferredWidth: 36; Layout.preferredHeight: 36; Layout.alignment: Qt.AlignHCenter; opacity: 0.5 }
                        PC.Label { text: center.tr("Hier ist gerade alles ruhig."); Layout.fillWidth: true; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 18 }
                        PC.Label { text: center.tr("Neue Meldungen erscheinen automatisch."); Layout.fillWidth: true; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; color: Kirigami.Theme.disabledTextColor }
                    }
                }
            }
            Rectangle { visible: center.wide; Layout.fillHeight: true; implicitWidth: 1; color: Qt.alpha(Kirigami.Theme.textColor,0.14) }
            Item {
                visible: center.wide || !!center.selected; Layout.fillWidth: true; Layout.fillHeight: true
                NotificationDetail {
                    anchors.fill: parent; visible: !!center.selected; notice: center.selected; uiLanguage: center.uiLanguage; now: center.now; backVisible: !center.wide
                    onBack: center.selectedKey=""
                    onAction: (identity,system,operation)=>center.action(identity,system,operation)
                }
                ColumnLayout {
                    visible: !center.selected; anchors.centerIn: parent; width: parent.width-48; spacing: 12
                    PC.Label { text: center.tr("Wähle eine Meldung"); font.pixelSize: 22; Layout.fillWidth: true; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
                    PC.Label { text: center.tr("Hier liest du die Zusammenfassung und kannst direkt weiterarbeiten."); color: Kirigami.Theme.disabledTextColor; Layout.fillWidth: true; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
                }
            }
        }
        PC.Label { text: center.tr(center.gaming ? "Spiel erkannt · Meldungen werden still gesammelt." : "Systemmeldungen bleiben auf diesem Gerät."); Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: Kirigami.Theme.disabledTextColor }
    }
}
