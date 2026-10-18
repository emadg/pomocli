#include "desktopbridge.h"

#include <QDBusError>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QDBusVariant>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStringList>
#include <QTimer>

namespace {
constexpr auto service = "org.pomocli.Desktop";
constexpr auto objectPath = "/org/pomocli/Desktop";
constexpr auto interfaceName = "org.pomocli.Desktop1";
constexpr int timeoutMs = 3000;
}

DesktopBridge::DesktopBridge(QObject *parent)
    : QObject(parent)
    , m_bus(QDBusConnection::sessionBus())
{
    disconnected();
    auto *watcher = new QDBusServiceWatcher(QString::fromLatin1(service), m_bus,
                                          QDBusServiceWatcher::WatchForOwnerChange, this);
    connect(watcher, &QDBusServiceWatcher::serviceOwnerChanged, this, &DesktopBridge::ownerChanged);
    const bool subscribed = m_bus.connect(QString::fromLatin1(service), QString::fromLatin1(objectPath),
                                         QString::fromLatin1(interfaceName), QStringLiteral("SnapshotChanged"),
                                         this, SLOT(receiveSnapshot(QString)));
    if (!m_bus.isConnected() || !subscribed) {
        setError(tr("Cannot connect to the desktop session bus."));
        return;
    }
    // Let QML finish constructing before publishing the first update.
    QTimer::singleShot(0, this, &DesktopBridge::refresh);
}

void DesktopBridge::setError(const QString &message)
{
    if (m_lastError == message)
        return;
    m_lastError = message;
    emit lastErrorChanged();
}

void DesktopBridge::clearError()
{
    setError(QString());
}

void DesktopBridge::setBusy(bool value)
{
    if (m_busy == value)
        return;
    m_busy = value;
    emit busyChanged();
}

void DesktopBridge::setAvailable(bool value)
{
    if (m_available == value)
        return;
    m_available = value;
    emit availableChanged();
}

void DesktopBridge::disconnected()
{
    const QVariantMap next{{QStringLiteral("connected"), false},
                           {QStringLiteral("state"), QStringLiteral("disconnected")}};
    if (m_snapshot != next) {
        m_snapshot = next;
        emit snapshotChanged();
    }
}

void DesktopBridge::ownerChanged(const QString &, const QString &, const QString &newOwner)
{
    ++m_generation;
    ++m_snapshotRevision;
    setBusy(false);
    setAvailable(false);
    disconnected();
    if (!newOwner.isEmpty())
        refresh();
}

void DesktopBridge::receiveSnapshot(const QString &snapshot)
{
    ++m_snapshotRevision;
    const QJsonDocument document = QJsonDocument::fromJson(snapshot.toUtf8());
    if (!document.isObject() || !document.object().value(QStringLiteral("connected")).isBool()
        || !document.object().value(QStringLiteral("state")).isString()) {
        disconnected();
        setError(tr("The desktop companion returned an invalid timer status."));
        return;
    }
    setAvailable(true);
    const QVariantMap next = document.object().toVariantMap();
    if (m_snapshot != next) {
        m_snapshot = next;
        emit snapshotChanged();
    }
}

void DesktopBridge::refresh()
{
    if (!m_bus.isConnected()) {
        setAvailable(false);
        disconnected();
        return;
    }
    QDBusMessage message = QDBusMessage::createMethodCall(QString::fromLatin1(service),
        QString::fromLatin1(objectPath), QStringLiteral("org.freedesktop.DBus.Properties"), QStringLiteral("Get"));
    message << QString::fromLatin1(interfaceName) << QStringLiteral("Snapshot");
    const quint64 generation = m_generation;
    const quint64 revision = m_snapshotRevision;
    auto *call = new QDBusPendingCallWatcher(m_bus.asyncCall(message, timeoutMs), this);
    connect(call, &QDBusPendingCallWatcher::finished, this, [this, generation, revision](QDBusPendingCallWatcher *watcher) {
        const QDBusPendingReply<QDBusVariant> reply = *watcher;
        watcher->deleteLater();
        // An old property reply must not replace a newer signal or a new owner.
        if (generation != m_generation || revision != m_snapshotRevision)
            return;
        if (reply.isError()) {
            setAvailable(false);
            disconnected();
            const auto type = reply.error().type();
            if (type != QDBusError::ServiceUnknown
                && reply.error().name() != QStringLiteral("org.freedesktop.DBus.Error.NameHasNoOwner"))
                setError(reply.error().message());
            return;
        }
        receiveSnapshot(reply.value().variant().toString());
    });
}

void DesktopBridge::action(const QString &name)
{
    static const QStringList actions{QStringLiteral("quick-start"), QStringLiteral("distract"),
        QStringLiteral("pause"), QStringLiteral("resume"), QStringLiteral("stop"), QStringLiteral("complete")};
    if (!actions.contains(name)) {
        setError(tr("Unknown timer action."));
        emit actionFinished(name, false);
        return;
    }
    invoke(QStringLiteral("Action"), name);
}

void DesktopBridge::quit()
{
    invoke(QStringLiteral("Quit"));
}

void DesktopBridge::invoke(const QString &method, const QString &actionName)
{
    if (m_busy)
        return;
    if (!m_available) {
        setError(tr("Start PomoCLI Desktop from your application launcher first."));
        emit actionFinished(actionName, false);
        return;
    }
    clearError();
    setBusy(true);
    auto message = QDBusMessage::createMethodCall(QString::fromLatin1(service),
        QString::fromLatin1(objectPath), QString::fromLatin1(interfaceName), method);
    if (method == QStringLiteral("Action"))
        message << actionName;
    const quint64 generation = m_generation;
    auto *call = new QDBusPendingCallWatcher(m_bus.asyncCall(message, timeoutMs), this);
    connect(call, &QDBusPendingCallWatcher::finished, this, [this, generation, actionName, method](QDBusPendingCallWatcher *watcher) {
        const QDBusMessage reply = watcher->reply();
        watcher->deleteLater();
        if (generation != m_generation)
            return;
        setBusy(false);
        bool success = reply.type() != QDBusMessage::ErrorMessage;
        if (!success) {
            setError(reply.errorMessage());
        } else if (method == QStringLiteral("Action")) {
            const QJsonDocument document = QJsonDocument::fromJson(reply.arguments().value(0).toString().toUtf8());
            const auto object = document.object();
            success = document.isObject() && object.value(QStringLiteral("status")).toString() == QStringLiteral("ok");
            if (!success)
                setError(object.value(QStringLiteral("message")).toString(tr("The timer action failed.")));
        }
        emit actionFinished(actionName, success);
        if (method != QStringLiteral("Quit"))
            refresh();
    });
}
