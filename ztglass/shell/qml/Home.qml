// The home screen: the wallpaper, pages of apps four across, and the dock of
// four under a pane of glass. It lies under every app (layer: background).
import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

Window {
    id: win
    visible: true
    color: "black"
    title: "ztGlass Home"
    width: Screen.width
    height: Screen.height

    LayerShell.Window.scope: "ztglass-home"
    LayerShell.Window.layer: LayerShell.Window.LayerBackground
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorBottom
                               | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone

    // the geometry, in points
    readonly property real statusH: 34
    readonly property real side: 14
    readonly property real dockMargin: 12
    readonly property real dockH: 92
    readonly property real dockY: height - dockMargin - dockH
    readonly property real dotsH: 22
    readonly property real dotsY: dockY - 14 - dotsH
    readonly property real gridTop: statusH + 20
    readonly property real cellW: (width - 2 * side) / 4
    readonly property real cellH: 96
    readonly property int rows: Math.max(1, Math.floor((dotsY - 6 - gridTop) / cellH))
    readonly property int perPage: rows * 4
    readonly property int pages: Math.max(1, Math.ceil(shell.apps.length / perPage))

    Image {
        anchors.fill: parent
        source: shell.wallpaper
        sourceSize: Qt.size(Math.round(width * Screen.devicePixelRatio), Math.round(height * Screen.devicePixelRatio))
        fillMode: Image.PreserveAspectCrop
        cache: false
    }

    // everything that comes back when an app goes
    Item {
        id: stage
        anchors.fill: parent
        transformOrigin: Item.Center

        ListView {
            id: pager
            x: 0
            y: win.gridTop
            width: win.width
            height: win.rows * win.cellH
            orientation: ListView.Horizontal
            snapMode: ListView.SnapOneItem
            highlightRangeMode: ListView.StrictlyEnforceRange
            highlightMoveDuration: 320
            boundsBehavior: Flickable.DragOverBounds
            flickDeceleration: 2400
            maximumFlickVelocity: 5000
            cacheBuffer: width * 2
            pressDelay: 0
            model: win.pages
            delegate: Item {
                id: page
                required property int index
                width: pager.width
                height: pager.height
                Grid {
                    x: win.side
                    columns: 4
                    Repeater {
                        model: shell.apps.slice(page.index * win.perPage, (page.index + 1) * win.perPage)
                        delegate: Item {
                            required property var modelData
                            width: win.cellW
                            height: win.cellH
                            AppIcon {
                                anchors.horizontalCenter: parent.horizontalCenter
                                app: parent.modelData
                                onOpen: (icon, app) => win.open(icon, app)
                            }
                        }
                    }
                }
            }
        }

        // which page: dots on a small pane of glass
        Item {
            id: dots
            visible: win.pages > 1
            width: win.pages * 15 + 14
            height: win.dotsH
            x: Math.round((win.width - width) / 2)
            y: win.dotsY
            Image {
                anchors.fill: parent
                source: dots.visible ? shell.glassTint(dots.x, dots.y, dots.width, dots.height, dots.height / 2, 0.10) : ""
            }
            Row {
                anchors.centerIn: parent
                spacing: 8
                Repeater {
                    model: win.pages
                    Rectangle {
                        required property int index
                        width: 7; height: 7; radius: 3.5
                        color: "white"
                        opacity: pager.currentIndex === index ? 0.95 : 0.4
                        Behavior on opacity { NumberAnimation { duration: 200 } }
                    }
                }
            }
        }

        // the dock
        Item {
            id: dock
            x: win.dockMargin
            y: win.dockY
            width: win.width - 2 * win.dockMargin
            height: win.dockH
            Image {
                anchors.fill: parent
                source: shell.glass(dock.x, dock.y, dock.width, dock.height, 32)
            }
            Row {
                id: dockRow
                readonly property real gap: (dock.width - 4 * 82) / 5
                x: gap
                anchors.verticalCenter: parent.verticalCenter
                spacing: gap
                Repeater {
                    model: shell.dock
                    AppIcon {
                        required property var modelData
                        app: modelData
                        label: false
                        onOpen: (icon, app) => win.open(icon, app)
                    }
                }
            }
        }
    }

    // an app opening: its colour grows out of its icon to the whole screen
    Rectangle {
        id: zoom
        visible: false
        radius: 15
        property var app
        color: app ? app.tint : "black"
        Image {
            id: zoomIcon
            anchors.centerIn: parent
            width: 62; height: 62
            source: zoom.app ? zoom.app.icon_url : ""
        }
    }

    ParallelAnimation {
        id: grow
        NumberAnimation { target: zoom; property: "x"; to: 0; duration: 300; easing.type: Easing.OutCubic }
        NumberAnimation { target: zoom; property: "y"; to: 0; duration: 300; easing.type: Easing.OutCubic }
        NumberAnimation { target: zoom; property: "width"; to: win.width; duration: 300; easing.type: Easing.OutCubic }
        NumberAnimation { target: zoom; property: "height"; to: win.height; duration: 300; easing.type: Easing.OutCubic }
        NumberAnimation { target: zoom; property: "radius"; to: 38; duration: 300 }
        NumberAnimation { target: zoomIcon; property: "opacity"; from: 1; to: 0; duration: 260 }
        NumberAnimation { target: zoomIcon; property: "scale"; from: 1; to: 1.8; duration: 300; easing.type: Easing.OutCubic }
        NumberAnimation { target: stage; property: "scale"; to: 1.08; duration: 300; easing.type: Easing.OutCubic }
        NumberAnimation { target: stage; property: "opacity"; to: 0.0; duration: 260 }
    }

    // back home: the apps settle in from a little larger
    ParallelAnimation {
        id: back
        NumberAnimation { target: stage; property: "scale"; from: 1.1; to: 1.0; duration: 380; easing.type: Easing.OutCubic }
        NumberAnimation { target: stage; property: "opacity"; from: 0.0; to: 1.0; duration: 260 }
    }

    // an app that never comes: give the home screen back
    Timer {
        id: giveUp
        interval: 9000
        onTriggered: win.reset(true)
    }

    function open(icon, app) {
        if (grow.running || zoom.visible)
            return
        var p = icon.mapToItem(win.contentItem, 0, 0)
        zoom.app = app
        zoom.x = p.x; zoom.y = p.y
        zoom.width = icon.width; zoom.height = icon.height
        zoom.radius = 15
        zoomIcon.opacity = 1; zoomIcon.scale = 1
        zoom.visible = true
        grow.start()
        giveUp.restart()
        shell.launch(app.key)
    }

    function reset(animated) {
        giveUp.stop()
        grow.stop()
        zoom.visible = false
        if (animated) {
            back.start()
        } else {
            stage.scale = 1
            stage.opacity = 1
        }
    }

    Connections {
        target: shell
        function onWentHome() {
            if (zoom.visible || stage.opacity < 1) {
                win.reset(true)
            } else {
                // home while home: the first page
                pager.currentIndex = 0
            }
        }
        function onOpenedApp(key) {
            // the app is over us now: be ready for its return
            hideZoom.restart()
        }
    }

    Timer {
        id: hideZoom
        interval: 260
        onTriggered: {
            giveUp.stop()
            zoom.visible = false
            stage.scale = 1.1
            stage.opacity = 0
        }
    }
}
