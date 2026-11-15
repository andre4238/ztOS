// The lock screen: the date and the time large over the wallpaper; a swipe
// up opens the phone. It comes after the screen was off.
import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

Window {
    id: lock
    visible: shell.locked
    color: "transparent"
    title: "ztGlass Lock"
    width: Screen.width
    height: Screen.height

    LayerShell.Window.scope: "ztglass-lock"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorBottom
                               | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone

    onVisibleChanged: if (visible) { face.y = 0; face.opacity = 1 }

    Item {
        id: face
        width: lock.width
        height: lock.height

        Image {
            anchors.fill: parent
            source: shell.wallpaper
            sourceSize: Qt.size(Math.round(width * Screen.devicePixelRatio), Math.round(height * Screen.devicePixelRatio))
            fillMode: Image.PreserveAspectCrop
        }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#40000000" }
                GradientStop { position: 0.45; color: "#00000000" }
                GradientStop { position: 1.0; color: "#50000000" }
            }
        }

        Text {
            id: date
            y: 78
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: shell.dateText
            color: "#e6ffffff"
            font.family: "Inter"
            font.pixelSize: 19
            font.weight: Font.DemiBold
        }
        Text {
            anchors.top: date.bottom
            anchors.topMargin: -6
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: shell.clockText
            color: "#f2ffffff"
            font.family: "Inter Display"
            font.pixelSize: 96
            font.weight: Font.DemiBold
            font.features: { "tnum": 1 }
            font.letterSpacing: -2
        }

        // the battery while it charges
        Item {
            visible: shell.charging
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 170
            width: chargeText.width + 32
            height: 34
            Image {
                anchors.fill: parent
                source: parent.visible ? shell.glassTint(parent.x, parent.y, parent.width, parent.height, 17, 0.12) : ""
            }
            Text {
                id: chargeText
                anchors.centerIn: parent
                text: "Charging · " + shell.battery + " %"
                color: "white"
                font.family: "Inter"
                font.pixelSize: 13
                font.weight: Font.Medium
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 56
            text: "Swipe up to open"
            color: "#ccffffff"
            font.family: "Inter"
            font.pixelSize: 13
            font.weight: Font.Medium
            SequentialAnimation on opacity {
                running: lock.visible
                loops: Animation.Infinite
                NumberAnimation { from: 0.45; to: 1.0; duration: 1200; easing.type: Easing.InOutSine }
                NumberAnimation { from: 1.0; to: 0.45; duration: 1200; easing.type: Easing.InOutSine }
            }
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 13
            width: 128; height: 5; radius: 2.5
            color: "#d9ffffff"
        }
    }

    MouseArea {
        anchors.fill: parent
        property real y0
        property real t0
        onPressed: (m) => { y0 = m.y; t0 = Date.now(); away.stop() }
        onPositionChanged: (m) => {
            var up = Math.max(0, y0 - m.y)
            face.y = -up
            face.opacity = 1 - Math.min(0.7, up / lock.height)
        }
        onReleased: (m) => {
            var up = y0 - m.y
            var speed = up / Math.max(1, Date.now() - t0)
            if (up > 140 || (up > 40 && speed > 0.5))
                away.start()
            else
                settle.start()
        }
    }

    ParallelAnimation {
        id: away
        NumberAnimation { target: face; property: "y"; to: -lock.height; duration: 260; easing.type: Easing.OutCubic }
        NumberAnimation { target: face; property: "opacity"; to: 0; duration: 240 }
        onFinished: shell.unlock()
    }
    ParallelAnimation {
        id: settle
        NumberAnimation { target: face; property: "y"; to: 0; duration: 240; easing.type: Easing.OutCubic }
        NumberAnimation { target: face; property: "opacity"; to: 1; duration: 200 }
    }
}
