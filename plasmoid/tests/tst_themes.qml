import QtQuick
import QtTest
import org.kde.kirigami as Kirigami
import "../contents/ui" as Lumen

Rectangle {
    id: scene
    width: 540; height: 720
    Kirigami.Theme.inherit: false
    property var palette: ({background: "#20343f", text: "#f0f6f8", muted: "#b1c5cf", accent: "#9be5d8", hover: "#344f5d"})
    Kirigami.Theme.backgroundColor: palette.background
    Kirigami.Theme.textColor: palette.text
    Kirigami.Theme.disabledTextColor: palette.muted
    Kirigami.Theme.highlightColor: palette.accent
    Kirigami.Theme.alternateBackgroundColor: palette.hover
    color: Kirigami.Theme.backgroundColor
    Lumen.CompactBar { id: bar; x: 16; y: 8; width: 280; height: 44; surface: "home" }
    Lumen.ControlCenter { id: center; x: 0; y: 64; width: parent.width; height: 630
        notificationSettings: QtObject { property date notificationsInhibitedUntil: new Date(0); property bool notificationsInhibitedByApplication: false; function save() {} }
        systemState: ({volume: 55, muted: false, brightness: 80, network: "Verbunden"})
    }
    TestCase {
        name: "LumenThemeInheritance"; when: windowShown
        function test_all_surfaces_follow_palette_changes() {
            const variants = [
                {name:"glass", background:"#20343f", text:"#f0f6f8", muted:"#b1c5cf", accent:"#9be5d8", hover:"#344f5d"},
                {name:"graphite", background:"#252b2e", text:"#edf1ef", muted:"#aebcb8", accent:"#72c9b1", hover:"#35403f"},
                {name:"atelier", background:"#f2efe8", text:"#302e29", muted:"#645e54", accent:"#52634f", hover:"#e5e1d6"},
                {name:"midnight", background:"#10151f", text:"#eef1fa", muted:"#a9b7ce", accent:"#a7b6ff", hover:"#29364e"}
            ];
            for (const palette of variants) {
                scene.palette = palette; wait(100); waitForRendering(scene);
                const button = findChild(bar,"homeButton");
                compare(button.Kirigami.Theme.textColor.toString(),palette.text);
                compare(center.Kirigami.Theme.backgroundColor.toString(),palette.background);
                compare(findChild(center,"volumeSlider").Kirigami.Theme.highlightColor.toString(),palette.accent);
                grabImage(scene).save("artifacts/themes/panel-" + palette.name + ".png");
            }
        }
    }
}
