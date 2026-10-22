// SPDX-FileCopyrightText: 2013 Heena Mahour <heena393@gmail.com>
// SPDX-FileCopyrightText: 2013 Sebastian Kügler <sebas@kde.org>
// SPDX-FileCopyrightText: 2016 Kai Uwe Broulik <kde@privat.broulik.de>
// SPDX-License-Identifier: GPL-2.0-or-later
// Keep KDE's full and compact presenters separate so their native menus retain ownership.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import QtQml.Models
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.private.keyboardindicator as KeyboardIndicator
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import plasma.applet.org.kde.plasma.appmenu as AppMenu

PlasmoidItem {
    id: root
    objectName: "lumenAppMenu"
    readonly property bool compactView: Plasmoid.configuration.compactView
    readonly property int widthBudget: Math.max(40, Plasmoid.configuration.widthBudget)
    readonly property bool menusAvailable: appMenuModel.menuAvailable && windowState.hasMenu && !windowState.fullScreen
    readonly property bool menuBar: windowState.activeWindow !== null && windowState.maximized && !windowState.fullScreen
    readonly property bool available: compactView ? menusAvailable && !menuBar : menuBar
    readonly property string appName: windowState.appName || i18n("Anwendung")
    property bool overflowOpen: false
    onAvailableChanged: if (!available && fullRepresentationItem) fullRepresentationItem.closeMenus()
    onMenuBarChanged: if (!compactView && fullRepresentationItem) fullRepresentationItem.fitIslands()
    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => disconnectSource(source)
    }
    Timer { id: fitTimer; interval: 200; onTriggered: runner.connectSource("/usr/bin/lumen-panel --topbar-fit") }
    Plasmoid.constraintHints: Plasmoid.CanFillArea
    Plasmoid.status: !available ? PlasmaCore.Types.HiddenStatus
        : Plasmoid.currentIndex >= 0 ? PlasmaCore.Types.NeedsAttentionStatus : PlasmaCore.Types.ActiveStatus
    preferredRepresentation: compactView ? compactRepresentation : fullRepresentation
    preloadFullRepresentation: true
    onCompactViewChanged: Plasmoid.view = compactView ? 1 : 0
    Component.onCompleted: { Plasmoid.model = appMenuModel; Plasmoid.view = compactView ? 1 : 0; }
    WindowMenuState {
        id: windowState
        screenGeometry: root.screenGeometry
        holdActiveWindow: root.overflowOpen || Plasmoid.currentIndex >= 0 || Plasmoid.containment.status === PlasmaCore.Types.AcceptingInputStatus
    }
    AppMenu.AppMenuModel {
        id: appMenuModel
        containmentStatus: root.overflowOpen || Plasmoid.currentIndex >= 0 ? PlasmaCore.Types.AcceptingInputStatus : Plasmoid.containment.status
        screenGeometry: root.screenGeometry
        allScreens: false
        onRequestActivateIndex: index => Plasmoid.requestActivateIndex(index)
    }
    // Clients may hide their own menubar even for normal windows.
    compactRepresentation: PlasmaComponents.ToolButton {
        objectName: "compactApplicationMenu"
        icon.name: "application-menu"
        Layout.fillWidth: false
        Layout.fillHeight: false
        Layout.minimumWidth: implicitWidth
        Layout.maximumWidth: implicitWidth
        text: root.appName
        display: PlasmaComponents.AbstractButton.IconOnly
        enabled: root.available
        down: Plasmoid.currentIndex >= 0
        Accessible.name: i18n("Menü von %1 öffnen", root.appName)
        onPressed: Plasmoid.trigger(this, 0)
    }
    fullRepresentation: RowLayout {
        id: buttons
        function closeMenus() { overflowMenu.close(); windowMenu.close(); }
        function fitIslands() {
            if (root.compactView) return;
            const requested = root.menuBar ? Math.ceil(nativeWidth + 12) : 0;
            if (Plasmoid.configuration.requiredWidth !== requested) {
                Plasmoid.configuration.requiredWidth = requested;
                fitTimer.restart();
            }
        }
        onNativeWidthChanged: fitIslands()
        property int measureRevision: 0
        property int delegateRevision: 0
        readonly property real nativeWidth: {
            measureRevision;
            let result = root.menusAvailable ? 0 : 40;
            for (let i = 0; i < measurements.count; ++i) {
                const item = measurements.objectAt(i);
                if (item && item.activeMenu !== "" && (item.activeActions?.visible ?? false)) result += item.naturalWidth;
            }
            return result;
        }
        readonly property bool showTitle: nativeWidth + Math.min(120, title.implicitWidth) + 12 <= root.widthBudget
        readonly property real requiredWidth: Math.min(root.widthBudget, nativeWidth + (showTitle ? Math.min(120, title.implicitWidth) + 12 : 0))
        readonly property real menuWidth: requiredWidth
        readonly property int overflowIndex: {
            measureRevision;
            if (nativeWidth <= root.widthBudget) return measurements.count;
            let used = 40;
            for (let i = 0; i < measurements.count; ++i) {
                const item = measurements.objectAt(i);
                if (!item || item.activeMenu === "" || !(item.activeActions?.visible ?? false)) continue;
                used += item.naturalWidth;
                if (used > root.widthBudget) return i;
            }
            return measurements.count;
        }
        Layout.minimumWidth: menuWidth
        Layout.maximumWidth: menuWidth
        Layout.minimumHeight: implicitHeight
        spacing: 0
        Binding { target: Plasmoid; property: "buttonGrid"; value: buttons }
        PlasmaComponents.Label {
            id: title
            text: root.appName
            font.weight: Font.Medium
            visible: buttons.showTitle
            Layout.maximumWidth: 120
            Layout.rightMargin: 12
            elide: Text.ElideRight
        }
        Instantiator {
            id: measurements
            model: root.menusAvailable && appMenuModel.visible ? appMenuModel : null
            onObjectAdded: Qt.callLater(function() { if (buttons) buttons.measureRevision++; })
            onObjectRemoved: Qt.callLater(function() { if (buttons) buttons.measureRevision++; })
            delegate: QtObject {
                required property int index
                required property string activeMenu
                required property PlasmaCore.Action activeActions
                readonly property real naturalWidth: Math.ceil(metrics.advanceWidth) + 16
                property TextMetrics metrics: TextMetrics { font: Kirigami.Theme.defaultFont; text: activeMenu.replace(/&(.)/g, "$1") }
            }
        }
        Repeater {
            id: menus
            onItemAdded: Qt.callLater(function() { if (buttons) buttons.delegateRevision++; })
            onItemRemoved: Qt.callLater(function() { if (buttons) buttons.delegateRevision++; })
            model: root.menusAvailable && appMenuModel.visible ? appMenuModel : null
            AppMenu.MenuDelegate {
                required property int index
                required property string activeMenu
                required property PlasmaCore.Action activeActions
                readonly property int buttonIndex: index
                readonly property real naturalWidth: { if (!buttons || !measurements) return 40; buttons.measureRevision; return measurements.objectAt(index)?.naturalWidth ?? 40; }
                Layout.minimumWidth: naturalWidth
                Layout.maximumWidth: naturalWidth
                objectName: "applicationMenuButton" + index
                Layout.fillHeight: true
                leftPadding: 8; rightPadding: 8
                text: activeMenu
                visible: index < buttons.overflowIndex && text !== "" && (activeActions?.visible ?? false)
                enabled: activeActions?.enabled ?? false
                down: Plasmoid.currentIndex === index
                menuIsOpen: Plasmoid.currentIndex !== -1
                Kirigami.MnemonicData.active: alt.pressed
                onActivated: if (root.available) Plasmoid.trigger(this, index)
                KeyboardIndicator.KeyState { id: alt; key: Qt.Key_Alt }
            }
        }
        PlasmaComponents.ToolButton {
            id: windowButton
            objectName: "applicationWindowActions"
            visible: !root.menusAvailable
            Layout.minimumWidth: 40; Layout.maximumWidth: 40
            icon.name: "window"
            Accessible.name: i18n("Fensteraktionen für %1", root.appName)
            onClicked: windowMenu.open()
            QQC2.Menu {
                id: windowMenu
                property var targetWindow: null
                onAboutToShow: targetWindow = windowState.activeWindow
                popupType: QQC2.Popup.Window
                y: windowButton.height
                onVisibleChanged: root.overflowOpen = visible
                QQC2.MenuItem { text: i18n("Fenster wiederherstellen"); onTriggered: windowState.windowAction("maximize", windowMenu.targetWindow) }
                QQC2.MenuItem { text: i18n("Minimieren"); onTriggered: windowState.windowAction("minimize", windowMenu.targetWindow) }
                QQC2.MenuItem { text: i18n("Schließen"); onTriggered: windowState.windowAction("close", windowMenu.targetWindow) }
            }
        }
        PlasmaComponents.ToolButton {
            id: overflowButton
            objectName: "applicationMenuOverflow"
            Layout.minimumWidth: 40
            Layout.maximumWidth: 40
            visible: buttons.overflowIndex < menus.count
            icon.name: "overflow-menu"
            Accessible.name: i18n("Weitere App-Menüs")
            onClicked: overflowMenu.visible ? overflowMenu.close() : overflowMenu.open()
            QQC2.Menu {
                id: overflowMenu
                popupType: QQC2.Popup.Window
                y: overflowButton.height
                function focusEntry(from, direction) {
                    for (let step = 1; step <= count; ++step) {
                        const next = (from + direction * step + count) % count;
                        const item = itemAt(next);
                        if (item && item.visible && item.enabled) { currentIndex = next; item.forceActiveFocus(); return; }
                    }
                }
                onOpened: Qt.callLater(function() { if (overflowMenu) overflowMenu.focusEntry(-1, 1); })
                onVisibleChanged: root.overflowOpen = visible
                Instantiator {
                    model: menus.count
                    delegate: QQC2.ItemDelegate {
                        required property int index
                        readonly property var source: { if (!buttons || !menus) return null; buttons.delegateRevision; return menus.itemAt(index); }
                        text: source ? source.text : ""
                        visible: index >= buttons.overflowIndex && text !== "" && (source?.activeActions?.visible ?? false)
                        height: visible ? implicitHeight : 0
                        enabled: source?.activeActions?.enabled ?? false
                        // Keep this popup as the native submenu's Wayland parent until its action finishes.
                        function choose() { if (root.available) Plasmoid.trigger(this, index); }
                        onClicked: choose()
                        Keys.onReturnPressed: choose()
                        Keys.onEnterPressed: choose()
                        Keys.onDownPressed: overflowMenu.focusEntry(index, 1)
                        Keys.onUpPressed: overflowMenu.focusEntry(index, -1)
                        Keys.onEscapePressed: overflowMenu.close()
                    }
                    onObjectAdded: (index, object) => overflowMenu.insertItem(index, object)
                    onObjectRemoved: (index, object) => overflowMenu.removeItem(object)
                }
            }
        }
        Connections {
            target: Plasmoid
            function onCurrentIndexChanged() {
                if (Plasmoid.currentIndex < 0 && overflowMenu.visible) overflowMenu.close();
            }
            function onRequestActivateIndex(index: int) {
                if (!root.available) return;
                if (root.compactView) Plasmoid.trigger(root.compactRepresentationItem, 0);
                else {
                    const button = menus.itemAt(index);
                    if (button && button.enabled) Plasmoid.trigger(button.visible ? button : overflowButton, index);
                }
            }
            function onActivated() {
                if (!root.available) return;
                if (root.compactView) Plasmoid.trigger(root.compactRepresentationItem, 0);
                else {
                    const first = menus.itemAt(0);
                    if (first && first.enabled && first.visible) first.activated();
                }
            }
        }
    }
}
