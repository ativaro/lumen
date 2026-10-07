pragma ComponentBehavior: Bound
import "Translations.js" as I18n
import QtQuick
import org.kde.kirigami as Kirigami
import QtQuick.Layouts

RowLayout {
    id: bar
    property string uiLanguage: Qt.locale().name.toLowerCase().indexOf("de") === 0 ? "de" : "en"
    function tr(source, args) { return I18n.tr(source, uiLanguage, args); }
    property string surface: "home"
    property var snapshot: ({active: [], attention: false, busy: false})
    property bool expanded: false
    property int panelWidth: 0
    property int unreadNotifications: 0
    readonly property bool compactHome: surface === "home" && width < 230
    signal toggle()
    signal launch(string action)
    signal search()
    signal voice()
    signal notifications()
    spacing: compactHome ? 4 : 12
    Layout.minimumHeight: 28
    Layout.minimumWidth: surface === "home" ? 154 : surface === "search" ? 220 : surface === "control" ? 94 : 50
    Layout.preferredWidth: panelWidth > 0 ? Math.max(Layout.minimumWidth, panelWidth) : surface === "home" ? 266 : surface === "search" ? 460 : surface === "control" ? 104 : 62
    LumenButton {
        objectName: "homeButton"
        visible: bar.surface === "home" || bar.surface === "tasks"
        Layout.fillWidth: true
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        text: bar.surface === "home" && bar.width >= 180 ? "Lumen" : ""
        icon.name: "lumen"; symbolSize: 28
        font.pixelSize: 19; font.weight: Font.DemiBold
        flat: true; checkable: true; checked: bar.expanded
        Accessible.name: bar.tr("Lumen Systemübersicht")
        onClicked: bar.toggle()
    }
    Rectangle { visible: bar.surface === "home"; color: Kirigami.Theme.disabledTextColor; opacity: 0.65; implicitWidth: 1; implicitHeight: 26 }
    LumenButton {
        visible: bar.surface === "home"
        objectName: "filesButton"
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        text: bar.compactHome ? "" : bar.tr("Dateien"); icon.name: "folder"; font.pixelSize: 16
        Accessible.name: bar.tr("Dateien")
        flat: true; onClicked: bar.launch("files")
    }
    LumenButton {
        visible: bar.surface === "search"
        Layout.fillWidth: true
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        objectName: "searchButton"
        text: bar.tr("Suchen oder fragen …"); icon.name: "search"
        font.pixelSize: 16
        flat: true
        Accessible.name: bar.tr("Dateien und Apps suchen oder ein Gespräch führen")
        onClicked: bar.search()
    }
    LumenButton {
        visible: bar.surface === "search"
        objectName: "voiceButton"
        Layout.preferredWidth: 42
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        icon.name: "audio-input-microphone"
        flat: true
        Accessible.name: bar.tr("Mit Lumen sprechen")
        onClicked: bar.voice()
    }
    LumenButton {
        visible: bar.surface === "control"
        objectName: "notificationButton"
        Layout.preferredWidth: 40; Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0; flat: true; icon.name: "notifications"; symbolSize: 22
        Accessible.name: "Lumen Notification" + (bar.unreadNotifications ? " · " + bar.unreadNotifications : "")
        onClicked: bar.notifications()
        Rectangle { visible: bar.unreadNotifications>0; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6; width: 6; height: 6; radius: 3; color: Kirigami.Theme.highlightColor }
    }
    LumenButton {
        visible: bar.surface === "control"
        Layout.fillWidth: true
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        objectName: "centerButton"
        icon.name: "adjustlevels"; symbolSize: 24
        flat: true; checkable: true; checked: bar.expanded
        Accessible.name: bar.tr("Einstellungen, Systemsteuerung und Themes")
        onClicked: bar.toggle()
    }
}
