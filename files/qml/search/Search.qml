pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    required property var controller
    readonly property var theme: window.controller.theme
    width: 1240; height: 700
    minimumWidth: 620; minimumHeight: 560
    property int section: 0
    property bool resultDialogVisible: false
    // A remapped Wayland surface can receive the previous surface's focus-out first.
    property bool focusReceived: false
    readonly property bool homeVisible: !controller.conversation && !controller.query.trim() && section === 0
    onHomeVisibleChanged: if (homeVisible && visible && visibility === Window.Windowed && height > 700) height = 700
    visible: false; color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    title: "Lumen"
    font.family: window.theme.fontFamily
    palette.windowText: window.theme.text; palette.text: window.theme.text
    palette.base: window.theme.base; palette.button: window.theme.button
    palette.buttonText: window.theme.text; palette.highlight: window.theme.accent
    palette.highlightedText: window.theme.onAccent; palette.placeholderText: window.theme.muted
    onClosing: function(event) { event.accepted = false; hide() }
    onActiveChanged: {
        if (active) focusReceived = true
        else if (visible && focusReceived) Qt.callLater(function() {
            if (window.visible && window.focusReceived && !window.active && !attachments.visible && !window.resultDialogVisible) window.hide()
        })
    }
    onVisibleChanged: { if (!visible) { focusReceived = false; window.controller.hidden() } else { composer.forceActiveFocus(); window.controller.homeView.start() } }
    Shortcut { sequence: "Escape"; enabled: !options.opened; onActivated: window.hide() }
    Connections {
        target: window.controller
        function onHideRequested() { window.hide() }
        function onFocusRequested() { composer.forceActiveFocus() }
        function onQueryChanged() { if (composer.text !== window.controller.query) composer.text = window.controller.query }
        function onSelectionChanged() { results.positionViewAtIndex(window.controller.selectedIndex, ListView.Contain) }
        function onMessagesChanged() { conversation.updatePosition() }
    }
    Rectangle {
        anchors.fill: surface; anchors.margins: -5
        radius: surface.radius + 5; color: "#15000000"
    }
    Rectangle {
        id: surface
        anchors.fill: parent; anchors.margins: 10
        radius: window.theme.radius + 7
        color: window.theme.window; border.color: Qt.alpha(window.theme.border, 0.8)
        clip: true
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 24; spacing: 16
            Item {
                id: header
                Layout.fillWidth: true; Layout.preferredHeight: 38
                readonly property real navSpace: width - 2 * Math.max(brand.width, windowActions.width) - 24
                DragHandler { target: null; onActiveChanged: if (active) window.startSystemMove() }
                RowLayout {
                    id: brand
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; spacing: 10
                    Image { source: "image://icons/lumen?" + window.theme.name; sourceSize: Qt.size(21,21); Layout.preferredWidth: 21; Layout.preferredHeight: 21 }
                    Label { text: "Lumen"; color: window.theme.text; font.pixelSize: 16; font.weight: Font.DemiBold }
                }
                Frame {
                    id: navigation
                    objectName: "homeNavigation"
                    anchors.centerIn: parent; visible: implicitWidth <= header.navSpace; padding: 3
                    background: Rectangle { radius: 10; color: Qt.alpha(window.theme.base,0.65); border.color: Qt.alpha(window.theme.border,0.8) }
                    contentItem: RowLayout { spacing: 3
                        Repeater { model: [window.controller.text("Übersicht"),window.controller.text("Aufträge"),window.controller.text("Gespräche")]
                            LumenButton {
                                required property string modelData; required property int index
                                theme: window.theme; quiet: true; checkable: true; checked: !window.controller.conversation && window.section === index
                                implicitHeight: 34; font.pixelSize: Math.max(13,window.theme.fontSize-4); text: modelData
                                onClicked: { window.section=index; window.controller.browse(); if(index===2)window.controller.load_sessions() }
                            }
                        }
                    }
                }
                ComboBox {
                    anchors.centerIn: parent; visible: !navigation.visible; width: Math.min(190,header.navSpace)
                    model: [window.controller.text("Übersicht"),window.controller.text("Aufträge"),window.controller.text("Gespräche")]
                    currentIndex: window.section; Accessible.name: window.controller.text("Ansicht")
                    onActivated: { window.section=currentIndex;window.controller.browse();if(currentIndex===2)window.controller.load_sessions() }
                }
                RowLayout {
                    id: windowActions
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                    LumenButton { objectName: "openDetails"; theme: window.theme; quiet: true; visible: window.controller.sharedConversation; icon.name: "window-new"; icon.width: 16; icon.height: 16; implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8; hint: window.controller.text("Detailansicht"); onClicked: window.controller.expand() }
                    LumenButton { theme: window.theme; quiet: true; icon.name: "configure"; icon.width: 16; icon.height: 16; implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8; hint: window.controller.text("Einstellungen"); onClicked: window.controller.open_setup() }
                    LumenButton { theme: window.theme; quiet: true; visible: window.width>=800; text: "−"; implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8; hint: window.controller.text("Minimieren"); onClicked: window.showMinimized() }
                    LumenButton { theme: window.theme; quiet: true; visible: window.width>=800; text: "□"; implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8; hint: window.controller.text("Maximieren oder wiederherstellen"); onClicked: window.visibility === Window.Maximized ? window.showNormal() : window.showMaximized() }
                    LumenButton {
                        id: optionsButton; theme: window.theme; quiet: true; text: "···"; font.pixelSize: 23
                        implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8
                        hint: window.controller.text("Gesprächsoptionen und Verlauf")
                        visible: window.controller.conversation; onClicked: { options.open(); window.controller.load_sessions() }
                    }
                    LumenButton { theme: window.theme; quiet: true; text: "×"; font.pixelSize: 20; implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8; hint: window.controller.text("Lumen ausblenden · Esc"); onClicked: window.hide() }
                }
            }
            Rectangle {
                Layout.fillWidth: true; Layout.leftMargin: window.homeVisible && window.width>700 ? 14 : 0; Layout.rightMargin: Layout.leftMargin
                implicitHeight: inputRow.implicitHeight + (window.homeVisible ? 34 : 20)
                color: Qt.alpha(window.theme.base, 0.85); radius: window.homeVisible ? 17 : window.theme.radius + 6
                border.color: composer.activeFocus ? Qt.alpha(window.theme.accent, 0.8) : window.theme.border
                border.width: 1
                RowLayout {
                    id: inputRow
                    anchors.fill: parent; anchors.margins: 14; spacing: 10
                    Image { source: "image://icons/system-search?" + window.theme.name + "&tint=" + encodeURIComponent(window.theme.muted); sourceSize: Qt.size(20, 20); Layout.preferredWidth: 20; Layout.preferredHeight: 20; Layout.leftMargin: 8; opacity: 0.7 }
                    ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: Math.max(40, Math.min(100, composer.implicitHeight))
                        clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        TextArea {
                            id: composer; objectName: "composer"
                            placeholderText: window.controller.text(window.homeVisible ? "Was möchtest du erledigen?" : "Dateien, Apps oder eine Frage …")
                            text: window.controller.query; color: window.theme.text; placeholderTextColor: window.theme.muted
                            font.pixelSize: window.homeVisible ? Math.max(14,window.theme.fontSize-1) : window.theme.fontSize; selectByMouse: true; wrapMode: TextEdit.Wrap
                            padding: 8; background: null
                            Accessible.name: window.controller.text("Suchen oder mit Lumen sprechen")
                            onTextChanged: if (text !== window.controller.query) window.controller.set_query(text)
                            ContextMenu.menu: Menu {
                                MenuItem { text: qsTr("Copy"); onTriggered: composer.copy() }
                                MenuItem { text: qsTr("Cut"); onTriggered: composer.cut() }
                                MenuItem { text: qsTr("Paste"); enabled: !window.controller.clipboard_protected(); onTriggered: { if (!window.controller.paste_image()) composer.paste() } }
                            }
                            Keys.onPressed: function(event) {
                                if (event.matches(StandardKey.Paste) && window.controller.paste_image()) { event.accepted = true; return }
                                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) { window.controller.submit(!!(event.modifiers & Qt.ControlModifier)); event.accepted = true }
                                else if (!window.controller.conversation && (event.key === Qt.Key_Down || event.key === Qt.Key_Up)) { window.controller.move_selection(event.key === Qt.Key_Down ? 1 : -1); event.accepted = true }
                            }
                        }
                    }
                    LumenButton { theme: window.theme; quiet: true; icon.name: "mail-attachment"; icon.width: 16; icon.height: 16; implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8; hint: window.controller.text("Dateien hinzufügen"); enabled: !window.controller.busy; onClicked: attachments.open() }
                    LumenButton {
                        theme: window.theme; quiet: !window.controller.voiceActive; primary: window.controller.voiceActive
                        icon.name: "audio-input-microphone"; icon.width: 16; icon.height: 16; implicitWidth: 32; implicitHeight: 32; leftPadding: 8; rightPadding: 8
                        hint: window.controller.text("Sprachgespräch starten oder beenden")
                        enabled: window.controller.voiceActive || !window.controller.busy
                        onClicked: window.controller.toggle_voice()
                    }
                    LumenButton {
                        theme: window.theme; primary: true; text: window.controller.busy ? "■" : "↑"
                        background: Rectangle { radius: 22; color: window.theme.accent; border.color: parent.activeFocus ? window.theme.text : "transparent" }
                        font.pixelSize: 22; implicitWidth: 42; implicitHeight: 42; leftPadding: 8; rightPadding: 8
                        hint: window.controller.busy ? window.controller.text("Abbrechen") : window.controller.text("Ausgewählten Treffer öffnen oder Nachricht senden")
                        onClicked: window.controller.busy ? window.controller.stop() : window.controller.submit(false)
                    }
                }
            }
            RowLayout { Layout.fillWidth: true; visible: window.controller.attachments.length>0
                Label { Layout.fillWidth: true; text: window.controller.text("Angehängte Dateien") + " · " + window.controller.attachments.length; color: window.theme.muted; font.pixelSize: window.theme.fontSize-2 }
                LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Entfernen"); enabled: !window.controller.busy; onClicked: window.controller.clear_attachments() }
            }
            VoiceMeter { Layout.fillWidth: true; controller: window.controller; visible: window.controller.voiceActive }
            LumenButton {
                theme: window.theme; visible: window.controller.voiceSetupRequired
                text: window.controller.text("Sprache einrichten")
                onClicked: window.controller.open_voice_setup()
            }
            Label {
                Layout.fillWidth: true; visible: window.controller.error.length > 0
                text: window.controller.error; textFormat: Text.PlainText; wrapMode: Text.Wrap
                color: window.theme.light ? "#ab3539" : "#ffb9b4"
                font.pixelSize: 13
            }
            StackLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: window.controller.conversation ? 1 : window.section === 1 ? 2 : window.section === 2 ? 3 : window.homeVisible ? 4 : 0
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
                                    Label { text: result.modelData.title; textFormat: Text.PlainText; color: window.theme.text; font.pixelSize: window.theme.fontSize - 1; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Label { text: result.modelData.detail; textFormat: Text.PlainText; color: window.theme.muted; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                }
                                Label { text: result.index === window.controller.selectedIndex ? "↵" : "›"; color: result.index === window.controller.selectedIndex ? window.theme.accent : window.theme.muted; font.pixelSize: 19; Layout.rightMargin: 10 }
                            }
                        }
                        Label { anchors.centerIn: parent; visible: results.count === 0; text: window.controller.text("Dateien, Apps oder eine Frage …"); color: window.theme.muted }
                    }
                }
                Item {
                    ScrollView {
                        anchors.fill: parent
                        id: conversation; objectName: "conversation"
                        readonly property Flickable scroller: contentItem as Flickable
                    property bool following: true
                    property string lastUserKey: ""
                    property string firstKey: ""
                    readonly property real scrollEnd: Math.max(0, contentHeight - availableHeight)
                    readonly property bool newerBelow: !following && scroller !== null && scrollEnd - scroller.contentY > 48
                    function goToLatest() {
                        if (!scroller) return
                        scroller.cancelFlick()
                        following = true
                        composer.forceActiveFocus()
                    }
                    function updatePosition() {
                        const rows = window.controller.messages
                        let userKey = ""
                        for (let i = rows.length - 1; i >= 0; --i) {
                            if (rows[i].role === "user") { userKey = String(rows[i].key); break }
                        }
                        const first = rows.length ? String(rows[0].key) : ""
                        // A submitted follow-up resumes following, even after reading older text.
                        if (first !== firstKey || userKey !== lastUserKey || !rows.length) following = true
                        firstKey = first
                        lastUserKey = userKey
                        while (messageSlots.count < rows.length) messageSlots.append({slot: messageSlots.count})
                        if (messageSlots.count > rows.length) messageSlots.remove(rows.length, messageSlots.count - rows.length)
                    }
                    Component.onCompleted: updatePosition()
                    ListModel { id: messageSlots }
                    Timer {
                        id: followPosition
                        interval: 16; repeat: true
                        running: conversation.visible && conversation.following && conversation.scroller !== null
                                 && !conversation.scroller.moving && !conversationBar.pressed
                                 && Math.abs(conversation.scrollEnd - conversation.scroller.contentY) > 0.5
                        onTriggered: {
                            const y = conversation.scroller.contentY
                            const remaining = conversation.scrollEnd - y
                            // Chase the current end; streaming never restarts an animation.
                            conversation.scroller.contentY = Math.abs(remaining) < 1 ? conversation.scrollEnd : y + remaining * 0.45
                        }
                    }
                    WheelHandler {
                        target: null
                        onWheel: function(event) {
                            const delta = event.pixelDelta.y || event.angleDelta.y
                            if (delta > 0) conversation.following = false
                            else if (delta < 0) wheelFinished.restart()
                            event.accepted = false
                        }
                    }
                    Timer {
                        id: wheelFinished; interval: 160
                        onTriggered: if (conversation.scroller && conversation.scrollEnd - conversation.scroller.contentY < 24) conversation.following = true
                    }
                    Connections {
                        target: conversation.scroller
                        function onMovementStarted() { conversation.following = false }
                        function onMovementEnded() {
                            conversation.following = conversation.scrollEnd - conversation.scroller.contentY < 24
                        }
                    }
                    ScrollBar.vertical: ScrollBar {
                        id: conversationBar; policy: ScrollBar.AsNeeded
                        onPressedChanged: {
                            if (pressed) conversation.following = false
                            else if (conversation.scroller) conversation.following = conversation.scrollEnd - conversation.scroller.contentY < 24
                        }
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Up || event.key === Qt.Key_PageUp || event.key === Qt.Key_Home) conversation.following = false
                        else if (event.key === Qt.Key_End) conversation.following = true
                    }
                        clip: true; contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ColumnLayout {
                            width: Math.min(960, conversation.availableWidth); x: (conversation.availableWidth - width) / 2; spacing: window.theme.spacing + 8
                            Label { Layout.fillWidth: true; visible: window.controller.messages.length === 0 && !window.controller.busy; text: window.controller.text("Wobei kann ich dir helfen?"); color: window.theme.text; font.pixelSize: 24; font.weight: Font.Medium; wrapMode: Text.Wrap }
                            Repeater {
                                id: messageRepeater
                                model: messageSlots
                                Frame {
                                    id: messageRow
                                    objectName: "messageBubble"
                                    required property int slot
                                    readonly property var modelData: window.controller.messages[slot] || ({role: "", body: "", blocks: [], key: "", activity: "", actions: false, presentation: false})
                                    readonly property bool userMessage: modelData.role === "user"
                                    Layout.fillWidth: true
                                    Layout.maximumWidth: userMessage ? Math.min(960, conversation.availableWidth) * 8 / 9 : 960
                                    Layout.alignment: userMessage ? Qt.AlignRight : Qt.AlignLeft
                                    leftPadding: userMessage ? 18 : 22; rightPadding: leftPadding; topPadding: userMessage ? 14 : 20; bottomPadding: topPadding
                                    background: Rectangle {
                                        radius: 14
                                        color: messageRow.userMessage ? Qt.alpha(window.theme.accent, 0.07) : "transparent"
                                        border.width: messageRow.userMessage ? 1 : 0
                                        border.color: Qt.alpha(window.theme.border, 0.6)
                                    }
                                    contentItem: ColumnLayout {
                                        spacing: messageRow.userMessage ? 8 : 16
                                        Label { visible: messageRow.userMessage; text: window.controller.text("DU"); font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 1; color: window.theme.muted }
                                        RowLayout {
                                            visible: !messageRow.userMessage; spacing: 9
                                            Image { source: "image://icons/lumen?" + window.theme.name; sourceSize: Qt.size(26, 26); Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
                                            Label { text: "Lumen"; color: window.theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
                                            Item { Layout.fillWidth: true }
                                        }
                                        TextArea {
                                            objectName: "messageBody"
                                            visible: messageRow.userMessage
                                            Layout.fillWidth: true; text: messageRow.modelData.body
                                            textFormat: TextEdit.RichText; readOnly: true; selectByMouse: true
                                            wrapMode: TextEdit.Wrap; color: window.theme.text; font.pixelSize: window.theme.fontSize
                                            background: null; padding: 0
                                            onLinkActivated: function(link) { window.controller.open_link(link) }
                                        }
                                        AnswerBlocks {
                                            visible: !messageRow.userMessage
                                            Layout.fillWidth: true
                                            blocks: messageRow.modelData.blocks
                                            theme: window.theme; controller: window.controller
                                            messageKey: messageRow.modelData.key
                                        }
                                        Loader {
                                            Layout.fillWidth: true
                                            active: messageRow.modelData.presentation === true
                                            visible: active
                                            sourceComponent: ResultView {
                                                view: window.controller.richView; theme: window.theme
                                                onDialogVisibleChanged: window.resultDialogVisible = dialogVisible
                                                Component.onDestruction: window.resultDialogVisible = false
                                            }
                                        }
                                        Label { Layout.fillWidth: true; visible: messageRow.modelData.activity.length > 0; text: messageRow.modelData.activity + " …"; color: window.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                                        ColumnLayout {
                                            objectName: "answerActions"
                                            Layout.fillWidth: true; spacing: 8
                                            visible: messageRow.modelData.actions && !window.controller.busy
                                            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.alpha(window.theme.border, 0.5) }
                                            Flow {
                                                Layout.fillWidth: true; spacing: 4
                                                LumenButton {
                                                    id: copyAnswer; objectName: "copyAnswer"
                                                    property bool copied: false
                                                    theme: window.theme; quiet: true
                                                    icon.name: copied ? "emblem-ok-symbolic" : "edit-copy"
                                                    text: window.controller.text(copied ? "Kopiert" : "Kopieren")
                                                    onClicked: { window.controller.copy_answer(); copied = true; copiedReset.restart() }
                                                    Timer { id: copiedReset; interval: 1800; onTriggered: copyAnswer.copied = false }
                                                }
                                                LumenButton { objectName: "saveAnswer"; theme: window.theme; quiet: true; icon.name: "bookmark-new"; text: window.controller.text("Für mich speichern"); onClicked: window.controller.capture_knowledge(false) }
                                                LumenButton { objectName: "rememberAnswer"; theme: window.theme; quiet: true; icon.name: "view-history"; text: window.controller.text("Merk dir das"); onClicked: window.controller.capture_knowledge(true) }
                                            }
                                        }
                                    }
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
                                        Label { text: window.controller.text("Aktion erlauben?"); color: window.theme.text; font.pixelSize: window.theme.fontSize - 1; font.weight: Font.Medium }
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
                            RowLayout {
                                Layout.fillWidth: true; visible: window.controller.busy
                                BusyIndicator { running: window.controller.busy; implicitWidth: 24; implicitHeight: 24 }
                                Label { text: window.controller.status; color: window.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                            Item { Layout.preferredHeight: 10; Layout.fillWidth: true }
                        }
                    }
                    LumenButton {
                        objectName: "latestMessage"
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                        visible: conversation.newerBelow
                        theme: window.theme
                        icon.name: "go-down-symbolic"
                        text: window.controller.text("Zur neuesten Nachricht")
                        onClicked: conversation.goToLatest()
                    }
                }
                ScrollView { id: tasksPage; contentWidth: availableWidth; clip: true
                    HomeList { width: tasksPage.availableWidth; controller: window.controller; kind: "tasks"; limit: 80; onShowAll: window.controller.homeView.open_page("tasks") }
                }
                ScrollView { id: sessionsPage; contentWidth: availableWidth; clip: true
                    ColumnLayout { width: sessionsPage.availableWidth
                        LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Gespräch fortsetzen"); visible: window.controller.messages.length>0; onClicked: window.controller.show_conversation() }
                        HomeList { Layout.fillWidth: true; controller: window.controller; kind: "sessions"; limit: 5; onShowAll: limit += 5 }
                    }
                }
                ScrollView { id: homePage; contentWidth: availableWidth; clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    HomeOverview { width: homePage.availableWidth; controller: window.controller; onShowTasks: window.section=1 }
                }
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Qt.alpha(window.theme.border, 0.5) }
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 38; Layout.maximumHeight: 38
                Rectangle { visible: window.homeVisible; width: 6; height: 6; radius: 3; color: window.theme.accent }
                Label { visible: window.homeVisible; text: window.controller.homeView.status; color: window.theme.text; font.pixelSize: Math.max(11,window.theme.fontSize-6) }
                Label { visible: window.homeVisible && window.width>800; text: window.controller.homeView.detail; color: window.theme.muted; font.pixelSize: Math.max(11,window.theme.fontSize-6) }
                LumenButton { visible: !window.homeVisible; theme: window.theme; quiet: true; text: window.controller.text("Neue Suche"); enabled: !window.controller.busy; onClicked: window.controller.reset() }
                Item { Layout.fillWidth: true }
                LumenButton { visible: window.homeVisible; theme: window.theme; quiet: true; font.pixelSize: Math.max(11,window.theme.fontSize-6); text: window.controller.text("Systemstatus") + " →"; onClicked: window.controller.homeView.open_page("system") }
                Label { visible: !window.homeVisible; Layout.fillWidth: true; Layout.maximumWidth: 530; text: window.controller.conversation ? (window.controller.execution === "server" ? window.controller.serverOrigin + " · " : "") + window.controller.status : window.controller.hint; textFormat: Text.PlainText; color: window.theme.muted; font.pixelSize: 11; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap }
            }
        }
    }
    FileDialog { id: attachments; title: window.controller.text("Dateien hinzufügen"); fileMode: FileDialog.OpenFiles; onAccepted: window.controller.add_attachments(selectedFiles.map(function(url) { return url.toString() })) }
    Popup {
        id: options
        x: Math.max(20, window.width - width - 35); y: 68
        width: Math.min(360, window.width - 40); padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: window.theme.base; radius: window.theme.radius; border.color: window.theme.border }
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: window.controller.text("Gesprächsoptionen"); color: window.theme.text; font.pixelSize: window.theme.fontSize - 1; font.weight: Font.Medium }
            ComboBox { Layout.fillWidth: true; model: window.controller.sessions; textRole: "title"; valueRole: "id"; currentIndex: Math.max(0, window.controller.sessions.findIndex(function(s) { return s.id === window.controller.session })); enabled: !window.controller.busy; Accessible.name: window.controller.text("Gespräch auswählen"); onActivated: window.controller.select_session(currentValue) }
            ComboBox { objectName: "executionChoice"; Layout.fillWidth: true; model: [window.controller.text("Dieses Gerät"), window.controller.text("Lumen Server · Textgespräch")]; currentIndex: window.controller.execution === "server" ? 1 : 0; enabled: !window.controller.busy; Accessible.name: window.controller.text("Ausführung"); onActivated: window.controller.set_execution(currentIndex ? "server" : "local") }
            ComboBox { objectName: "serverModelChoice"; visible: window.controller.execution === "server"; Layout.fillWidth: true; model: window.controller.serverModels; textRole: "name"; valueRole: "id"; enabled: !window.controller.busy; Accessible.name: window.controller.text("Servermodell"); onActivated: window.controller.set_server_model(currentValue) }
            Label { visible: window.controller.execution === "server"; Layout.fillWidth: true; text: window.controller.serverOrigin + "\n" + window.controller.text("Verwendet das auf dem Server konfigurierte Modell. Nur deine Nachrichten werden übertragen."); color: window.theme.muted; wrapMode: Text.Wrap }
            LumenButton { visible: window.controller.execution === "server"; theme: window.theme; quiet: true; text: window.controller.text("Serververbindung prüfen"); onClicked: window.controller.check_server() }
            ComboBox { Layout.fillWidth: true; model: [window.controller.text("Aufgaben erledigen"), window.controller.text("Lesen & prüfen")]; currentIndex: window.controller.mode === "plan" ? 1 : 0; enabled: !window.controller.busy && window.controller.execution === "local"; Accessible.name: window.controller.text("Arbeitsweise von Lumen"); onActivated: window.controller.set_mode(currentIndex ? "plan" : "build") }
            ComboBox { objectName: "personaChoice"; Layout.fillWidth: true; model: window.controller.personaOptions; textRole: "title"; valueRole: "id"; currentIndex: Math.max(0, window.controller.personaOptions.findIndex(function(p) { return p.id === window.controller.persona })); enabled: !window.controller.busy && window.controller.execution === "local"; Accessible.name: window.controller.text("Persönlichkeit für dieses Gespräch"); onActivated: window.controller.set_persona(currentValue) }
            CheckBox { enabled: window.controller.execution === "local"; text: window.controller.text("Nicht mehr nachfragen"); checked: window.controller.autoApprove; onToggled: window.controller.set_auto_approve(checked); palette.windowText: window.theme.text; palette.highlight: window.theme.accent }
            Label { Layout.fillWidth: true; text: window.controller.text("Werkzeugfreigaben automatisch erlauben, auch Befehle und Dateiänderungen."); color: window.theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap }
            CheckBox { text: window.controller.text("Schritte erklären"); checked: window.controller.learn; onToggled: window.controller.set_learn(checked); palette.windowText: window.theme.text; palette.highlight: window.theme.accent }
            LumenButton { theme: window.theme; quiet: true; text: window.controller.text("Einstellungen"); onClicked: window.controller.open_setup() }
        }
    }
}
