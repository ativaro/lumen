pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property var controller
    required property string kind
    property int limit: 3
    readonly property var theme: controller.theme
    readonly property var rows: kind === "tasks" ? controller.homeView.tasks : kind === "recent" ? controller.homeView.recent : controller.sessions.filter(function(s) { return s.id.length > 0 })
    signal showAll()
    spacing: 0
    RowLayout { Layout.fillWidth: true; Layout.bottomMargin: 14
        Label { Layout.fillWidth: true; text: root.controller.text(root.kind === "tasks" ? "Deine Aufträge" : root.kind === "recent" ? "Zuletzt verwendet" : "Deine Gespräche"); color: root.theme.text; font.family: root.theme.fontFamily; font.pixelSize: root.theme.fontSize; font.weight: Font.Medium }
        Label { text: root.rows.length; color: root.theme.muted; font.pixelSize: Math.max(11,root.theme.fontSize-6); visible: root.rows.length <= root.limit }
        LumenButton { theme: root.theme; quiet: true; implicitHeight: 30; leftPadding: 6; rightPadding: 6; font.pixelSize: Math.max(11,root.theme.fontSize-6); text: root.controller.text("Alle anzeigen") + " →"; visible: root.rows.length > root.limit; onClicked: root.showAll() }
    }
    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.alpha(root.theme.border,0.6) }
    Label { Layout.fillWidth: true; visible: root.rows.length === 0; text: root.controller.text(root.kind === "tasks" ? "Noch keine Aufträge." : root.kind === "recent" ? "Hier erscheinen zuletzt geöffnete Dateien." : "Hier erscheinen deine Gespräche."); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: root.theme.muted; font.pixelSize: root.theme.fontSize-1; Layout.topMargin: 18; Layout.bottomMargin: 18 }
    Repeater {
        model: root.rows.slice(0,root.limit)
        ColumnLayout {
            id: entry
            required property var modelData
            Layout.fillWidth: true; spacing: 0
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                ItemDelegate {
                    id: openRow
                    Layout.fillWidth: true; implicitHeight: Math.max(root.theme.fontSize+(root.theme.compact ? 40 : 50),rowContents.implicitHeight+24)
                    leftPadding: 4; rightPadding: 4
                    enabled: root.kind !== "sessions" || !root.controller.busy
                    Accessible.name: entry.modelData.title
                    onClicked: root.kind === "tasks" ? root.controller.homeView.open_task(entry.modelData.id) : root.kind === "recent" ? root.controller.homeView.open_recent(entry.modelData.path) : root.controller.select_session(entry.modelData.id)
                    background: Rectangle { color: openRow.hovered || openRow.down ? Qt.alpha(root.theme.hover,0.5) : "transparent"; radius: 7; border.color: openRow.activeFocus ? root.theme.accent : "transparent" }
                    contentItem: RowLayout {
                        id: rowContents
                        spacing: 13
                        Item { visible: root.kind !== "tasks"; Layout.preferredWidth: 32; Layout.preferredHeight: 36
                            Image { anchors.centerIn: parent; source: "image://icons/" + (root.kind === "sessions" ? "dialog-messages" : "text-x-generic") + "?" + root.theme.name + "&tint=" + encodeURIComponent(root.theme.muted); sourceSize: Qt.size(19,19); width: 19; height: 19 }
                        }
                        Rectangle { visible: root.kind === "tasks"; Layout.preferredWidth: 18; Layout.preferredHeight: 18; radius: 9; color: ["needs_input","paused","draft"].indexOf(entry.modelData.status)>=0 ? "#dba441" : ["failed","interrupted"].indexOf(entry.modelData.status)>=0 ? "#c66b64" : root.theme.accent
                            Text { anchors.centerIn: parent; text: entry.modelData.status === "completed" ? "✓" : ""; color: root.theme.onAccent; font.pixelSize: 13 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 4
                            Label { Layout.fillWidth: true; text: entry.modelData.title; textFormat: Text.PlainText; elide: Text.ElideRight; color: root.theme.text; font.pixelSize: Math.max(13,root.theme.fontSize-4); font.weight: Font.Medium }
                            Label { Layout.fillWidth: true; visible: text.length > 0; text: root.kind === "tasks" ? (entry.modelData.state || "") : root.kind === "sessions" ? (entry.modelData.updated ? new Date(entry.modelData.updated).toLocaleString(Qt.locale(),Locale.ShortFormat) : "") : (entry.modelData.detail || "") + (entry.modelData.updated ? " · " + new Date(entry.modelData.updated*1000).toLocaleDateString(Qt.locale(),Locale.ShortFormat) : ""); textFormat: Text.PlainText; elide: Text.ElideMiddle; color: root.theme.muted; font.pixelSize: Math.max(11,root.theme.fontSize-6) }
                        }
                        Label { visible: root.kind === "sessions"; text: "›"; color: root.theme.muted; font.pixelSize: 15; Layout.rightMargin: 6 }
                        Label { visible: root.kind === "recent" && text.length > 0; text: (entry.modelData.path || "").split('/').pop().includes('.') ? entry.modelData.path.split('.').pop().slice(0,5).toUpperCase() : ""; color: root.theme.muted; font.pixelSize: Math.max(9,root.theme.fontSize-8); padding: 4; background: Rectangle { radius: 4; color: "transparent"; border.color: Qt.alpha(root.theme.border,0.6) } }
                    }
                }
                LumenButton { visible: root.kind === "tasks" && ["completed","cancelled"].indexOf(entry.modelData.status)>=0; theme: root.theme; quiet: true; text: "×"; hint: root.controller.text("Auftrag schließen"); onClicked: root.controller.homeView.dismiss(entry.modelData.id) }
                LumenButton { visible: root.kind === "tasks" && entry.modelData.status === "needs_input"; theme: root.theme; quiet: true; text: root.controller.text("Ansehen"); onClicked: root.controller.homeView.open_task(entry.modelData.id) }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.alpha(root.theme.border,0.2) }
        }
    }
}
