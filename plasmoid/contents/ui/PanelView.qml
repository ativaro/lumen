pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: panel
    property var snapshot: ({active: [], recent: [], error: "", busy: false, attention: false})
    property string expandedTask: ""
    property string title: "Dein System"
    property bool navigation: true
    property bool dismissBusy: false
    signal launch(string action)
    signal openTask(string taskId)
    signal dismissTask(string taskId)
    signal refresh()
    spacing: Kirigami.Units.smallSpacing * 2
    ListModel { id: activeTasks; dynamicRoles: true }
    ListModel { id: recentTasks; dynamicRoles: true }
    function updateRows(model, rows) {
        for (let index = 0; index < rows.length; ++index) {
            let previous = index;
            while (previous < model.count && model.get(previous).record.id !== rows[index].id) ++previous;
            if (previous === model.count) model.insert(index, {record: rows[index]});
            else {
                if (previous !== index) model.move(previous, index, 1);
                model.setProperty(index, "record", rows[index]);
            }
        }
        if (model.count > rows.length) model.remove(rows.length, model.count - rows.length);
    }
    onSnapshotChanged: {
        updateRows(activeTasks, snapshot.active);
        updateRows(recentTasks, snapshot.recent);
    }

    RowLayout {
        Layout.fillWidth: true
        Kirigami.Heading { text: panel.title; font.pixelSize: panel.navigation ? 24 : 19; font.weight: Font.DemiBold; level: panel.navigation ? 2 : 3; Layout.fillWidth: true }
        LumenButton { flat: true;
            visible: panel.navigation
            icon.name: "view-refresh"
            icon.color: Kirigami.Theme.textColor
            text: "Aktualisieren"
            display: PC.AbstractButton.IconOnly
            Accessible.name: text
            PC.ToolTip.text: text
            PC.ToolTip.visible: hovered
            onClicked: panel.refresh()
        }
    }
    PC.Label {
        Layout.fillWidth: true
        visible: panel.navigation || panel.snapshot.error !== "" || panel.snapshot.attention || panel.snapshot.busy
        text: panel.snapshot.error || (panel.snapshot.attention ? "Lumen braucht deine Rückmeldung"
            : panel.snapshot.busy ? "Lumen arbeitet für dich" : "Deine Aufgaben im Blick")
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: panel.snapshot.error ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
    }
    PC.ScrollView {
        id: scroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            width: scroll.availableWidth
            spacing: Kirigami.Units.smallSpacing * 2
            PC.Label {
                Layout.fillWidth: true
                visible: !panel.snapshot.error && panel.snapshot.active.length === 0 && panel.snapshot.recent.length === 0
                text: "Keine Aufgaben in dieser Übersicht. Den Verlauf findest du unter „Alle Aufgaben“."
                wrapMode: Text.Wrap
                Layout.topMargin: Kirigami.Units.largeSpacing
            }
            Kirigami.Heading {
                text: "Aktuell"; font.pixelSize: 12; color: Kirigami.Theme.disabledTextColor
                level: 4
                visible: panel.snapshot.active.length > 0
            }
            Repeater {
                model: activeTasks
                TaskCard {
                    required property var record
                    task: record
                    dismissBusy: panel.dismissBusy
                    Layout.fillWidth: true
                    expanded: panel.expandedTask === task.id
                    onToggle: panel.expandedTask = expanded ? "" : task.id
                    onOpenTask: taskId => panel.openTask(taskId)
                    onDismissTask: taskId => panel.dismissTask(taskId)
                }
            }
            Kirigami.Heading {
                text: "Zuletzt"; font.pixelSize: 12; color: Kirigami.Theme.disabledTextColor
                level: 4
                visible: panel.snapshot.recent.length > 0
                Layout.topMargin: Kirigami.Units.smallSpacing
            }
            Repeater {
                model: recentTasks
                TaskCard {
                    required property var record
                    task: record
                    dismissBusy: panel.dismissBusy
                    Layout.fillWidth: true
                    expanded: panel.expandedTask === task.id
                    onToggle: panel.expandedTask = expanded ? "" : task.id
                    onOpenTask: taskId => panel.openTask(taskId)
                    onDismissTask: taskId => panel.dismissTask(taskId)
                }
            }
        }
    }
    LumenButton {
        Layout.fillWidth: true
        flat: true
        text: "Alle Aufgaben"
        hint: "›"
        icon.name: "view-task"
        icon.color: Kirigami.Theme.textColor
        onClicked: panel.launch("tasks")
    }
    GridLayout {
        visible: panel.navigation
        Layout.fillWidth: true
        columns: panel.width < 440 ? 1 : 3
        LumenButton {
            Layout.fillWidth: true
            flat: true
            text: "Dateien"
            icon.name: "folder"
            icon.color: Kirigami.Theme.textColor
            onClicked: panel.launch("files")
        }
        LumenButton {
            Layout.fillWidth: true
            flat: true
            text: "Systemstatus"
            icon.name: "utilities-system-monitor"
            icon.color: Kirigami.Theme.textColor
            onClicked: panel.launch("system")
        }
        LumenButton {
            Layout.fillWidth: true
            flat: true
            text: "Arbeitsplatz"
            objectName: "workplaceButton"
            icon.name: "user-desktop"
            icon.color: Kirigami.Theme.textColor
            onClicked: panel.launch("workplace")
        }
    }
}
