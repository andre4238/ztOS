// The status bar: the time on the left, the radio and the battery left of
// the camera's hole. A pull down on it opens the control centre.
import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

Window {
    id: bar
    visible: true
    color: "transparent"
    title: "ztGlass Status"
    width: Screen.width
    height: 34

    LayerShell.Window.scope: "ztglass-status"
    LayerShell.Window.layer: LayerShell.Window.LayerTop
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: height
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone

    // where the front camera's hole is, so nothing is under it
    readonly property real holeLeft: width - 44

    Text {
        x: 30
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 1
        text: shell.clockText
        color: "white"
        font.family: "Inter"
        font.pixelSize: 16
        font.weight: Font.DemiBold
        font.features: { "tnum": 1 }
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: bar.width - bar.holeLeft + 10
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 1
        spacing: 7

        // Wi-Fi: three arcs, lit as strong as it is
        Canvas {
            id: wifi
            width: 17; height: 12
            visible: shell.wifi >= 0
            property int level: shell.wifi
            onLevelChanged: requestPaint()
            onPaint: {
                var c = getContext("2d")
                c.reset()
                var cx = width / 2, cy = height - 0.5
                for (var i = 0; i < 3; i++) {
                    c.beginPath()
                    if (i === 0) {
                        c.moveTo(cx, cy)
                        c.arc(cx, cy, 4, -Math.PI * 0.75, -Math.PI * 0.25)
                        c.closePath()
                        c.fillStyle = level >= 1 ? "white" : "#55ffffff"
                        c.fill()
                    } else {
                        c.arc(cx, cy, 4 + i * 4, -Math.PI * 0.75, -Math.PI * 0.25)
                        c.lineWidth = 2.2
                        c.lineCap = "round"
                        c.strokeStyle = level >= i + 1 ? "white" : "#55ffffff"
                        c.stroke()
                    }
                }
            }
        }

        // the battery: how full, green while it charges
        Item {
            width: 27; height: 13
            Rectangle {
                id: shellRect
                width: 24; height: 13
                radius: 4
                color: "transparent"
                border.color: "#88ffffff"
                border.width: 1
                Rectangle {
                    x: 2; y: 2
                    height: parent.height - 4
                    width: Math.max(2, (parent.width - 4) * shell.battery / 100)
                    radius: 2
                    color: shell.charging ? "#4cd964" : shell.battery <= 20 ? "#ff453a" : "white"
                }
            }
            Rectangle {
                x: 25; y: 4.5
                width: 1.6; height: 4
                radius: 0.8
                color: "#88ffffff"
            }
        }
    }

    // a pull down from the bar: the control centre
    MouseArea {
        anchors.fill: parent
        property real y0
        onPressed: (m) => y0 = m.y
        onPositionChanged: (m) => { if (m.y - y0 > 14) shell.showControl(true) }
        onClicked: shell.showControl(true)
    }
}
