// The control centre: pulled down from the status bar, over whatever shows.
// Wi-Fi, flight mode, the volume, the screen off, and a few apps at hand.
import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

Window {
    id: cc
    visible: shell.control
    color: "transparent"
    title: "ztGlass Control"
    width: Screen.width
    height: Screen.height

    LayerShell.Window.scope: "ztglass-control"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorBottom
                               | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone

    property bool wifiOn: true
    property bool planeOn: false

    onVisibleChanged: {
        if (visible) {
            wifiOn = shell.wifiEnabled()
            planeOn = shell.airplane()
            panel.opacity = 0
            panel.scale = 0.94
            come.start()
        }
    }

    ParallelAnimation {
        id: come
        NumberAnimation { target: panel; property: "opacity"; to: 1; duration: 200 }
        NumberAnimation { target: panel; property: "scale"; to: 1; duration: 300; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
        NumberAnimation { target: shade; property: "opacity"; from: 0; to: 1; duration: 220 }
    }
    ParallelAnimation {
        id: go
        NumberAnimation { target: panel; property: "opacity"; to: 0; duration: 160 }
        NumberAnimation { target: panel; property: "scale"; to: 0.94; duration: 180 }
        NumberAnimation { target: shade; property: "opacity"; to: 0; duration: 180 }
        onFinished: shell.showControl(false)
    }

    // the blurred wallpaper, darkened, over everything
    Item {
        id: shade
        anchors.fill: parent
        Image {
            anchors.fill: parent
            source: shell.wallpaperBlur
            fillMode: Image.PreserveAspectCrop
            opacity: 0.92
        }
        Rectangle { anchors.fill: parent; color: "#59000000" }
    }

    MouseArea {
        anchors.fill: parent
        property real y0
        onPressed: (m) => y0 = m.y
        onReleased: (m) => go.start()
    }

    component Tile: Rectangle {
        radius: 26
        color: "#26ffffff"
        border.color: "#3dffffff"
        border.width: 1
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#1fffffff" }
                GradientStop { position: 0.5; color: "#00ffffff" }
            }
        }
    }

    component Toggle: Item {
        id: t
        property bool on: false
        property color tint: "#0a84ff"
        property string glyph: ""
        property string label: ""
        signal toggled()
        width: 64; height: 84
        Rectangle {
            id: knob
            width: 58; height: 58; radius: 29
            anchors.horizontalCenter: parent.horizontalCenter
            color: t.on ? t.tint : "#33ffffff"
            border.color: t.on ? "transparent" : "#30ffffff"
            Behavior on color { ColorAnimation { duration: 160 } }
            scale: ta.pressed ? 0.9 : 1
            Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutBack } }
            Text {
                anchors.centerIn: parent
                text: t.glyph
                color: "white"
                font.family: "Inter"
                font.pixelSize: 22
                font.weight: Font.DemiBold
            }
        }
        Text {
            anchors.top: knob.bottom
            anchors.topMargin: 6
            anchors.horizontalCenter: parent.horizontalCenter
            text: t.label
            color: "#e6ffffff"
            font.family: "Inter"
            font.pixelSize: 11
            font.weight: Font.Medium
        }
        MouseArea { id: ta; anchors.fill: parent; onClicked: t.toggled() }
    }

    Item {
        id: panel
        width: cc.width - 32
        x: 16
        y: 64
        height: 360
        transformOrigin: Item.Top

        MouseArea { anchors.fill: parent }   // taps between the tiles stay here

        Tile {
            id: radios
            width: (panel.width - 14) / 2
            height: width
            Grid {
                anchors.centerIn: parent
                columns: 2
                spacing: 6
                Toggle {
                    on: cc.planeOn
                    tint: "#ff9f0a"
                    glyph: "✈"
                    label: "Flight"
                    onToggled: { cc.planeOn = !cc.planeOn; shell.setAirplane(cc.planeOn) }
                }
                Toggle {
                    on: cc.wifiOn
                    glyph: "◠"
                    label: "Wi-Fi"
                    onToggled: { cc.wifiOn = !cc.wifiOn; shell.setWifi(cc.wifiOn) }
                }
            }
        }

        // the volume: a tall slider, as full as it is loud
        Tile {
            id: vol
            x: radios.width + 14
            width: (panel.width - 14 - 14) / 4
            height: radios.height
            clip: true
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: parent.height * shell.volume
                radius: parent.radius
                color: "#f2ffffff"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 14
                text: shell.muted ? "🔇" : "🔊"
                font.pixelSize: 18
                color: shell.volume > 0.15 ? "#333" : "white"
            }
            MouseArea {
                anchors.fill: parent
                function at(m) { shell.setVolume(1 - m.y / height) }
                onPressed: (m) => at(m)
                onPositionChanged: (m) => at(m)
            }
        }

        // the screen off
        Tile {
            x: vol.x + vol.width + 14
            width: vol.width
            height: radios.height
            Text {
                anchors.centerIn: parent
                text: "⏻"
                color: "white"
                font.pixelSize: 26
            }
            MouseArea { anchors.fill: parent; onClicked: shell.sleep() }
        }

        // a few apps at hand
        Repeater {
            model: shell.dock.concat(shell.apps).filter(function (a) {
                return ["ztcamera.desktop", "ztsettings.desktop", "ztsound.desktop", "ztpower.desktop"].indexOf(a.key) >= 0
            }).slice(0, 4)
            Tile {
                required property var modelData
                required property int index
                y: radios.height + 14
                x: index * (width + 14)
                width: (panel.width - 3 * 14) / 4
                height: width
                Image {
                    anchors.centerIn: parent
                    width: 40; height: 40
                    source: parent.modelData.icon_url
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: { shell.showControl(false); shell.launch(parent.modelData.key) }
                }
            }
        }
    }
}
