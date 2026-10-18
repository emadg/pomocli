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
    readonly property real iconExtent: Math.min(width, height)
    readonly property real slashLength: iconExtent * 1.24
    readonly property real slashThickness: Math.max(2, Math.min(7, iconExtent * 0.075))
    readonly property real slashGap: Math.max(1.6, Math.min(5, iconExtent * 0.055))

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
        visible: root.showStatusIcon && !root.disconnected
    }

    Canvas {
        id: cutout
        objectName: "disconnectCutout"
        anchors.fill: parent
        visible: root.showStatusIcon && root.disconnected
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Immediate
        antialiasing: true
        readonly property url imageSource: root.lightForeground
            ? Qt.resolvedUrl("../images/pomocli-status-icon-light-canvas.svg")
            : Qt.resolvedUrl("../images/pomocli-status-icon-dark-canvas.svg")
        property url loadedSource

        function updateSource() {
            if (!available)
                return;
            if (loadedSource.toString().length > 0 && (!visible || loadedSource !== imageSource)) {
                unloadImage(loadedSource);
                loadedSource = "";
            }
            if (visible) {
                loadedSource = imageSource;
                loadImage(imageSource);
                requestPaint();
            }
        }
        onAvailableChanged: updateSource()
        onVisibleChanged: updateSource()
        onImageSourceChanged: updateSource()
        onImageLoaded: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            ctx.clearRect(0, 0, width, height);
            if (!visible || !isImageLoaded(imageSource))
                return;
            const imageWidth = Math.min(width, height * 981 / 833);
            const imageHeight = imageWidth * 833 / 981;
            ctx.drawImage(imageSource, (width - imageWidth) / 2, (height - imageHeight) / 2, imageWidth, imageHeight);
            // Erase alpha around the slash, leaving the background visible.
            const offset = (root.slashLength - root.slashThickness) / (2 * Math.SQRT2);
            ctx.globalCompositeOperation = "destination-out";
            ctx.strokeStyle = "white";
            ctx.lineWidth = root.slashThickness + root.slashGap * 2;
            ctx.lineCap = "round";
            ctx.beginPath();
            ctx.moveTo(width / 2 - offset, height / 2 + offset);
            ctx.lineTo(width / 2 + offset, height / 2 - offset);
            ctx.stroke();
        }
    }

    Kirigami.Icon {
        anchors.fill: parent
        source: root.source
        visible: !root.showStatusIcon
    }

    Item {
        objectName: "disconnectSlash"
        anchors.centerIn: parent
        visible: root.disconnected
        width: root.slashLength
        height: root.slashThickness
        rotation: -45
        Rectangle {
            objectName: "disconnectSlashStroke"
            anchors.centerIn: parent
            width: root.slashLength
            height: root.slashThickness
            radius: height / 2
            color: Kirigami.Theme.negativeTextColor
            antialiasing: true
        }
    }
}
