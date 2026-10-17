import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import "bridge" as Backend

PlasmoidItem {
    id: root

    readonly property var status: bridge.snapshot
    readonly property bool connected: status.connected === true
    readonly property bool running: connected && status.state === "running"
    readonly property bool paused: connected && status.state === "paused"
    readonly property bool activeSession: running || paused
    readonly property bool elapsed: status.timer_mode === "elapsed"
    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
    readonly property string timeText: formatTime(elapsed ? status.elapsed_seconds : status.time_left)
    readonly property string stateText: !bridge.available ? i18n("Companion not running")
        : !connected ? i18n("Timer unavailable")
        : paused ? i18n("Paused")
        : running ? (elapsed ? i18n("Stopwatch") : i18n("Focus session"))
        : i18n("Ready to focus")
    readonly property string statusIcon: Qt.resolvedUrl("../images/pomocli-status-icon.svg")
    readonly property string timerIcon: status.feedback === true ? Qt.resolvedUrl("../images/bolt.svg")
        : paused ? "media-playback-pause"
        : !connected ? "network-disconnect"
        : statusIcon

    function formatTime(value) {
        const seconds = Math.max(0, Math.floor(Number(value) || 0));
        const minutes = Math.floor(seconds / 60);
        const suffix = String(seconds % 60).padStart(2, "0");
        if (seconds >= 3600)
            return String(Math.floor(seconds / 3600)) + ":" + String(minutes % 60).padStart(2, "0") + ":" + suffix;
        return String(minutes).padStart(2, "0") + ":" + suffix;
    }

    function runAction(name) {
        bridge.action(name);
    }

    Backend.DesktopBridge { id: bridge }

    preferredRepresentation: compactRepresentation
    toolTipMainText: activeSession && status.task_name ? status.task_name : i18n("PomoCLI Timer")
    toolTipSubText: stateText + (activeSession ? " · " + timeText : "")
    toolTipTextFormat: Text.PlainText
    Plasmoid.status: activeSession ? PlasmaCore.Types.ActiveStatus : PlasmaCore.Types.PassiveStatus

    compactRepresentation: Item {
        id: compact
        readonly property real horizontalWidth: compactRow.implicitWidth + Kirigami.Units.smallSpacing * 2
        Layout.minimumWidth: root.vertical ? 0 : horizontalWidth
        Layout.preferredWidth: root.vertical ? Kirigami.Units.gridUnit * 3 : horizontalWidth
        Layout.minimumHeight: root.vertical ? compactColumn.implicitHeight : 0
        Layout.preferredHeight: root.vertical ? compactColumn.implicitHeight : Kirigami.Units.gridUnit * 2
        implicitWidth: Layout.preferredWidth
        implicitHeight: Layout.preferredHeight

        RowLayout {
            id: compactRow
            anchors.centerIn: parent
            visible: !root.vertical
            spacing: Kirigami.Units.smallSpacing
            TimerIcon {
                source: root.timerIcon
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: implicitWidth
            }
            PlasmaComponents.Label {
                id: panelLabel
                text: root.activeSession ? root.timeText : (root.connected ? i18n("Pomo") : "--:--")
                font.family: "monospace"
                font.bold: root.running
                opacity: root.paused ? 0.65 : 1
                // Reserve stable space for the current timer format so ticks
                // never move neighboring panel items.
                Layout.minimumWidth: timerMetrics.width
            }
        }

        ColumnLayout {
            id: compactColumn
            anchors.centerIn: parent
            visible: root.vertical
            spacing: 0
            TimerIcon {
                source: root.timerIcon
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: implicitWidth
            }
            PlasmaComponents.Label {
                text: root.activeSession ? root.timeText : (root.connected ? i18n("Pomo") : "--:--")
                font.family: "monospace"
                font.pixelSize: Math.min(Kirigami.Theme.defaultFont.pixelSize,
                                        Math.max(9, compact.width / Math.max(5, text.length) * 1.5))
                opacity: root.paused ? 0.65 : 1
                Layout.alignment: Qt.AlignHCenter
            }
        }

        TextMetrics {
            id: timerMetrics
            font: panelLabel.font
            text: "0".repeat(Math.max(5, root.timeText.length))
        }

        QQC2.AbstractButton {
            anchors.fill: parent
            Accessible.name: i18n("PomoCLI timer: %1", root.stateText)
            Accessible.description: root.activeSession ? root.timeText : ""
            onClicked: root.expanded = !root.expanded
            background: Rectangle {
                radius: Kirigami.Units.smallSpacing
                color: Kirigami.Theme.highlightColor
                opacity: parent.down ? 0.25 : parent.hovered ? 0.12 : 0
            }
        }
    }

    fullRepresentation: ColumnLayout {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 15
        Layout.preferredWidth: Kirigami.Units.gridUnit * 19
        Layout.minimumHeight: implicitHeight
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Label {
            text: root.activeSession ? root.timeText : i18n("PomoCLI")
            textFormat: Text.PlainText
            font.family: root.activeSession ? "monospace" : Kirigami.Theme.defaultFont.family
            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 1.8
            font.bold: true
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Kirigami.Units.largeSpacing
        }
        PlasmaComponents.Label {
            text: root.stateText
            textFormat: Text.PlainText
            Layout.alignment: Qt.AlignHCenter
        }
        PlasmaComponents.Label {
            visible: root.activeSession && !!root.status.task_name
            text: root.status.task_name || ""
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }
        PlasmaComponents.Label {
            visible: root.activeSession && !!root.status.project_name
            text: root.status.project_name || ""
            textFormat: Text.PlainText
            opacity: 0.7
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }

        Kirigami.InlineMessage {
            visible: bridge.lastError.length > 0
            text: bridge.lastError
            type: Kirigami.MessageType.Error
            Layout.fillWidth: true
            actions: [Kirigami.Action {
                text: i18n("Dismiss")
                onTriggered: bridge.clearError()
            }]
        }
        PlasmaComponents.Label {
            visible: !bridge.available
            text: i18n("Open PomoCLI Desktop from your application launcher to connect.")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        PlasmaComponents.Button {
            text: i18n("Quick Start…")
            icon.name: "list-add"
            enabled: bridge.available && !bridge.busy && !root.activeSession
            Layout.fillWidth: true
            onClicked: root.runAction("quick-start")
        }
        PlasmaComponents.Button {
            text: i18n("Log Distraction")
            icon.source: Qt.resolvedUrl("../images/bolt.svg")
            enabled: root.running && !bridge.busy && root.status.feedback !== true
            Layout.fillWidth: true
            onClicked: root.runAction("distract")
        }
        PlasmaComponents.Button {
            text: root.paused ? i18n("Resume") : i18n("Pause")
            icon.name: root.paused ? "media-playback-start" : "media-playback-pause"
            enabled: root.activeSession && !bridge.busy
            Layout.fillWidth: true
            onClicked: root.runAction(root.paused ? "resume" : "pause")
        }
        PlasmaComponents.Button {
            text: i18n("Stop and Save")
            icon.name: "media-playback-stop"
            enabled: root.activeSession && !bridge.busy
            Layout.fillWidth: true
            onClicked: root.runAction("stop")
        }
        PlasmaComponents.Button {
            visible: root.activeSession && root.elapsed
            text: i18n("Complete Session")
            icon.name: "dialog-ok-apply"
            enabled: root.activeSession && !bridge.busy
            Layout.fillWidth: true
            onClicked: root.runAction("complete")
        }
        PlasmaComponents.Button {
            text: i18n("Quit Companion")
            icon.name: "application-exit"
            enabled: bridge.available && !bridge.busy
            Layout.fillWidth: true
            Layout.bottomMargin: Kirigami.Units.largeSpacing
            onClicked: bridge.quit()
        }
    }
}
