pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    required property var controller
    readonly property var theme: window.controller.theme
    width: 860; height: 680
    minimumWidth: 520; minimumHeight: 430
    visible: false; color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint
    title: window.controller.text("Lumen Suche")
    font.family: "Noto Sans"
    palette.windowText: window.theme.text; palette.text: window.theme.text
    palette.base: window.theme.base; palette.button: window.theme.button
    palette.buttonText: window.theme.text; palette.highlight: window.theme.accent
    palette.highlightedText: window.theme.onAccent; palette.placeholderText: window.theme.muted
    onClosing: function(event) { event.accepted = false; hide() }
    onVisibleChanged: { if (!visible) window.controller.hidden(); else composer.forceActiveFocus() }
    Shortcut { sequence: "Escape"; enabled: !options.opened; onActivated: window.hide() }
    Connections {
        target: window.controller
        function onHideRequested() { window.hide() }
        function onFocusRequested() { composer.forceActiveFocus() }
        function onQueryChanged() { if (composer.text !== window.controller.query) composer.text = window.controller.query }
        function onSelectionChanged() { results.positionViewAtIndex(window.controller.selectedIndex, ListView.Contain) }
        function onMessagesChanged() { if (conversation.atYEnd && conversation.scroller) Qt.callLater(function() { conversation.scroller.contentY = Math.max(0, conversation.contentHeight - conversation.height) }) }
    }
    Rectangle {
        anchors.fill: surface; anchors.margins: -5
        radius: surface.radius + 5; color: "#15000000"
    }
    Rectangle {
        id: surface
        anchors.fill: parent; anchors.margins: 10
        radius: window.theme.radius + 12
        color: window.theme.window; border.color: Qt.alpha(window.theme.border, 0.8)
        clip: true
        Rectangle {
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 1
            height: 150; radius: surface.radius
            gradient: Gradient { GradientStop { position: 0; color: Qt.alpha(window.theme.accent, 0.06) } GradientStop { position: 1; color: "transparent" } }
        }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 24; spacing: 16
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 38; Layout.maximumHeight: 38; spacing: 8
                Image { source: "image://icons/lumen?" + window.theme.name; sourceSize: Qt.size(24, 24); Layout.preferredWidth: 24; Layout.preferredHeight: 24 }
                Label { text: "Lumen"; color: window.theme.text; font.pixelSize: 16; font.weight: Font.DemiBold }
                Label { text: " /  " + window.controller.text("Suche"); color: window.theme.muted; font.pixelSize: 15 }
                Item {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    DragHandler { target: null; onActiveChanged: if (active) window.startSystemMove() }
                }
                LumenButton {
                    id: optionsButton; theme: window.theme; quiet: true; text: "···"; font.pixelSize: 23
                    hint: window.controller.text("Gesprächsoptionen und Verlauf")
                    visible: window.controller.conversation; onClicked: { options.open(); window.controller.load_sessions() }
                }
                LumenButton { theme: window.theme; quiet: true; text: "×"; font.pixelSize: 24; implicitWidth: 36; leftPadding: 6; rightPadding: 6; hint: window.controller.text("Suche schließen · Esc"); onClicked: window.hide() }
            }
            Rectangle {
                Layout.fillWidth: true; implicitHeight: inputRow.implicitHeight + 20
                color: Qt.alpha(window.theme.base, 0.85); radius: window.theme.radius + 6
                border.color: composer.activeFocus ? Qt.alpha(window.theme.accent, 0.8) : window.theme.border
                border.width: 1
                RowLayout {
                    id: inputRow
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    Image { source: "image://icons/system-search?" + window.theme.name; sourceSize: Qt.size(20, 20); Layout.preferredWidth: 20; Layout.preferredHeight: 20; Layout.leftMargin: 8; opacity: 0.7 }
                    ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: Math.max(40, Math.min(100, composer.implicitHeight))
                        clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        TextArea {
                            id: composer; objectName: "composer"
                            placeholderText: window.controller.text("Dateien, Apps oder eine Frage …")
                            text: window.controller.query; color: window.theme.text; placeholderTextColor: window.theme.muted
                            font.pixelSize: 17; selectByMouse: true; wrapMode: TextEdit.Wrap
                            padding: 8; background: null
                            Accessible.name: window.controller.text("Suchen oder mit Lumen sprechen")
                            onTextChanged: if (text !== window.controller.query) window.controller.set_query(text)
                            Keys.onPressed: function(event) {
                                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) { window.controller.submit(!!(event.modifiers & Qt.ControlModifier)); event.accepted = true }
                                else if (!window.controller.conversation && (event.key === Qt.Key_Down || event.key === Qt.Key_Up)) { window.controller.move_selection(event.key === Qt.Key_Down ? 1 : -1); event.accepted = true }
                            }
                        }
                    }
                    LumenButton {
                        theme: window.theme; quiet: !window.controller.voiceActive; primary: window.controller.voiceActive
                        icon.name: "audio-input-microphone"; implicitWidth: 40; leftPadding: 10; rightPadding: 10
                        hint: window.controller.text("Sprachgespräch starten oder beenden")
                        enabled: window.controller.voiceActive || !window.controller.busy
                        onClicked: window.controller.toggle_voice()
                    }
                    LumenButton {
                        theme: window.theme; primary: true; text: window.controller.busy ? "■" : "↑"
                        font.pixelSize: 22; implicitWidth: 42; implicitHeight: 42; leftPadding: 8; rightPadding: 8
                        hint: window.controller.busy ? window.controller.text("Abbrechen") : window.controller.text("Ausgewählten Treffer öffnen oder Nachricht senden")
                        onClicked: window.controller.busy ? window.controller.stop() : window.controller.submit(false)
                    }
                }
            }
            VoiceMeter { Layout.fillWidth: true; controller: window.controller; visible: window.controller.voiceActive }
            Label {
                Layout.fillWidth: true; visible: window.controller.error.length > 0
                text: window.controller.error; textFormat: Text.PlainText; wrapMode: Text.Wrap
                color: window.theme.light ? "#ab3539" : "#ffb9b4"
                font.pixelSize: 13
            }
            StackLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: window.controller.conversation ? 1 : 0
                ColumnLayout {
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: window.controller.query.trim() ? window.controller.text("Suchtreffer") : window.controller.text("Anwendungen"); color: window.theme.muted; font.pixelSize: 11; font.letterSpacing: 1.2; font.capitalization: Font.AllUppercase }
                        Item { Layout.fillWidth: true }
                        Label { text: results.count; color: window.theme.muted; font.pixelSize: 11 }
                    }
                    ListView {
                        id: results; objectName: "results"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        model: window.controller.results; currentIndex: window.controller.selectedIndex
                        spacing: 4; clip: true; boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: ItemDelegate {
                            id: result
                            required property var modelData
                            required property int index
                            width: ListView.view.width; height: 70
                            hoverEnabled: true
                            Accessible.name: modelData.title + ", " + modelData.detail
                            onClicked: window.controller.activate_result(index)
                            background: Rectangle {
                                radius: window.theme.radius
                                color: result.index === window.controller.selectedIndex ? Qt.alpha(window.theme.hover, 0.85) : result.hovered ? Qt.alpha(window.theme.hover, 0.4) : "transparent"
                                border.color: result.index === window.controller.selectedIndex ? Qt.alpha(window.theme.accent, 0.32) : "transparent"
                                Rectangle { visible: result.index === window.controller.selectedIndex; width: 3; height: 24; radius: 1.5; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; color: window.theme.accent }
                            }
                            contentItem: RowLayout {
                                spacing: 14
                                Rectangle {
                                    Layout.preferredWidth: 42; Layout.preferredHeight: 42; radius: 11
                                    color: Qt.alpha(window.theme.base, 0.65)
                                    Image { anchors.centerIn: parent; source: "image://icons/" + result.modelData.icon + "?" + window.theme.name; sourceSize: Qt.size(25, 25); width: 25; height: 25 }
                                }
                                ColumnLayout {
                                    spacing: 4; Layout.fillWidth: true
                                    Label { text: result.modelData.title; textFormat: Text.PlainText; color: window.theme.text; font.pixelSize: 15; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Label { text: result.modelData.detail; textFormat: Text.PlainText; color: window.theme.muted; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                }
                                Label { text: result.index === window.controller.selectedIndex ? "↵" : "›"; color: result.index === window.controller.selectedIndex ? window.theme.accent : window.theme.muted; font.pixelSize: 19; Layout.rightMargin: 10 }
                            }
                        }
                        Label { anchors.centerIn: parent; visible: results.count === 0; text: window.controller.text("Dateien, Apps oder eine Frage …"); color: window.theme.muted }
                    }
                }
                ScrollView {
                    id: conversation; objectName: "conversation"
                    readonly property Flickable scroller: contentItem as Flickable
                    property bool atYEnd: scroller ? scroller.contentY >= contentHeight - height - 50 : true
                    clip: true; contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ColumnLayout {
                        width: conversation.availableWidth; spacing: 18
                        Label { Layout.fillWidth: true; visible: window.controller.messages.length === 0 && !window.controller.busy; text: window.controller.text("Wobei kann ich dir helfen?"); color: window.theme.text; font.pixelSize: 24; font.weight: Font.Medium; wrapMode: Text.Wrap }
                        Repeater {
                            model: window.controller.messages
                            ColumnLayout {
                                id: messageRow
                                required property var modelData
                                Layout.fillWidth: true; spacing: 7
                                Label { text: messageRow.modelData.role === "user" ? window.controller.text("DU") : "LUMEN"; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.5; color: messageRow.modelData.role === "user" ? window.theme.muted : window.theme.accent }
                                TextArea {
                                    Layout.fillWidth: true; text: messageRow.modelData.body
                                    textFormat: TextEdit.RichText; readOnly: true; selectByMouse: true
                                    wrapMode: TextEdit.Wrap; color: window.theme.text; font.pixelSize: 15
                                    background: null; padding: 0
                                    onLinkActivated: function(link) { window.controller.open_link(link) }
                                }
                                Label { Layout.fillWidth: true; visible: messageRow.modelData.activity.length > 0; text: messageRow.modelData.activity + " …"; color: window.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                            }
                        }
                        Repeater {
                            model: window.controller.permissions
                            Rectangle {
                                id: permission
                                required property var modelData
                                Layout.fillWidth: true; implicitHeight: permissionBody.implicitHeight + 32
                                color: window.theme.button; radius: window.theme.radius; border.color: Qt.alpha(window.theme.accent, 0.45)
                                ColumnLayout {
                                    id: permissionBody
                                    anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 16; spacing: 10
                                    Label { text: window.controller.text("Aktion erlauben?"); color: window.theme.text; font.pixelSize: 15; font.weight: Font.Medium }
                                    Label { Layout.fillWidth: true; text: permission.modelData.label + "\n" + (permission.modelData.patterns || []).join("\n"); textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere; color: window.theme.muted; font.pixelSize: 12 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Ablehnen"); onClicked: window.controller.permission_reply(permission.modelData.id, false) }
                                        Item { Layout.fillWidth: true }
                                        LumenButton { theme: window.theme; primary: true; text: window.controller.text("Einmal erlauben"); onClicked: window.controller.permission_reply(permission.modelData.id, true) }
                                    }
                                }
                            }
                        }
                        Repeater { model: window.controller.questions; QuestionCard { required property var modelData; controller: window.controller; request: modelData; Layout.fillWidth: true } }
                        Flow {
                            Layout.fillWidth: true; spacing: 4; visible: window.controller.messages.length > 0 && !window.controller.busy
                            LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Kopieren"); onClicked: window.controller.copy_answer() }
                            LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Für mich speichern"); onClicked: window.controller.capture_knowledge(false) }
                            LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Merk dir das"); onClicked: window.controller.capture_knowledge(true) }
                        }
                        RowLayout {
                            Layout.fillWidth: true; visible: window.controller.busy
                            BusyIndicator { running: window.controller.busy; implicitWidth: 24; implicitHeight: 24 }
                            Label { text: window.controller.status; color: window.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        }
                        Item { Layout.preferredHeight: 10; Layout.fillWidth: true }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Qt.alpha(window.theme.border, 0.5) }
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 38; Layout.maximumHeight: 38
                LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Neue Suche"); enabled: !window.controller.busy; onClicked: window.controller.reset() }
                Item { Layout.fillWidth: true }
                Label { Layout.fillWidth: true; Layout.maximumWidth: 530; text: window.controller.conversation ? window.controller.status : window.controller.hint; textFormat: Text.PlainText; color: window.theme.muted; font.pixelSize: 11; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap }
            }
        }
    }
    Popup {
        id: options
        x: Math.max(20, window.width - width - 35); y: 68
        width: Math.min(360, window.width - 40); padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: window.theme.base; radius: window.theme.radius; border.color: window.theme.border }
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: window.controller.text("Gesprächsoptionen"); color: window.theme.text; font.pixelSize: 15; font.weight: Font.Medium }
            ComboBox { Layout.fillWidth: true; model: window.controller.sessions; textRole: "title"; valueRole: "id"; currentIndex: Math.max(0, window.controller.sessions.findIndex(function(s) { return s.id === window.controller.session })); enabled: !window.controller.busy; Accessible.name: window.controller.text("Gespräch auswählen"); onActivated: window.controller.select_session(currentValue) }
            ComboBox { Layout.fillWidth: true; model: [window.controller.text("Aufgaben erledigen"), window.controller.text("Lesen & prüfen")]; currentIndex: window.controller.mode === "plan" ? 1 : 0; enabled: !window.controller.busy; Accessible.name: window.controller.text("Arbeitsweise von Lumen"); onActivated: window.controller.set_mode(currentIndex ? "plan" : "build") }
            CheckBox { text: window.controller.text("Nicht mehr nachfragen"); checked: window.controller.autoApprove; onToggled: window.controller.set_auto_approve(checked); palette.windowText: window.theme.text; palette.highlight: window.theme.accent }
            Label { Layout.fillWidth: true; text: window.controller.text("Werkzeugfreigaben automatisch erlauben, auch Befehle und Dateiänderungen."); color: window.theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap }
            CheckBox { text: window.controller.text("Schritte erklären"); checked: window.controller.learn; onToggled: window.controller.set_learn(checked); palette.windowText: window.theme.text; palette.highlight: window.theme.accent }
            LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Einstellungen"); onClicked: window.controller.open_setup() }
        }
    }
}
