#include "desktopbridge.h"

#include <QDBusConnection>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QScopedPointer>
#include <QSignalSpy>
#include <QtTest>

class FakeCompanion final : public QObject
{
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.pomocli.Desktop1")
    Q_PROPERTY(QString Snapshot READ snapshot)

public:
    QString snapshot() const { return m_snapshot; }
    QString lastAction;
    bool quitCalled = false;
    QString result = QStringLiteral(R"({"status":"ok"})");

    void publish(const QString &value)
    {
        m_snapshot = value;
        emit SnapshotChanged(value);
    }

public slots:
    QString Action(const QString &name)
    {
        lastAction = name;
        return result;
    }
    void Quit() { quitCalled = true; }

signals:
    void SnapshotChanged(const QString &snapshot);

private:
    QString m_snapshot = QStringLiteral(R"({"connected":true,"state":"running","time_left":65,"timer_mode":"countdown"})");
};

class DesktopBridgeTest final : public QObject
{
    Q_OBJECT

private slots:
    void init()
    {
        m_companion = new FakeCompanion;
        auto bus = QDBusConnection::sessionBus();
        QVERIFY(bus.isConnected());
        QVERIFY(bus.registerObject(QStringLiteral("/org/pomocli/Desktop"), m_companion,
            QDBusConnection::ExportAllSlots | QDBusConnection::ExportAllSignals | QDBusConnection::ExportAllProperties));
        QVERIFY(bus.registerService(QStringLiteral("org.pomocli.Desktop")));
    }

    void cleanup()
    {
        auto bus = QDBusConnection::sessionBus();
        bus.unregisterService(QStringLiteral("org.pomocli.Desktop"));
        bus.unregisterObject(QStringLiteral("/org/pomocli/Desktop"));
        delete m_companion;
        m_companion = nullptr;
    }

    void initialSnapshotAndSignals()
    {
        DesktopBridge bridge;
        QTRY_VERIFY(bridge.available());
        QCOMPARE(bridge.snapshot().value(QStringLiteral("time_left")).toInt(), 65);
        m_companion->publish(QStringLiteral(R"({"connected":true,"state":"paused","time_left":60,"timer_mode":"countdown"})"));
        QTRY_COMPARE(bridge.snapshot().value(QStringLiteral("state")).toString(), QStringLiteral("paused"));
        QCOMPARE(bridge.snapshot().value(QStringLiteral("time_left")).toInt(), 60);
    }

    void bundledQmlPluginLoads()
    {
        QQmlEngine engine;
        QQmlComponent component(&engine);
        component.setData("import \"bridge\" as Backend\nBackend.DesktopBridge {}\n",
            QUrl::fromLocalFile(QStringLiteral(POMO_TEST_QML_DIRECTORY) + QStringLiteral("BridgeTest.qml")));
        QTRY_VERIFY(component.status() != QQmlComponent::Loading);
        QVERIFY2(!component.isError(), qPrintable(component.errorString()));
        QScopedPointer<QObject> object(component.create());
        QVERIFY2(object, qPrintable(component.errorString()));
        QTRY_VERIFY(object->property("available").toBool());
    }

    void actionsAndErrors()
    {
        DesktopBridge bridge;
        QTRY_VERIFY(bridge.available());
        QSignalSpy finished(&bridge, &DesktopBridge::actionFinished);
        bridge.action(QStringLiteral("pause"));
        QTRY_COMPARE(finished.count(), 1);
        QCOMPARE(m_companion->lastAction, QStringLiteral("pause"));
        QCOMPARE(finished.at(0).at(1).toBool(), true);
        QVERIFY(!bridge.busy());

        m_companion->result = QStringLiteral(R"({"status":"error","message":"Session changed"})");
        bridge.action(QStringLiteral("stop"));
        QTRY_COMPARE(finished.count(), 2);
        QCOMPARE(bridge.lastError(), QStringLiteral("Session changed"));
        QCOMPARE(finished.at(1).at(1).toBool(), false);
        bridge.clearError();
        QVERIFY(bridge.lastError().isEmpty());

        bridge.action(QStringLiteral("not-an-action"));
        QCOMPARE(finished.count(), 3);
        QCOMPARE(m_companion->lastAction, QStringLiteral("stop"));
    }

    void malformedSnapshotAndRecovery()
    {
        DesktopBridge bridge;
        QTRY_VERIFY(bridge.available());
        m_companion->publish(QStringLiteral("not json"));
        QTRY_VERIFY(!bridge.lastError().isEmpty());
        QVERIFY(!bridge.snapshot().value(QStringLiteral("connected")).toBool());
        m_companion->publish(QStringLiteral(R"({"connected":true,"state":"idle"})"));
        QTRY_COMPARE(bridge.snapshot().value(QStringLiteral("state")).toString(), QStringLiteral("idle"));
        bridge.clearError();
        QVERIFY(bridge.lastError().isEmpty());
    }

    void ownerLossAndReconnect()
    {
        DesktopBridge bridge;
        QTRY_VERIFY(bridge.available());
        auto bus = QDBusConnection::sessionBus();
        QVERIFY(bus.unregisterService(QStringLiteral("org.pomocli.Desktop")));
        QTRY_VERIFY(!bridge.available());
        QVERIFY(!bridge.snapshot().value(QStringLiteral("connected")).toBool());
        QVERIFY(bus.registerService(QStringLiteral("org.pomocli.Desktop")));
        QTRY_VERIFY(bridge.available());
        QCOMPARE(bridge.snapshot().value(QStringLiteral("time_left")).toInt(), 65);
        bridge.quit();
        QTRY_VERIFY(m_companion->quitCalled);
    }

private:
    FakeCompanion *m_companion = nullptr;
};

QTEST_GUILESS_MAIN(DesktopBridgeTest)
#include "test_desktopbridge.moc"
