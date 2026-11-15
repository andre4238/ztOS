// One app: its icon, and its name under it (not in the dock).
import QtQuick

Item {
    id: root
    property var app
    property bool label: true
    property real size: 62
    signal open(Item icon, var app)

    width: size + 20
    height: label ? size + 22 : size

    Image {
        id: icon
        width: root.size
        height: root.size
        anchors.horizontalCenter: parent.horizontalCenter
        source: root.app ? root.app.icon_url : ""
        sourceSize: Qt.size(Math.round(root.size * Screen.devicePixelRatio), Math.round(root.size * Screen.devicePixelRatio))
        smooth: true
        asynchronous: false
        scale: area.pressed ? 0.88 : 1.0
        opacity: area.pressed ? 0.82 : 1.0
        Behavior on scale { NumberAnimation { duration: area.pressed ? 90 : 220; easing.type: Easing.OutBack; easing.overshoot: 2.2 } }
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }

    Text {
        visible: root.label
        anchors.top: icon.bottom
        anchors.topMargin: 5
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        text: root.app ? root.app.name : ""
        color: "white"
        font.family: "Inter"
        font.pixelSize: 12
        font.weight: Font.Medium
        style: Text.Raised
        styleColor: "#55000000"
    }

    MouseArea {
        id: area
        anchors.fill: parent
        onClicked: root.open(icon, root.app)
    }
}
