import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.ksvg as KSvg

Item {
    id: root

    property string source
    property color color: Kirigami.Theme.textColor
    readonly property string statusIcon: Qt.resolvedUrl("../images/pomocli-status-icon.svg")
    readonly property bool showStatusIcon: source === statusIcon

    implicitWidth: Kirigami.Units.iconSizes.small
    implicitHeight: implicitWidth

    // KSvg applies Plasma's palette to the template, including with Qt's
    // software renderer. Preserve the original Mac icon's aspect ratio.
    KSvg.SvgItem {
        anchors.centerIn: parent
        width: Math.min(root.width, root.height * 981 / 833)
        height: width * 833 / 981
        imagePath: root.statusIcon
        visible: root.showStatusIcon
        Kirigami.Theme.inherit: false
        Kirigami.Theme.textColor: root.color
    }

    Kirigami.Icon {
        anchors.fill: parent
        source: root.source
        visible: !root.showStatusIcon
    }
}
