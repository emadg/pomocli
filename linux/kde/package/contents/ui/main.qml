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
    readonly property bool connected: bridge.available && status.connected === true
    readonly property bool running: connected && status.state === "running"
    readonly property bool paused: connected && status.state === "paused"
    readonly property bool activeSession: running || paused
    readonly property bool elapsed: status.timer_mode === "elapsed"
    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
    readonly property bool inPanel: vertical || Plasmoid.formFactor === PlasmaCore.Types.Horizontal
    readonly property string timeText: formatTime(elapsed ? status.elapsed_seconds : status.time_left)
    readonly property string stateText: !bridge.available ? i18n("Companion not running")
        : !connected ? i18n("Timer unavailable")
        : paused ? i18n("Paused")
        : running ? (elapsed ? i18n("Stopwatch") : i18n("Focus session"))
        : i18n("Ready to focus")
    readonly property string statusIcon: Qt.resolvedUrl("../images/pomocli-status-icon.svg")
    readonly property string timerIcon: activeSession && status.feedback === true ? Qt.resolvedUrl("../images/bolt.svg")
        : paused ? "media-playback-pause"
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

    preferredRepresentation: inPanel ? compactRepresentation : fullRepresentation
    toolTipMainText: activeSession && status.task_name ? status.task_name : i18n("PomoCLI Timer")
    toolTipSubText: stateText + (activeSession ? " · " + timeText : "")
    toolTipTextFormat: Text.PlainText
    Plasmoid.status: activeSession ? PlasmaCore.Types.ActiveStatus : PlasmaCore.Types.PassiveStatus
    Plasmoid.backgroundHints: root.inPanel ? PlasmaCore.Types.DefaultBackground : PlasmaCore.Types.NoBackground

    compactRepresentation: PanelTimer {
        connected: root.connected
        activeSession: root.activeSession
        paused: root.paused
        vertical: root.vertical
        timeText: root.timeText
        stateText: root.stateText
        iconSource: root.timerIcon
        foregroundColor: root.Kirigami.Theme.textColor
        onClicked: root.expanded = !root.expanded
    }

    fullRepresentation: Loader {
        sourceComponent: root.inPanel ? controlsComponent : desktopComponent
        Layout.minimumWidth: root.inPanel ? Kirigami.Units.gridUnit * 15 : item ? item.minimumWidth : 32
        Layout.minimumHeight: root.inPanel ? implicitHeight : item ? item.minimumHeight : 32
        Layout.preferredWidth: root.inPanel ? Kirigami.Units.gridUnit * 19 : 264
        Layout.preferredHeight: root.inPanel ? implicitHeight : 176
    }

    Component {
        id: desktopComponent
        DesktopTimer {
            id: desktopFace
            connected: root.connected
            activeSession: root.activeSession
            paused: root.paused
            timeText: root.timeText
            stateText: root.stateText
            taskName: root.status.task_name || ""
            projectName: root.status.project_name || ""
            iconSource: root.timerIcon
            foregroundColor: root.Kirigami.Theme.textColor
            surfaceColor: root.Kirigami.Theme.backgroundColor
            onClicked: desktopMenu.popup(desktopFace, width / 2, height / 2)
        }
    }

    QQC2.Menu {
        id: desktopMenu
        width: Kirigami.Units.gridUnit * 20
        QQC2.MenuItem { text: root.stateText; enabled: false }
        QQC2.MenuItem {
            visible: !bridge.available
            text: i18n("Open PomoCLI Desktop from your application launcher to connect.")
            enabled: false
            contentItem: Text {
                text: parent.text
                color: Kirigami.Theme.textColor
                wrapMode: Text.Wrap
            }
        }
        QQC2.MenuItem {
            visible: bridge.lastError.length > 0
            text: bridge.lastError
            enabled: false
            contentItem: Text {
                text: parent.text
                textFormat: Text.PlainText
                color: Kirigami.Theme.negativeTextColor
                wrapMode: Text.Wrap
            }
        }
        QQC2.MenuItem {
            visible: bridge.lastError.length > 0
            text: i18n("Dismiss error")
            onTriggered: bridge.clearError()
        }
        QQC2.MenuSeparator {}
        QQC2.MenuItem {
            text: i18n("Quick Start…")
            enabled: bridge.available && !bridge.busy && !root.activeSession
            onTriggered: root.runAction("quick-start")
        }
        QQC2.MenuItem {
            text: i18n("Log Distraction")
            enabled: root.running && !bridge.busy && root.status.feedback !== true
            onTriggered: root.runAction("distract")
        }
        QQC2.MenuItem {
            text: root.paused ? i18n("Resume") : i18n("Pause")
            enabled: root.activeSession && !bridge.busy
            onTriggered: root.runAction(root.paused ? "resume" : "pause")
        }
        QQC2.MenuItem {
            text: i18n("Stop and Save")
            enabled: root.activeSession && !bridge.busy
            onTriggered: root.runAction("stop")
        }
        QQC2.MenuItem {
            visible: root.activeSession && root.elapsed
            text: i18n("Complete Session")
            enabled: root.activeSession && !bridge.busy
            onTriggered: root.runAction("complete")
        }
        QQC2.MenuSeparator {}
        QQC2.MenuItem {
            text: i18n("Quit Companion")
            enabled: bridge.available && !bridge.busy
            onTriggered: bridge.quit()
        }
    }

    Component {
        id: controlsComponent
        ColumnLayout {
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
}
