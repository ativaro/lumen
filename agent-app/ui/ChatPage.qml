// Chat page — modern messenger-style bubbles with live streaming.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "Theme.js" as Theme
import "Paths.js" as Paths

Item {
    id: page

    property var executor
    property bool busy: false
    // messages: [{ role: "user"|"assistant", text: "..." }]
    property var messages: []
    property string live: ""

    signal sendRequested(string text)

    function shq(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    function send() {
        var q = input.text.trim();
        if (q === "" || busy) return;
        busy = true;
        var m = messages.slice();
        m.push({ role: "user", text: q });
        messages = m;
        input.text = "";
        live = "";
        var bridge = Paths.binDir + "/lumen-agent-bridge";
        executor.stream(bridge + " chat " + shq(q), "chat");
    }

    function clearChat() {
        messages = [];
        live = "";
    }

    Connections {
        target: page.executor
        function onStreamData(tag, text) {
            if (tag !== "chat") return;
            page.live += text;
        }
        function onStreamDone(tag, rc) {
            if (tag !== "chat") return;
            var m = page.messages.slice();
            m.push({ role: "assistant", text: page.live.trim() });
            page.messages = m;
            page.live = "";
            page.busy = false;
        }
    }

    Item {
        anchors.fill: parent

        // ---- message list -----------------------------------------------
        ListView {
            id: list
            anchors { left: parent.left; right: parent.right; top: parent.top; bottom: composer.top }
            clip: true
            topMargin: 18
            bottomMargin: 18
            spacing: 16
            model: page.messages
            boundsBehavior: Flickable.StopAtBounds

            delegate: Item {
                width: list.width
                height: bubble.implicitHeight

                readonly property bool isUser: modelData.role === "user"

                Rectangle {
                    id: bubble
                    // user bubbles right-aligned, assistant left-aligned
                    x: isUser ? parent.width - width - 22 : 22
                    width: Math.min(parent.width * 0.78, Math.max(implicitText, 180))
                    implicitHeight: txt.implicitHeight + 26
                    radius: Theme.radius
                    color: isUser ? Theme.userBubble : Theme.surfaceAlt
                    border.width: isUser ? 0 : 1
                    border.color: Theme.border

                    // assistant accent stripe
                    Rectangle {
                        visible: !isUser
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                        width: 3
                        radius: 2
                        color: Theme.accent
                    }

                    property real implicitText: txt.implicitWidth + 34

                    QQC2.Label {
                        id: txt
                        anchors {
                            left: parent.left; right: parent.right; top: parent.top
                            leftMargin: isUser ? 15 : 18
                            rightMargin: 15
                            topMargin: 13
                        }
                        text: modelData.text
                        textFormat: Text.MarkdownText
                        wrapMode: Text.Wrap
                        color: Theme.text
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize + 0.5
                        lineHeight: 1.15
                    }
                }
            }

            // streaming bubble
            footer: Item {
                width: list.width
                height: page.live !== "" ? liveBubble.height + 16 : 0
                Rectangle {
                    id: liveBubble
                    x: 22
                    width: list.width * 0.78
                    height: liveTxt.implicitHeight + 26
                    radius: Theme.radius
                    color: Theme.surfaceAlt
                    border.width: 1
                    border.color: Theme.border

                    Rectangle {
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                        width: 3; radius: 2; color: Theme.accent
                    }

                    QQC2.Label {
                        id: liveTxt
                        anchors { left: parent.left; top: parent.top; right: parent.right; leftMargin: 18; rightMargin: 15; topMargin: 13 }
                        text: page.live
                        textFormat: Text.MarkdownText
                        wrapMode: Text.Wrap
                        color: Theme.text
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize + 0.5
                    }
                }
            }

            // auto-scroll to bottom when content changes
            onCountChanged: Qt.callLater(() => positionViewAtEnd())
            Connections {
                target: page
                function onLiveChanged() { Qt.callLater(() => list.positionViewAtEnd()) }
            }
        }

        // empty state — centered overlay above the list
        Column {
            id: emptyState
            visible: page.messages.length === 0 && page.live === ""
            anchors.centerIn: list
            anchors.verticalCenterOffset: -20
            spacing: 10
            width: Math.min(parent.width - 60, 420)

            Kirigami.Icon {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "opencode"
                width: 56; height: 56
                opacity: 0.65
            }
            QQC2.Label {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: "Wie kann ich helfen?"
                color: Theme.text
                font.pointSize: Kirigami.Theme.defaultFont.pointSize + 4
                font.bold: true
            }
            QQC2.Label {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: "Frag opencode zu Code, System oder KDE"
                color: Theme.textFaint
            }
        }

        // ---- composer ---------------------------------------------------
        Rectangle {
            id: composer
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 74
            color: Theme.surface
            Rectangle {
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: 1
                color: Theme.border
            }

            Rectangle {
                id: field
                anchors { fill: parent; leftMargin: 18; rightMargin: 18; topMargin: 13; bottomMargin: 13 }
                radius: Theme.radius
                color: Theme.surfaceAlt
                border.width: 1
                border.color: input.activeFocus ? Theme.accent : Theme.border
                Behavior on border.color { ColorAnimation { duration: 120 } }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 6
                    spacing: 8

                    QQC2.TextField {
                        id: input
                        Layout.fillWidth: true
                        placeholderText: "Nachricht an opencode …"
                        color: Theme.text
                        placeholderTextColor: Theme.textFaint
                        background: null
                        enabled: !page.busy
                        onAccepted: page.send()
                    }

                    QQC2.BusyIndicator {
                        visible: page.busy
                        running: page.busy
                        Layout.preferredWidth: 22; Layout.preferredHeight: 22
                    }

                    Rectangle {
                        Layout.preferredWidth: 38; Layout.preferredHeight: 38
                        radius: Theme.radiusSm
                        color: (input.text.trim() !== "" && !page.busy) ? Theme.accent : Theme.elevated
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Kirigami.Icon {
                            anchors.centerIn: parent
                            source: "document-send"
                            width: 20; height: 20
                            color: (input.text.trim() !== "" && !page.busy) ? "#06202e" : Theme.textFaint
                        }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: page.send() }
                    }

                    Rectangle {
                        Layout.preferredWidth: 38; Layout.preferredHeight: 38
                        radius: Theme.radiusSm
                        color: hoverClear.hovered ? Theme.elevated : "transparent"
                        Kirigami.Icon {
                            anchors.centerIn: parent
                            source: "edit-clear"
                            width: 18; height: 18
                            color: Theme.textDim
                        }
                        HoverHandler { id: hoverClear; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: page.clearChat() }
                    }
                }
            }
        }
    }
}
