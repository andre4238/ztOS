// The volume, for a moment, when a volume key is pressed: a slim pane at
// the left edge, next to the keys.
import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

Window {
    id: hud
    visible: false
    color: "transparent"
    title: "ztGlass Volume"
    width: 52
    height: 330

    LayerShell.Window.scope: "ztglass-volume"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone

    Rectangle {
        id: pill
        x: 10; y: 158
        width: 36; height: 164
        radius: 18
        color: "#8c1c1c22"
        border.color: "#40ffffff"
        clip: true
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: parent.height * shell.volume
            color: "#f2ffffff"
            Behavior on height { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 8
            text: shell.muted || shell.volume === 0 ? "🔇" : "🔊"
            font.pixelSize: 14
        }
    }

    Timer {
        id: hide
        interval: 1600
        onTriggered: hud.visible = false
    }

    Connections {
        target: shell
        function onVolumeShown() {
            hud.visible = true
            hide.restart()
        }
    }
}
