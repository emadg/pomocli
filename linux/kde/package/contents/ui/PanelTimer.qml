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
    readonly property real timerFontSize: Math.max(9, Math.min(Math.max(12, Kirigami.Theme.defaultFont.pixelSize),
        Math.max(1, height - edge * 2) * 100 / Math.max(1, panelFontMetrics.height)))
    implicitWidth: vertical ? Kirigami.Units.gridUnit * 3
        : activeSession ? sessionRow.implicitWidth + edge * 2 : Math.max(24, height)
    implicitHeight: vertical ? (activeSession && showVerticalTimer ? sessionColumn.implicitHeight + edge * 2 : Math.max(24, width))
        : Kirigami.Units.gridUnit * 2
    Layout.minimumWidth: vertical ? 24 : activeSession ? sessionRow.implicitWidth + edge * 2 : 24
    Layout.preferredWidth: implicitWidth
    Layout.minimumHeight: vertical && activeSession && showVerticalTimer ? sessionColumn.implicitHeight + edge * 2 : 24
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
        RowLayout {
            id: sessionRow
            anchors.centerIn: parent
            visible: root.activeSession && !root.vertical
            spacing: root.edge
            TimerIcon { source: root.iconSource; color: root.foregroundColor }
            Text {
                objectName: "horizontalTimer"
                text: root.timeText
                textFormat: Text.PlainText
                color: root.foregroundColor
                font.family: "monospace"
                font.pixelSize: root.timerFontSize
                font.bold: !root.paused
                opacity: root.paused ? 0.65 : 1
                Layout.minimumWidth: timerMetrics.width
            }
        }
        ColumnLayout {
            id: sessionColumn
            anchors.centerIn: parent
            visible: root.activeSession && root.vertical && root.showVerticalTimer
            spacing: 0
            TimerIcon {
                source: root.iconSource
                color: root.foregroundColor
                Layout.alignment: Qt.AlignHCenter
            }
            Text {
                objectName: "verticalTimer"
                text: root.timeText
                textFormat: Text.PlainText
                color: root.foregroundColor
                font.family: "monospace"
                font.pixelSize: Math.min(Math.max(12, Kirigami.Theme.defaultFont.pixelSize),
                    Math.max(9, (root.width - root.edge * 2) / Math.max(5, text.length) / 0.65))
                opacity: root.paused ? 0.65 : 1
                Layout.alignment: Qt.AlignHCenter
            }
        }
    }

    TextMetrics {
        id: timerMetrics
        font.family: "monospace"
        font.pixelSize: root.timerFontSize
        font.bold: true
        text: "0".repeat(Math.max(5, root.timeText.length))
    }
    TextMetrics {
        id: verticalMetrics
        font.family: "monospace"
        font.pixelSize: 9
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
