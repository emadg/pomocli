import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

QQC2.AbstractButton {
    id: root

    property bool connected: false
    property bool activeSession: false
    property bool paused: false
    property bool vertical: false
    property string timeText: "00:00"
    property string stateText
    property string iconSource: Qt.resolvedUrl("../images/pomocli-status-icon.svg")
    property color foregroundColor: Kirigami.Theme.textColor

    readonly property real edge: Kirigami.Units.smallSpacing
    readonly property real idleExtent: 0.85 * Math.max(16, Math.min(48, (vertical ? width : height) - edge * 2))
    readonly property bool showVerticalTimer: width >= verticalMetrics.advanceWidth + edge * 2
    readonly property real sessionPadding: vertical ? edge : Math.min(edge, Math.max(1, (height - 20) / 4))
    readonly property real sessionIconSize: vertical ? 16 : Math.max(8, Math.min(16, Math.round(height * 0.28)))
    readonly property real timerFontSize: vertical
        ? Math.max(9, Math.min(24, (width - edge * 2) * 100 / Math.max(1, formatMetrics.advanceWidth)))
        : Math.max(9, Math.min(28,
            Math.max(1, height - sessionPadding * 2 - sessionIconSize) * 100 / Math.max(1, panelFontMetrics.height)))
    implicitWidth: vertical ? Kirigami.Units.gridUnit * 3
        : activeSession ? sessionColumn.implicitWidth + sessionPadding * 2 : Math.max(24, height)
    implicitHeight: vertical ? (activeSession && showVerticalTimer ? sessionColumn.implicitHeight + sessionPadding * 2 : Math.max(24, width))
        : Kirigami.Units.gridUnit * 2
    Layout.minimumWidth: vertical ? 24 : activeSession ? sessionColumn.implicitWidth + sessionPadding * 2 : 24
    Layout.preferredWidth: implicitWidth
    Layout.minimumHeight: vertical && activeSession && showVerticalTimer ? sessionColumn.implicitHeight + sessionPadding * 2 : 24
    Layout.preferredHeight: implicitHeight
    padding: 0
    focusPolicy: Qt.StrongFocus

    Accessible.name: qsTr("PomoCLI timer: %1").arg(stateText)
    Accessible.description: activeSession ? timeText : ""

    contentItem: Item {
        TimerIcon {
            objectName: "idleGlyph"
            anchors.centerIn: parent
            visible: !root.activeSession || (root.vertical && !root.showVerticalTimer)
            source: root.iconSource
            color: root.foregroundColor
            disconnected: !root.connected
            width: root.idleExtent
            height: width
        }
        ColumnLayout {
            id: sessionColumn
            anchors.centerIn: parent
            visible: root.activeSession && (!root.vertical || root.showVerticalTimer)
            spacing: 0
            TimerIcon {
                objectName: "sessionGlyph"
                source: root.iconSource
                color: root.foregroundColor
                implicitWidth: root.sessionIconSize
                implicitHeight: implicitWidth
                Layout.alignment: Qt.AlignHCenter
            }
            Text {
                objectName: "panelTimer"
                text: root.timeText
                textFormat: Text.PlainText
                color: root.foregroundColor
                font.family: "monospace"
                font.pixelSize: root.timerFontSize
                font.letterSpacing: 0
                font.bold: !root.paused
                fontSizeMode: Text.Fit
                minimumPixelSize: 9
                opacity: root.paused ? 0.65 : 1
                horizontalAlignment: Text.AlignHCenter
                Layout.minimumWidth: timerMetrics.advanceWidth
                Layout.maximumWidth: timerMetrics.advanceWidth
                Layout.alignment: Qt.AlignHCenter
            }
        }
    }

    TextMetrics {
        id: timerMetrics
        font.family: "monospace"
        font.pixelSize: root.timerFontSize
        font.bold: true
        font.letterSpacing: 0
        text: "0".repeat(Math.max(5, root.timeText.length))
    }
    TextMetrics {
        id: verticalMetrics
        font.family: "monospace"
        font.pixelSize: 9
        font.bold: true
        font.letterSpacing: 0
        text: "0".repeat(Math.max(5, root.timeText.length))
    }
    TextMetrics {
        id: formatMetrics
        font.family: "monospace"
        font.pixelSize: 100
        font.bold: true
        font.letterSpacing: 0
        text: "0".repeat(Math.max(5, root.timeText.length))
    }
    FontMetrics {
        id: panelFontMetrics
        font.family: "monospace"
        font.pixelSize: 100
        font.bold: true
    }
    background: Rectangle {
        radius: Kirigami.Units.smallSpacing
        color: Kirigami.Theme.highlightColor
        opacity: root.down ? 0.25 : root.hovered || root.visualFocus ? 0.12 : 0
    }
}
