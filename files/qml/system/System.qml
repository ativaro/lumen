import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Pane {
    id: root
    required property var controller
    property var t: controller.theme
    property var d: controller.data
    property int page: 0
    property var expanded: ({})
    width: 1280; height: 900; padding: 0
    background: Rectangle { color: root.t.window }
    font.family: t.fontFamily; font.pixelSize: t.fontSize
    function tx(s) { return controller.text(s) }
    palette.window: t.window; palette.base: t.base; palette.text: t.text
    palette.button: t.button; palette.buttonText: t.text; palette.highlight: t.accent
    component LabelText: Text {
        color: root.t.text; font.family: root.t.fontFamily; font.pixelSize: root.t.fontSize
        textFormat: Text.PlainText
    }
    component Surface: Rectangle {
        radius: root.t.radius; color: Qt.alpha(root.t.base,.75); border.color: Qt.alpha(root.t.border,.4)
    }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            objectName: 'systemNavigation'
            Layout.fillHeight: true; Layout.preferredWidth: root.t.navWidth
            color: Qt.alpha(t.base,.62)
            Rectangle { anchors.right: parent.right; height: parent.height; width: 1; color: Qt.alpha(t.border,.32) }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: root.t.pageMargin; spacing: 9
                RowLayout {
                    Layout.topMargin: 15; Layout.bottomMargin: 30; spacing: 12
                    Rectangle {
                        width: 32; height: 32; radius: 10; color: Qt.alpha(t.accent,.14); border.color: Qt.alpha(t.accent,.35)
                        LabelText { anchors.centerIn: parent; text: '▥'; color: t.accent; font.pixelSize: 23 }
                    }
                    LabelText { text: 'Lumen'; font.pixelSize: 23; font.weight: Font.DemiBold }
                }
                LabelText { text: 'SYSTEM'; font.pixelSize: 11; font.letterSpacing: 2; color: t.muted; Layout.leftMargin: 12; Layout.bottomMargin: 8 }
                Repeater {
                    model: [root.tx('Übersicht'), root.tx('Aktivität'), root.tx('Geräte')]
                    SystemButton { required property string modelData; required property int index
                        objectName: 'page'+index; theme: root.t; text: modelData; selected: root.page===index
                        Layout.fillWidth: true; onClicked: root.page=index
                    }
                }
                Item { Layout.fillHeight: true }
                LabelText { text: root.tx('Lokal auf deinem Rechner'); font.pixelSize: 12; color: t.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.leftMargin: 10; Layout.bottomMargin: 12 }
                SystemButton { theme: root.t; text: root.tx('Einstellungen'); Layout.fillWidth: true; onClicked: controller.settings_page() }
            }
        }
        ColumnLayout {
            Layout.fillHeight: true; Layout.fillWidth: true; spacing: 0
            RowLayout {
                Layout.fillWidth: true; Layout.margins: root.t.pageMargin; Layout.bottomMargin: 10
                Rectangle { width: 7; height: 7; radius: 4; color: controller.paused || d.stale ? t.muted : t.accent }
                LabelText { text: d.status || ''; color: t.muted; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                SystemButton { objectName: 'retry'; visible: d.stale && !controller.paused; theme: root.t; text: root.tx('Erneut starten'); onClicked: controller.restart() }
                SystemButton { objectName: 'pause'; theme: root.t; text: controller.paused ? root.tx('Fortsetzen') : root.tx('Pausieren'); onClicked: controller.toggle_pause() }
            }
            ScrollView {
                id: scroll; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: scroll.availableWidth; spacing: 22
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.leftMargin: root.t.pageMargin; Layout.rightMargin: root.t.pageMargin; spacing: 9
                        LabelText { objectName: 'systemPageHeading'; text: page===0 ? root.tx('Dein System. Auf einen Blick.') : page===1 ? root.tx('Was beschäftigt deinen Rechner?') : root.tx('Deine Geräte. Alle Details.')
                            font.pixelSize: root.t.headingSize; font.weight: Font.Medium; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        LabelText { text: page===0 ? root.tx('Leistung, Speicher und Aktivität – direkt von deinem Rechner.') : page===1 ? root.tx('Messwerte verstehen. Veränderungen erkennen.') : root.tx('Die Sensoren, die dein System bereitstellt.')
                            color: t.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: t.fontSize-1 }
                    }
                    ColumnLayout {
                        visible: page===0; Layout.fillWidth: true; Layout.leftMargin: root.t.pageMargin; Layout.rightMargin: root.t.pageMargin; spacing: 22
                        GridLayout {
                            columns: 2; columnSpacing: 16; rowSpacing: 16; Layout.fillWidth: true
                            Repeater { model: d.metrics || []
                                StatCard { required property var modelData; theme: root.t; metric: modelData; seconds: d.seconds || 60
                                    Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.preferredHeight: 192 }
                            }
                        }
                        Surface {
                            Layout.fillWidth: true; implicitHeight: active.implicitHeight+36
                            ColumnLayout {
                                id: active; anchors.fill: parent; anchors.margins: 18; spacing: 10
                                RowLayout {
                                    LabelText { text: root.tx('Gerade aktiv'); font.weight: Font.DemiBold; Layout.fillWidth: true }
                                    SystemButton { objectName: 'showActivity'; theme: root.t; text: root.tx('Aktivität ansehen')+'  →'; onClicked: root.page=1 }
                                }
                                Repeater { model: (d.processes || []).slice(0,3)
                                    RowLayout { required property var modelData; spacing: 16
                                        Rectangle { width: 5; height: 5; radius: 3; color: t.accent }
                                        LabelText { text: modelData.name; Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: t.fontSize-2 }
                                        LabelText { text: modelData.cpu+' CPU'; color: t.muted; font.pixelSize: t.fontSize-3 }
                                        LabelText { text: modelData.memory; color: t.muted; font.pixelSize: t.fontSize-3; Layout.preferredWidth: 90; horizontalAlignment: Text.AlignRight }
                                    }
                                }
                                LabelText { visible: !(d.processes || []).length; text: root.tx('Prozesse werden gelesen …'); color: t.muted }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            SystemButton { theme: root.t; text: root.tx('Geräte & Sensoren')+'  →'; onClicked: root.page=2 }
                            Item { Layout.fillWidth: true }
                            SystemButton { theme: root.t; primary: true; text: root.tx('Mit Lumen prüfen'); enabled: d.measured !== '—'; onClicked: controller.investigate() }
                        }
                    }
                    ColumnLayout {
                        visible: page===1; Layout.fillWidth: true; Layout.leftMargin: root.t.pageMargin; Layout.rightMargin: root.t.pageMargin; spacing: 18
                        RowLayout {
                            LabelText { text: root.tx('Verlauf'); font.weight: Font.DemiBold; Layout.fillWidth: true }
                            Repeater { model: [{s:60,t:'1 min'},{s:900,t:'15 min'},{s:3600,t:'1 h'}]
                                SystemButton { required property var modelData; theme: root.t; text: modelData.t; selected: d.seconds===modelData.s
                                    objectName: 'range'+modelData.s; onClicked: controller.set_range(modelData.s) }
                            }
                        }
                        GridLayout {
                            columns: root.width >= 1180 ? 2 : 1; columnSpacing: 18; rowSpacing: 18; Layout.fillWidth: true
                        Surface {
                            Layout.fillWidth: true; Layout.preferredWidth: 650; Layout.fillHeight: true; implicitHeight: charts.implicitHeight+40
                            ColumnLayout {
                                id: charts; anchors.fill: parent; anchors.margins: 20; spacing: 12
                                RowLayout {
                                    Repeater { model: [{n:'CPU',c:t.accent},{n:'GPU',c:'#78a9d4'},{n:'RAM',c:t.window==='#f2efe8'?'#987228':'#ddbd7d'}]
                                        RowLayout { required property var modelData
                                            Rectangle { width: 8; height: 8; radius: 4; color: modelData.c }
                                            LabelText { text: modelData.n; color: t.muted; font.pixelSize: 13 }
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                    LabelText { text: '0–100 %'; color: t.muted; font.pixelSize: 12 }
                                }
                                Trend { objectName: 'activityChart'; Layout.fillWidth: true; Layout.preferredHeight: 165
                                    points: d.points || []; keys: ['cpu','gpu','memory']; colors: [t.accent,'#78a9d4',t.window==='#f2efe8'?'#987228':'#ddbd7d']; grid: true; gridColor: t.border; seconds: d.seconds || 60; events: d.events || [] }
                                RowLayout {
                                    LabelText { text: root.tx('Netzwerk'); font.pixelSize: 13; color: t.muted }
                                    LabelText { text: d.network || '—'; font.pixelSize: 13; color: t.text; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight }
                                }
                                Trend { Layout.fillWidth: true; Layout.preferredHeight: 42; points: d.points || []; keys: ['network']; colors: [t.accent]; grid: true; gridColor: t.border; maximum: d.networkMax || 1; seconds: d.seconds || 60 }
                                LabelText { text: root.tx('Netzwerk automatisch skaliert · ohne Loopback'); font.pixelSize: 11; color: t.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                RowLayout {
                                    LabelText { text: d.seconds===3600 ? root.tx('Vor 1 Stunde') : d.seconds===900 ? root.tx('Vor 15 Minuten') : root.tx('Vor 1 Minute'); color: t.muted; font.pixelSize: 12 }
                                    Item { Layout.fillWidth: true }
                                    LabelText { text: (controller.paused ? root.tx('Letzte Messung') : root.tx('Jetzt'))+' · '+(d.measured || '—'); color: t.muted; font.pixelSize: 12 }
                                }
                            }
                        }
                        Surface {
                            Layout.fillWidth: true; Layout.preferredWidth: 290; Layout.fillHeight: true; implicitHeight: facts.implicitHeight+36
                            ColumnLayout { id: facts; anchors.fill: parent; anchors.margins: 18; spacing: 8
                                LabelText { text: root.tx('Was die Messwerte zeigen'); font.weight: Font.DemiBold }
                                Repeater { model: d.facts || []
                                    LabelText { required property string modelData; text: modelData; color: t.muted; font.pixelSize: t.fontSize-2; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                }
                                LabelText { text: root.tx('Zeitgleich bedeutet nicht automatisch ursächlich.'); color: t.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                            }
                        }
                        }
                        RowLayout {
                            LabelText { text: root.tx('Deine Prozesse'); font.weight: Font.DemiBold; Layout.fillWidth: true }
                            SystemButton { theme: root.t; text: 'CPU ↓'; onClicked: controller.set_sort('cpu') }
                            SystemButton { theme: root.t; text: 'RAM ↓'; onClicked: controller.set_sort('memory') }
                        }
                        LabelText { text: root.tx('CPU: 100 % entspricht einem logischen Kern · bis zu 80 Prozesse'); color: t.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 0
                            RowLayout {
                                Layout.fillWidth: true; Layout.bottomMargin: 8
                                LabelText { text: root.tx('Prozess'); Layout.fillWidth: true; color: t.muted; font.pixelSize: 12 }
                                LabelText { text: 'PID'; Layout.preferredWidth: 65; color: t.muted; font.pixelSize: 12; horizontalAlignment: Text.AlignRight }
                                LabelText { text: 'CPU'; Layout.preferredWidth: 85; color: t.muted; font.pixelSize: 12; horizontalAlignment: Text.AlignRight }
                                LabelText { text: 'RAM'; Layout.preferredWidth: 105; color: t.muted; font.pixelSize: 12; horizontalAlignment: Text.AlignRight }
                            }
                            Repeater { model: (d.processes || []).slice(0,root.allProcesses ? 80 : 8)
                                Rectangle { required property var modelData; Layout.fillWidth: true; implicitHeight: 42; color: 'transparent'
                                    Rectangle { width: parent.width; height: 1; color: Qt.alpha(t.border,.24) }
                                    RowLayout { anchors.fill: parent; spacing: 12
                                        LabelText { text: modelData.name; Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: t.fontSize-2 }
                                        LabelText { text: modelData.pid; Layout.preferredWidth: 65; color: t.muted; font.pixelSize: 12; horizontalAlignment: Text.AlignRight }
                                        LabelText { text: modelData.cpu; Layout.preferredWidth: 85; font.pixelSize: t.fontSize-2; horizontalAlignment: Text.AlignRight }
                                        LabelText { text: modelData.memory; Layout.preferredWidth: 105; color: t.muted; font.pixelSize: t.fontSize-2; horizontalAlignment: Text.AlignRight }
                                    }
                                }
                            }
                        }
                        SystemButton { theme: root.t; text: root.allProcesses ? root.tx('Weniger anzeigen') : root.tx('Alle anzeigen'); onClicked: root.allProcesses=!root.allProcesses }
                        LabelText { text: root.tx('Gemessene Veränderungen'); font.weight: Font.DemiBold }
                        LabelText { visible: !(d.events || []).length; text: root.tx('Noch keine Schwellenüberschreitungen in dieser Sitzung.'); color: t.muted; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: t.fontSize-2 }
                        Repeater { model: (d.events || []).slice(0,8)
                            LabelText { required property var modelData; text: modelData.time+'  ·  '+modelData.text; color: t.muted; font.pixelSize: t.fontSize-2; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        }
                        SystemButton { theme: root.t; primary: true; text: root.tx('Mit Lumen prüfen'); enabled: d.measured !== '—'; onClicked: controller.investigate() }
                    }
                    ColumnLayout {
                        visible: page===2; Layout.fillWidth: true; Layout.leftMargin: root.t.pageMargin; Layout.rightMargin: root.t.pageMargin; spacing: 14
                        LabelText { text: (d.cpuName || '—')+' · '+(d.cores || 0)+' '+root.tx('logische Kerne'); font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        LabelText { text: d.sensorStatus || ''; color: t.muted; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        LabelText { text: root.tx('Temperaturen, Lüfter und Leistung hängen von Hardware und Treiber ab. Fehlende Werte sind keine Fehlerdiagnose.'); color: t.muted; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: t.fontSize-2 }
                        Repeater { model: d.devices || []
                            Surface { required property var modelData; id: device; Layout.fillWidth: true; implicitHeight: deviceColumn.implicitHeight+28
                                ColumnLayout { id: deviceColumn; anchors.fill: parent; anchors.margins: 14; spacing: 12
                                    SystemButton { theme: root.t; text: (root.expanded[device.modelData.name] ? '−  ' : '+  ')+device.modelData.name; Layout.fillWidth: true
                                        onClicked: { let next=Object.assign({},root.expanded); next[device.modelData.name]=!next[device.modelData.name]; root.expanded=next } }
                                    ColumnLayout { visible: !!root.expanded[device.modelData.name]; Layout.fillWidth: true; spacing: 10
                                        Repeater { model: device.modelData.sensors
                                            RowLayout { required property var modelData
                                                LabelText { text: modelData.name; Layout.fillWidth: true; color: t.muted; elide: Text.ElideRight; font.pixelSize: t.fontSize-2 }
                                                LabelText { text: modelData.value; font.pixelSize: t.fontSize-2 }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        LabelText { visible: !(d.devices || []).length; text: root.tx('Keine Sensoren gemeldet. Optional lm_sensors und den passenden GPU-Treiber installieren.'); color: t.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        SystemButton { theme: root.t; text: root.tx('Hintergrundarbeit einstellen'); onClicked: controller.settings_page() }
                    }
                    Item { Layout.preferredHeight: 12 }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Qt.alpha(t.border,.32) }
            LabelText { Layout.margins: root.t.pageMargin; Layout.fillWidth: true; text: root.tx('Verlauf nur in dieser Sitzung · bis zu 1 Stunde · keine automatische KI-Analyse'); color: t.muted; font.pixelSize: 12; wrapMode: Text.WordWrap }
        }
    }
    property bool allProcesses: false
    onPageChanged: scroll.contentItem.contentY=0
}
