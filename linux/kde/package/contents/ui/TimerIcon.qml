import QtQuick
import org.kde.kirigami as Kirigami

Item {
    id: root

    property string source
    property color color: Kirigami.Theme.textColor
    property bool disconnected: false
    readonly property string statusIcon: Qt.resolvedUrl("../images/pomocli-status-icon.svg")
    readonly property bool showStatusIcon: source === statusIcon
    readonly property bool lightForeground: color.r * 0.2126 + color.g * 0.7152 + color.b * 0.0722 > 0.5

    implicitWidth: Kirigami.Units.iconSizes.small
    implicitHeight: implicitWidth

    // Both variants contain the original vector paths. Rasterize at the small
    // display size without relying on mask shaders or global Plasma SVG colors.
    Image {
        anchors.fill: parent
        source: root.lightForeground ? Qt.resolvedUrl("../images/pomocli-status-icon-light.svg") : root.statusIcon
        sourceSize.width: Math.max(1, width)
        sourceSize.height: Math.max(1, height)
        fillMode: Image.PreserveAspectFit
        visible: root.showStatusIcon
    }

    Kirigami.Icon {
        anchors.fill: parent
        source: root.source
        visible: !root.showStatusIcon
    }

    Rectangle {
        objectName: "disconnectSlash"
        anchors.centerIn: parent
        visible: root.disconnected
        width: Math.min(root.width, root.height) * 1.1
        height: Math.max(2, Math.min(5, Math.min(root.width, root.height) * 0.085))
        radius: height / 2
        rotation: -45
        color: Kirigami.Theme.negativeTextColor
    }
}
