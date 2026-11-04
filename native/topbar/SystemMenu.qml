import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Popup {
    id: menu
    required property string topic
    required property var colors
    required property var controller
    required property var translate
    required property real heightLimit
    property int section:0
    readonly property bool network:topic==="network"
    readonly property bool narrow:width<580
    readonly property var data:controller.details[topic]||({})
    readonly property var outputs:data.outputs||[]
    readonly property var inputs:data.inputs||[]
    readonly property var defaultInput:inputs.find(d=>d.default)||null
    readonly property var defaultOutput:outputs.find(d=>d.default)||null
    readonly property var sections:network?["Übersicht","WLAN","Kabel & Adapter","VPN & Proxy","Hotspot","Details & Diagnose"]:["Übersicht","Ausgabe","Mikrofon","Apps","Bluetooth","Klang & Technik"]
    property string status:""
    signal launchStudio()
    signal geometryUpdated()
    focus:true
    popupType:Popup.Item
    closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
    padding:0
    height:Math.min(700,heightLimit)
    background:Rectangle {color:menu.colors.window;radius:menu.colors.radius||10;border.color:menu.colors.border}
    onOpened:{status="";controller.inspect(topic)}
    onVisibleChanged:geometryUpdated()
    onHeightChanged:geometryUpdated()
    function t(text){return translate(text)}
    function act(action,target="",value=0){status="";controller.systemAction(topic,action,target,value)}
    function settings(action){menu.close();controller.control(action)}
    function profileTypes(types){return (data.profiles||[]).filter(p=>types.includes(p.type))}
    function editing(item){
        if(item.pressed || item.down || item.pending || item.popup?.visible)return true
        for(const child of item.children||[])if(editing(child))return true
        return false
    }
    Timer {interval:5000;repeat:true;running:menu.opened;onTriggered:if(!menu.editing(menu.contentItem))menu.controller.inspect(menu.topic)}
    Connections {target:menu.controller
        function onControlFinished(action,value){if(action.startsWith(menu.topic+":") && !action.endsWith(":inspect"))menu.status=menu.t("Status aktualisiert.")}
    }
    component Caption:Label {
        color:menu.colors.text;wrapMode:Text.Wrap;textFormat:Text.PlainText
        Layout.fillWidth:true
    }
    component Muted:Caption {color:menu.colors.muted}
    component Heading:Caption {font.pixelSize:18;font.weight:Font.Medium;Layout.topMargin:8}
    component Rule:Rectangle {height:1;color:menu.colors.border;Layout.fillWidth:true;Layout.topMargin:8;Layout.bottomMargin:8}
    component Action:BarButton {colors:menu.colors;key:true;Layout.fillWidth:true;enabled:!menu.controller.controlBusy}
    component Fold:ColumnLayout {
        default property alias body:contents.data
        property string title
        property bool expanded:false
        Layout.fillWidth:true;spacing:8
        Rule {}
        BarButton {colors:menu.colors;text:parent.title;glyph:parent.expanded?"arrow-down":"arrow-right";Layout.fillWidth:true;onClicked:parent.expanded=!parent.expanded}
        ColumnLayout {id:contents;visible:parent.expanded;Layout.fillWidth:true;spacing:8}
    }
    component Facts:ColumnLayout {
        property var rows:[]
        Layout.fillWidth:true;spacing:8
        Repeater {model:parent.rows
            GridLayout {required property var modelData;columns:menu.narrow?1:2;Layout.fillWidth:true;columnSpacing:12
                Muted {text:menu.t(modelData.label);Layout.preferredWidth:menu.narrow?-1:135}
                Caption {text:modelData.value;horizontalAlignment:menu.narrow?Text.AlignLeft:Text.AlignRight}
            }
        }
    }
    component Level:ColumnLayout {
        property string kind
        property var device
        property string label:menu.t("Lautstärke")
        Layout.fillWidth:true;spacing:4
        RowLayout {Layout.fillWidth:true
            Caption {text:parent.parent.label}
            Label {text:levelSlider.available?Math.round(levelSlider.pending?levelSlider.desired:levelSlider.modelValue)+" %":menu.t("Nicht verfügbar");color:menu.colors.text}
        }
        ControlSlider {id:levelSlider;controller:menu.controller;topic:menu.topic;action:"volume:"+parent.kind;target:parent.device?.id||"";modelValue:parent.device?.volume;Layout.fillWidth:true;Accessible.name:parent.label}
    }
    component Device:ColumnLayout {
        id:deviceControl
        required property var device
        required property string kind
        Layout.fillWidth:true;spacing:8
        Rule {}
        Caption {text:device.name;font.weight:Font.Medium}
        Muted {text:(device.default?menu.t("Standardgerät")+" · ":"")+(device.muted?menu.t("Stumm"):device.state||"")}
        RowLayout {Layout.fillWidth:true
            Action {objectName:"deviceDefault"+deviceControl.kind+deviceControl.device.id;text:menu.t("Als Standard verwenden");visible:!parent.parent.device.default;onClicked:menu.act("default:"+parent.parent.kind,parent.parent.device.id)}
            Action {objectName:"deviceMute"+deviceControl.kind+deviceControl.device.id;text:parent.parent.device.muted?menu.t("Ton an"):menu.t("Stumm");onClicked:menu.act("mute:"+parent.parent.kind,parent.parent.device.id)}
        }
        Level {kind:parent.kind;device:parent.device;label:menu.t(kind==="input"?"Verstärkung":"Lautstärke")}
        Fold {title:menu.t("Gerätedetails");Facts {rows:[{label:"Audioformat",value:deviceControl.device.format||menu.t("Nicht verfügbar")},{label:"Anschluss",value:deviceControl.device.activePort||menu.t("Nicht verfügbar")}]}}
    }
    component Profiles:ColumnLayout {
        property var entries:[]
        Layout.fillWidth:true;spacing:8
        Muted {visible:parent.entries.length===0;text:menu.t("Keine passenden Verbindungsprofile vorhanden.")}
        Repeater {model:parent.entries
            ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:6
                Caption {text:modelData.name;font.weight:Font.Medium}
                Muted {text:(modelData.active?menu.t("Verbunden"):menu.t("Nicht verbunden"))+(modelData.device && modelData.device!=="--"?" · "+modelData.device:"")}
                Action {text:menu.t(modelData.active?"Trennen":"Verbinden");onClicked:menu.act(modelData.active?"disconnect":"connect",modelData.id)}
                Rule {}
            }
        }
    }
    contentItem:ColumnLayout {
        spacing:0
        RowLayout {Layout.fillWidth:true;Layout.margins:24;spacing:12
            Kirigami.Icon {source:menu.network?"network-wireless":"audio-volume-high";width:24;height:24;color:menu.colors.accent}
            ColumnLayout {Layout.fillWidth:true;spacing:2
                Caption {text:menu.t(menu.network?"Netzwerk":"Audio");font.pixelSize:20;font.weight:Font.Medium}
                Muted {text:menu.t(menu.network?"Verbindungen & Internet":"Wiedergabe & Aufnahme")}
            }
            BarButton {colors:menu.colors;text:menu.t("Schließen");glyph:"window-close";iconOnly:true;onClicked:menu.close()}
        }
        Rectangle {height:1;Layout.fillWidth:true;color:menu.colors.border}
        GridLayout {Layout.fillWidth:true;Layout.fillHeight:true;columns:menu.narrow?1:2;rowSpacing:0;columnSpacing:0
            GridLayout {Layout.fillWidth:menu.narrow;Layout.fillHeight:!menu.narrow;Layout.alignment:Qt.AlignTop;Layout.margins:12;columns:menu.narrow?3:1;rowSpacing:4;columnSpacing:4
                Repeater {model:menu.sections
                    BarButton {required property string modelData;required property int index;objectName:menu.topic+"Section"+index
                        text:menu.t(modelData);colors:menu.colors;current:index===menu.section;Layout.fillWidth:true;Layout.preferredWidth:menu.narrow?0:158
                        implicitHeight:Math.max(40,navLabel.implicitHeight+16)
                        contentItem:Text {id:navLabel;text:parent.text;wrapMode:Text.Wrap;textFormat:Text.PlainText;color:menu.colors.text;font:parent.font}
                        onClicked:{menu.section=index;pageScroll.ScrollBar.vertical.position=0}
                    }
                }
                Item {visible:!menu.narrow;Layout.fillHeight:true}
            }
            ScrollView {id:pageScroll;Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:100;clip:true;contentWidth:availableWidth
                ColumnLayout {width:pageScroll.availableWidth;spacing:12
                    ColumnLayout {Layout.fillWidth:true;Layout.margins:24;spacing:12
                        Caption {visible:menu.section!==0;text:menu.t(menu.sections[menu.section]);font.pixelSize:18;font.weight:Font.Medium}
                        Muted {visible:!menu.data.available;text:menu.controller.controlBusy?menu.t("Systemdaten werden geladen …"):menu.t("Dieser Systemdienst ist nicht verfügbar.")}
                        Repeater {model:menu.data.errors||[]
                            Muted {required property var modelData;text:menu.t(modelData.area)+": "+menu.t(modelData.message)}
                        }
                        Loader {Layout.fillWidth:true;sourceComponent:menu.network?networkPage:audioPage}
                    }
                }
            }
        }
        Rectangle {height:1;Layout.fillWidth:true;color:menu.colors.border}
        Caption {objectName:menu.topic+"Feedback";Layout.margins:16;Layout.leftMargin:24;Layout.rightMargin:24;color:menu.colors.muted;text:menu.controller.error?menu.t(menu.controller.error):menu.controller.controlBusy?menu.t("Wird aktualisiert …"):menu.status||menu.t("Einstellungen für diesen Rechner")}
    }
    Component {id:networkPage
        ColumnLayout {spacing:12
            ColumnLayout {visible:menu.section===0;Layout.fillWidth:true;spacing:12
                Rectangle {color:menu.colors.base;radius:menu.colors.radius||10;border.color:menu.colors.border;Layout.fillWidth:true;implicitHeight:summary.implicitHeight+32
                    ColumnLayout {id:summary;anchors.fill:parent;anchors.margins:16;spacing:8
                        Caption {text:menu.t(menu.data.state==="connected"?"Mit dem Internet verbunden":menu.data.state==="connecting"?"Verbindet …":"Keine Internetverbindung");color:menu.colors.accent}
                        Muted {text:(menu.data.devices||[]).filter(d=>d.profile && d.profile!=="--").map(d=>d.profile+" · "+d.name).join("\n")||menu.t("Keine aktive Verbindung")}
                        Action {text:menu.t("Verbindung prüfen");glyph:"network-connect";onClicked:{menu.section=5;menu.act("diagnose")}}
                    }
                }
                Heading {text:menu.t("Verbindungen")}
                Action {text:menu.t("WLAN");glyph:"network-wireless";onClicked:menu.section=1}
                Action {text:menu.t("Kabel & Adapter");glyph:"network-wired";onClicked:menu.section=2}
                Heading {text:menu.t("Privatsphäre & Freigabe")}
                Profiles {visible:entries.length>0;entries:menu.profileTypes(["vpn","wireguard"]).filter(p=>p.active)}
                Action {text:menu.t("VPN & Proxy");glyph:"network-vpn";onClicked:menu.section=3}
                Action {text:menu.t("Hotspot");glyph:"network-wireless-hotspot";onClicked:menu.section=4}
            }
            ColumnLayout {visible:menu.section===1;Layout.fillWidth:true;spacing:12
                Switch {objectName:"wifiSwitch";text:menu.t("WLAN aktivieren");checked:!!menu.data.wifiEnabled;enabled:!!menu.data.available && !menu.controller.controlBusy;onClicked:menu.act("wifi","",checked?1:0)}
                Repeater {model:menu.data.wifiEnabled?menu.data.networks||[]:[]
                    ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:4
                        Caption {text:modelData.name;font.weight:Font.Medium}
                        Muted {text:modelData.signal+" % · "+(modelData.security||menu.t("Offenes Netzwerk"))+" · "+modelData.frequency+" · "+menu.t("Kanal")+" "+modelData.channel}
                        Action {text:menu.t(modelData.active?"Verbunden":"Verbinden");enabled:!modelData.active && !modelData.hidden && !menu.controller.controlBusy;onClicked:menu.act("join",modelData.id)}
                        Rule {}
                    }
                }
                Muted {visible:!!menu.data.wifiEnabled && !(menu.data.networks||[]).length;text:menu.t("Keine sichtbaren WLAN-Netze gefunden.")}
                Action {text:menu.t("Netze neu suchen");glyph:"view-refresh";visible:!!menu.data.wifiEnabled;onClicked:menu.act("rescan")}
                Fold {title:menu.t("Gespeicherte Netzwerke");Profiles {entries:menu.profileTypes(["802-11-wireless","wifi"])}}
                Action {text:menu.t("Verstecktes Netzwerk oder Profil hinzufügen …");onClicked:menu.settings("network")}
                Muted {text:menu.t("Passwörter und Zertifikate fragt die sichere Systemanmeldung ab.")}
            }
            ColumnLayout {visible:menu.section===2 || menu.section===5;Layout.fillWidth:true;spacing:12
                Facts {visible:menu.section===5;rows:[{label:"Verbindungsstatus",value:menu.data.state||menu.t("Nicht verfügbar")},{label:"Internetzugriff",value:menu.data.connectivity||menu.t("Nicht verfügbar")}]}
                Action {text:menu.t("Verbindung prüfen");visible:menu.section===5;onClicked:menu.act("diagnose")}
                Repeater {model:(menu.data.devices||[]).filter(d=>menu.section===5 || !["wifi","loopback"].includes(d.type))
                    Fold {required property var modelData;title:modelData.name+" · "+modelData.type;expanded:menu.section===2
                        Muted {text:modelData.state+" · "+modelData.profile}
                        Facts {rows:modelData.details}
                    }
                }
                Muted {visible:menu.section===5;text:menu.t("Die Diagnose nutzt die eingerichtete NetworkManager-Verbindungsprüfung. IP-Adressen und DNS stammen direkt von den Adaptern.")}
                Action {text:menu.t("IP, DNS, Routen & Verbindungsprofile …");onClicked:menu.settings("network")}
                Action {text:menu.t("Firewall …");visible:menu.section===5;onClicked:menu.settings("firewall")}
            }
            ColumnLayout {visible:menu.section===3;Layout.fillWidth:true;spacing:12
                Profiles {entries:menu.profileTypes(["vpn","wireguard"])}
                Action {text:menu.t("VPN hinzufügen, importieren oder bearbeiten …");onClicked:menu.settings("network")}
                Action {text:menu.t("Proxy einstellen …");onClicked:menu.settings("proxy")}
                Muted {text:menu.t("Automatische Verbindung, Zertifikate und Routing werden im jeweiligen Systemprofil eingestellt.")}
            }
            ColumnLayout {visible:menu.section===4;Layout.fillWidth:true;spacing:12
                Muted {text:menu.t("Internet teilen: WLAN-Profil mit Hotspot-Modus einrichten. Dort lassen sich Name, Sicherheit und Zugangsdaten verwalten.")}
                Action {text:menu.t("Hotspot einrichten oder bearbeiten …");glyph:"network-wireless-hotspot";onClicked:menu.settings("network")}
                Heading {text:menu.t("Hotspot-Profile")}
                Profiles {entries:(menu.data.profiles||[]).filter(p=>p.hotspot)}
            }
        }
    }
    Component {id:audioPage
        ColumnLayout {spacing:12
            ColumnLayout {visible:menu.section===0;Layout.fillWidth:true;spacing:12
                Rectangle {color:menu.colors.base;radius:menu.colors.radius||10;border.color:menu.colors.border;Layout.fillWidth:true;implicitHeight:outputSummary.implicitHeight+32
                  ColumnLayout {id:outputSummary;anchors.fill:parent;anchors.margins:16;spacing:12
                   Caption {text:menu.defaultOutput?.name||menu.t("Kein Ausgabegerät");font.weight:Font.Medium}
                   RowLayout {Layout.fillWidth:true
                    BarButton {objectName:"muteButton";colors:menu.colors;text:menu.t(menu.controller.snapshot.system?.muted?"Ton an":"Stumm");glyph:menu.controller.snapshot.system?.muted?"audio-volume-muted":"audio-volume-high";enabled:typeof(menu.controller.snapshot.system?.volume)==="number" && !menu.controller.controlBusy;onClicked:menu.controller.control("mute")}
                    ControlSlider {id:volume;objectName:"volumeSlider";controller:menu.controller;action:"volume";modelValue:menu.controller.snapshot.system?.volume;Layout.fillWidth:true;Accessible.name:menu.t("Lautstärke")}
                    Label {text:volume.available?Math.round(volume.pending?volume.desired:volume.modelValue)+" %":menu.t("Nicht verfügbar");color:menu.colors.text}
                   }
                   Action {text:menu.t("Ausgabegerät wechseln");onClicked:menu.section=1}
                  }
                }
                Rule {}
                Heading {text:menu.t("Mikrofon")}
                Caption {text:menu.defaultInput?.name||menu.t("Kein Mikrofon")}
                Muted {text:menu.defaultInput?.muted?menu.t("Stumm"):menu.t("Aktive Aufnahme-Apps")+": "+((menu.data.recording||[]).map(a=>a.name).join(", ")||menu.t("Keine"))}
                Action {text:menu.defaultInput?.muted?menu.t("Mikrofon freigeben"):menu.t("Mikrofon stummschalten");enabled:!!menu.defaultInput && !menu.controller.controlBusy;onClicked:menu.act("mute:input",menu.defaultInput.id)}
                Action {text:menu.t("Mikrofon einstellen");onClicked:menu.section=2}
                Rule {}
                Action {text:menu.t("App-Lautstärken & Ausgabe");onClicked:menu.section=3}
                Action {text:menu.t("Bluetooth-Audio");onClicked:menu.section=4}
            }
            ColumnLayout {visible:menu.section===1 || menu.section===2;Layout.fillWidth:true;spacing:8
                Repeater {model:menu.section===1?menu.outputs:menu.inputs
                    Device {required property var modelData;device:modelData;kind:menu.section===1?"output":"input"}
                }
                Muted {visible:!(menu.section===1?menu.outputs:menu.inputs).length;text:menu.t(menu.section===1?"Kein Ausgabegerät":"Kein Mikrofon")}
                Action {text:menu.t("Anschlüsse, Kanäle & Gerätetest …");onClicked:menu.settings("audio")}
                Muted {visible:menu.section===2;text:menu.t("Hier wird kein Mikrofon zum Testen eingeschaltet. Laufende Aufnahme-Apps erscheinen unter Apps.")}
            }
            ColumnLayout {visible:menu.section===3;Layout.fillWidth:true;spacing:12
                Repeater {model:[{kind:"playback",title:menu.t("Wiedergabe"),items:menu.data.playback||[],devices:menu.outputs},{kind:"recording",title:menu.t("Aufnahme"),items:menu.data.recording||[],devices:menu.inputs}]
                    ColumnLayout {id:streamGroup;required property var modelData;Layout.fillWidth:true;spacing:12
                        Heading {text:streamGroup.modelData.title}
                        Muted {visible:streamGroup.modelData.items.length===0;text:menu.t("Keine aktiven Apps")}
                        Repeater {model:streamGroup.modelData.items
                            ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:8
                                Caption {text:modelData.name;font.weight:Font.Medium}
                                Muted {text:modelData.media;visible:!!text}
                                Level {kind:streamGroup.modelData.kind;device:parent.modelData}
                                Action {text:menu.t(modelData.muted?"Ton an":"Stumm");onClicked:menu.act("mute:"+streamGroup.modelData.kind,modelData.id)}
                                ComboBox {objectName:"streamRoute"+modelData.id;Layout.fillWidth:true;model:streamGroup.modelData.devices;textRole:"name";valueRole:"id";currentIndex:streamGroup.modelData.devices.findIndex(d=>d.id===parent.modelData.device);enabled:!menu.controller.controlBusy;Accessible.name:menu.t("Gerät für App");onActivated:menu.act("route:"+streamGroup.modelData.kind,parent.modelData.id,Number(currentValue))}
                                Rule {}
                            }
                        }
                    }
                }
            }
            ColumnLayout {visible:menu.section===4;Layout.fillWidth:true;spacing:12
                Repeater {model:menu.data.bluetooth?.adapters||[]
                    Switch {required property var modelData;text:modelData.name;checked:modelData.powered;enabled:!menu.controller.controlBusy;onClicked:menu.act("bt-power",modelData.id,checked?1:0)}
                }
                Muted {visible:!(menu.data.bluetooth?.adapters||[]).length;text:menu.t("Kein Bluetooth-Adapter verfügbar.")}
                Repeater {model:menu.data.bluetooth?.devices||[]
                    ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:8
                        Caption {text:modelData.name;font.weight:Font.Medium}
                        Muted {text:menu.t(modelData.connected?"Verbunden":"Nicht verbunden")+(typeof modelData.battery==="number"?" · "+modelData.battery+" % "+menu.t("Akku"):"")}
                        Action {text:menu.t(modelData.connected?"Trennen":"Verbinden");onClicked:menu.act(modelData.connected?"bt-disconnect":"bt-connect",modelData.id)}
                        Rule {}
                    }
                }
                Action {text:menu.t("Audiogerät koppeln oder entfernen …");onClicked:menu.settings("bluetooth")}
                Muted {text:menu.t("Musik- und Headsetprofile unter Klang & Technik wählen. Das Headset-Mikrofon kann einen Profilwechsel erfordern.")}
            }
            ColumnLayout {visible:menu.section===5;Layout.fillWidth:true;spacing:12
                Muted {text:menu.data.server||menu.t("Nicht verfügbar")}
                Repeater {model:menu.data.cards||[]
                    ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:8
                        Heading {text:modelData.name}
                        ComboBox {Layout.fillWidth:true;model:parent.modelData.profiles;textRole:"name";valueRole:"id";currentIndex:parent.modelData.profiles.findIndex(p=>p.id===parent.modelData.active);enabled:!menu.controller.controlBusy;Accessible.name:menu.t("Audioprofil");onActivated:menu.act("profile",parent.modelData.id+"/"+currentValue)}
                    }
                }
                Action {text:menu.t("Balance, Anschlüsse & Kanalbelegung …");onClicked:menu.settings("audio")}
                Muted {text:menu.t("Klangverbesserungen, Rauschunterdrückung und Formate hängen vom Gerät und dem installierten Audiosystem ab. Es werden keine wirkungslosen Regler angeboten.")}
                Rule {}
                Action {text:"Lumen Audio Studio";glyph:"audio-input-microphone";onClicked:{menu.close();menu.launchStudio()}}
            }
        }
    }
}
