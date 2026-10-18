#pragma once

#include <QDBusConnection>
#include <QObject>
#include <QVariantMap>

class DesktopBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantMap snapshot READ snapshot NOTIFY snapshotChanged)
    Q_PROPERTY(bool available READ available NOTIFY availableChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)

public:
    explicit DesktopBridge(QObject *parent = nullptr);
    QVariantMap snapshot() const { return m_snapshot; }
    bool available() const { return m_available; }
    bool busy() const { return m_busy; }
    QString lastError() const { return m_lastError; }

    Q_INVOKABLE void action(const QString &name);
    Q_INVOKABLE void quit();
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void clearError();

signals:
    void snapshotChanged();
    void availableChanged();
    void busyChanged();
    void lastErrorChanged();
    void actionFinished(const QString &name, bool success);

private slots:
    void receiveSnapshot(const QString &snapshot);
    void ownerChanged(const QString &service, const QString &oldOwner, const QString &newOwner);

private:
    void setError(const QString &message);
    void setBusy(bool value);
    void setAvailable(bool value);
    void disconnected();
    void invoke(const QString &method, const QString &action = QString());

    QDBusConnection m_bus;
    QVariantMap m_snapshot;
    QString m_lastError;
    bool m_available = false;
    bool m_busy = false;
    quint64 m_generation = 0;
    quint64 m_snapshotRevision = 0;
};
