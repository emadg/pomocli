import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

QQC2.AbstractButton {
    id: root

    property bool connected: false
    property bool activeSession: false
    property bool paused: false
    property string timeText: "00:00"
    property string stateText
    property string taskName
    property string projectName
    property string iconSource: Qt.resolvedUrl("../images/pomocli-status-icon.svg")
    property color foregroundColor: Kirigami.Theme.textColor
    property color surfaceColor: Kirigami.Theme.backgroundColor

    readonly property bool showTitle: !activeSession && width >= 128 && height >= 32
    readonly property bool showCaption: showTitle && width >= 176 && height >= 96
    // The timer takes priority at every size; reduce secondary content first.
    readonly property bool showTimer: activeSession
    readonly property bool showHeader: showTimer && width >= 144 && height >= 72
    readonly property bool showTask: showTimer && width >= 132 && height >= 112 && taskName.length > 0
    readonly property bool showProject: showTimer && width >= 132 && height >= 144 && projectName.length > 0
    readonly property real baseFontSize: Math.max(12, Kirigami.Theme.defaultFont.pixelSize)
    readonly property real titleFontSize: Math.max(1, Math.min(48, face.width * 0.17, face.height * 0.75))
    readonly property real idleIconSize: Math.max(8, Math.min(128,
        showTitle ? face.width - titleMetrics.advanceWidth - idleRow.spacing : face.width,
        face.height - (showCaption ? caption.implicitHeight + Kirigami.Units.smallSpacing : 0)))
    readonly property real minimumWidth: activeSession ? Math.max(96, Math.ceil(timerMetrics.advanceWidth * 0.18) + 16) : 32
    readonly property real minimumHeight: activeSession ? 36 : 32
    readonly property real reservedHeight: (showHeader ? sessionHeader.implicitHeight + sessionColumn.spacing : 0)
        + (details.visible ? details.implicitHeight + sessionColumn.spacing : 0)
    readonly property real timerFontSize: Math.max(1, Math.min(112,
        face.width * 100 / Math.max(1, timerMetrics.width),
        Math.max(1, face.height - reservedHeight) * 100 / Math.max(1, timerMetrics.height)))

    implicitWidth: 264
    implicitHeight: 176
    padding: Math.min(8, Math.min(width, height) * 0.06)
    focusPolicy: Qt.StrongFocus
    Accessible.name: qsTr("PomoCLI timer: %1").arg(stateText)
    Accessible.description: activeSession
        ? [projectName, taskName, timeText].filter(text => text.length > 0).join(". ") : ""

    contentItem: Item {
        id: face
        RowLayout {
            id: idleRow
            anchors.centerIn: parent
            anchors.verticalCenterOffset: root.showCaption ? -(caption.implicitHeight + Kirigami.Units.smallSpacing) / 2 : 0
            visible: !root.showTimer
            spacing: Kirigami.Units.smallSpacing * 2
            TimerIcon {
                objectName: "idleGlyph"
                source: root.iconSource
                color: root.foregroundColor
                disconnected: !root.connected
                implicitWidth: root.idleIconSize
                implicitHeight: implicitWidth
            }
            Text {
                objectName: "pomoTitle"
                visible: root.showTitle
                text: qsTr("Pomo")
                color: root.foregroundColor
                font.pixelSize: root.titleFontSize
                font.bold: true
            }
        }
        Text {
            id: caption
            objectName: "readyCaption"
            anchors.top: idleRow.bottom
            anchors.topMargin: Kirigami.Units.smallSpacing
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            visible: root.showCaption
            text: root.connected ? qsTr("Ready to focus! 🍅👀") : qsTr("Not connected")
            textFormat: Text.PlainText
            color: root.connected ? root.foregroundColor : Kirigami.Theme.negativeTextColor
            opacity: root.connected ? 0.8 : 1
            font.pixelSize: root.baseFontSize
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
        ColumnLayout {
            id: sessionColumn
            anchors.centerIn: parent
            width: parent.width
            visible: root.showTimer
            spacing: Math.max(4, Math.min(12, root.height * 0.035))
            RowLayout {
                id: sessionHeader
                objectName: "sessionHeader"
                visible: root.showHeader
                Layout.alignment: Qt.AlignHCenter
                Layout.fillWidth: false
                Layout.maximumWidth: face.width
                spacing: Kirigami.Units.smallSpacing
                TimerIcon { objectName: "sessionGlyph"; source: root.iconSource; color: root.foregroundColor }
                Text {
                    objectName: "sessionState"
                    text: root.stateText
                    textFormat: Text.PlainText
                    color: root.foregroundColor
                    font.pixelSize: root.baseFontSize
                    opacity: 0.75
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            Text {
                objectName: "sessionTimer"
                text: root.timeText
                textFormat: Text.PlainText
                color: root.foregroundColor
                font.family: "monospace"
                font.pixelSize: root.timerFontSize
                fontSizeMode: Text.Fit
                minimumPixelSize: 1
                font.bold: true
                opacity: root.paused ? 0.65 : 1
                horizontalAlignment: Text.AlignHCenter
                Layout.fillWidth: true
                Layout.minimumWidth: 0
            }
            ColumnLayout {
                id: details
                visible: root.showTask || root.showProject
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 2
                Text {
                    id: taskLabel
                    objectName: "taskLabel"
                    visible: root.showTask
                    text: root.taskName
                    textFormat: Text.PlainText
                    color: root.foregroundColor
                    font.pixelSize: Math.min(18, root.baseFontSize * 1.15)
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                }
                Text {
                    id: projectLabel
                    objectName: "projectLabel"
                    visible: root.showProject
                    text: root.projectName
                    textFormat: Text.PlainText
                    color: root.foregroundColor
                    opacity: 0.7
                    font.pixelSize: root.baseFontSize
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                }
            }
        }
    }
    TextMetrics {
        id: titleMetrics
        font.pixelSize: root.titleFontSize
        font.bold: true
        text: qsTr("Pomo")
    }
    TextMetrics {
        id: timerMetrics
        font.family: "monospace"
        font.pixelSize: 100
        font.bold: true
        text: "0".repeat(Math.max(5, root.timeText.length))
    }
    background: Rectangle {
        radius: Kirigami.Units.smallSpacing * 2
        color: root.surfaceColor
        opacity: root.activeSession || root.showTitle ? 0.94 : root.hovered || root.visualFocus ? 0.7 : 0
        border.width: root.visualFocus ? 1 : 0
        border.color: Kirigami.Theme.highlightColor
    }
}
