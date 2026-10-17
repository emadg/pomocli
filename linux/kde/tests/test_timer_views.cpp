#include <QDir>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QScopedPointer>
#include <QSignalSpy>
#include <QtTest>

class TimerViewsTest final : public QObject
{
    Q_OBJECT

    QQuickItem *create(const QString &file, const QVariantMap &properties = {})
    {
        QQmlComponent component(&m_engine,
            QUrl::fromLocalFile(QStringLiteral(POMO_TEST_QML_DIRECTORY) + file));
        QVariantMap initial = properties;
        if (!initial.contains("foregroundColor"))
            initial.insert("foregroundColor", QColor("#232629"));
        if (file == "DesktopTimer.qml" && !initial.contains("surfaceColor"))
            initial.insert("surfaceColor", QColor("#f4f4f4"));
        QObject *object = component.createWithInitialProperties(initial);
        if (!object)
            qWarning().noquote() << component.errorString();
        return qobject_cast<QQuickItem *>(object);
    }

    void display(QQuickWindow &window, QQuickItem *item, const QSize &size)
    {
        window.resize(size);
        window.setColor(QColor("#f4f4f4"));
        item->setParentItem(window.contentItem());
        item->setSize(size);
        window.show();
        QTest::qWait(60);
    }

    void capture(QQuickWindow &window, const QString &name)
    {
        const QString directory = qEnvironmentVariable("POMO_WIDGET_PREVIEW_DIR");
        if (directory.isEmpty())
            return;
        QVERIFY(QDir().mkpath(directory));
        const QImage image = window.grabWindow();
        QVERIFY(!image.isNull());
        QVERIFY(image.save(directory + u'/' + name + QStringLiteral(".png")));
    }

    void fits(QQuickItem *root, const char *name)
    {
        auto *item = root->findChild<QQuickItem *>(QString::fromLatin1(name));
        QVERIFY(item);
        if (!item->isVisible())
            return;
        const QRectF bounds = item->mapRectToItem(root, item->boundingRect());
        QVERIFY2(QRectF(-1, -1, root->width() + 2, root->height() + 2).contains(bounds),
            qPrintable(QStringLiteral("%1 outside %2x%3: %4,%5 %6x%7")
                .arg(QString::fromLatin1(name)).arg(root->width()).arg(root->height())
                .arg(bounds.x()).arg(bounds.y()).arg(bounds.width()).arg(bounds.height())));
    }

private slots:
    void mainComponentCompiles()
    {
        QQmlComponent component(&m_engine,
            QUrl::fromLocalFile(QStringLiteral(POMO_TEST_QML_DIRECTORY) + QStringLiteral("main.qml")));
        QVERIFY2(component.isReady(), qPrintable(component.errorString()));
    }

    void desktopSizes_data()
    {
        QTest::addColumn<QSize>("size");
        QTest::addColumn<bool>("active");
        QTest::addColumn<bool>("connected");
        QTest::addColumn<bool>("timer");
        QTest::addColumn<bool>("title");
        QTest::addColumn<bool>("caption");
        QTest::addColumn<bool>("task");
        QTest::addColumn<bool>("project");
        QTest::newRow("idle-tiny") << QSize(40, 40) << false << true << false << false << false << false << false;
        QTest::newRow("idle-medium") << QSize(180, 96) << false << true << false << true << false << false << false;
        QTest::newRow("idle-large") << QSize(300, 220) << false << true << false << true << true << false << false;
        QTest::newRow("idle-huge") << QSize(600, 400) << false << true << false << true << true << false << false;
        QTest::newRow("disconnected") << QSize(300, 220) << false << false << false << true << true << false << false;
        QTest::newRow("active-tiny") << QSize(56, 56) << true << true << false << false << false << false << false;
        QTest::newRow("active-short") << QSize(300, 44) << true << true << false << false << false << false << false;
        QTest::newRow("active-narrow") << QSize(48, 240) << true << true << false << false << false << false << false;
        QTest::newRow("active-small") << QSize(150, 85) << true << true << true << false << false << false << false;
        QTest::newRow("active-medium") << QSize(260, 180) << true << true << true << false << false << true << false;
        QTest::newRow("active-large") << QSize(320, 240) << true << true << true << false << false << true << true;
        QTest::newRow("active-huge") << QSize(600, 400) << true << true << true << false << false << true << true;
    }

    void desktopSizes()
    {
        QFETCH(QSize, size);
        QFETCH(bool, active);
        QFETCH(bool, connected);
        QFETCH(bool, timer);
        QFETCH(bool, title);
        QFETCH(bool, caption);
        QFETCH(bool, task);
        QFETCH(bool, project);
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("DesktopTimer.qml"), {
            {"connected", connected}, {"activeSession", active}, {"timeText", "24:58"},
            {"stateText", active ? "Focus session" : "Ready to focus"},
            {"taskName", "Implement a very long task name that needs to be elided on small widgets"},
            {"projectName", "A project with a similarly long name that must fit inside the widget"},
        }));
        QVERIFY(item);
        display(window, item.data(), size);
        QCOMPARE(item->property("showTimer").toBool(), timer);
        QCOMPARE(item->property("showTitle").toBool(), title);
        QCOMPARE(item->property("showCaption").toBool(), caption);
        QCOMPARE(item->property("showTask").toBool(), task);
        QCOMPARE(item->property("showProject").toBool(), project);
        QVERIFY(item->property("idleIconSize").toReal() <= 96);
        QVERIFY(item->property("timerFontSize").toReal() <= 72);
        for (const char *name : {"idleGlyph", "pomoTitle", "readyCaption", "sessionTimer", "taskLabel", "projectLabel"})
            fits(item.data(), name);
        auto *slash = item->findChild<QQuickItem *>(QStringLiteral("disconnectSlash"));
        QVERIFY(slash);
        QCOMPARE(slash->isVisible(), !connected);
        if (caption && connected)
            QVERIFY(item->findChild<QObject *>(QStringLiteral("readyCaption"))->property("text").toString().contains(QStringLiteral("🍅👀")));
        capture(window, QString::fromLatin1(QTest::currentDataTag()));
    }

    void panelIdleAndSession()
    {
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("PanelTimer.qml"), {{"connected", true}}));
        QVERIFY(item);
        display(window, item.data(), QSize(40, 40));
        QVERIFY(item->findChild<QQuickItem *>(QStringLiteral("idleGlyph"))->isVisible());
        QVERIFY(!item->findChild<QQuickItem *>(QStringLiteral("horizontalTimer"))->isVisible());
        QVERIFY(item->property("idleExtent").toReal() > 16);
        capture(window, QStringLiteral("panel-idle"));
        item->setProperty("connected", false);
        QTest::qWait(30);
        QVERIFY(item->findChild<QQuickItem *>(QStringLiteral("disconnectSlash"))->isVisible());
        capture(window, QStringLiteral("panel-disconnected"));
        item->setProperty("connected", true);
        item->setProperty("activeSession", true);
        item->setProperty("timeText", "24:59");
        QTest::qWait(30);
        item->setWidth(item->implicitWidth());
        window.resize(qCeil(item->width()), 40);
        QTest::qWait(30);
        const qreal width = item->implicitWidth();
        fits(item.data(), "horizontalTimer");
        item->setProperty("timeText", "24:58");
        item->setProperty("paused", true);
        QTest::qWait(30);
        QCOMPARE(item->implicitWidth(), width);
        capture(window, QStringLiteral("panel-paused"));
        item->setProperty("timeText", "123:45:59");
        QTest::qWait(30);
        QVERIFY(item->implicitWidth() > width);
        item->setWidth(item->implicitWidth());
        window.resize(qCeil(item->width()), 40);
        QTest::qWait(30);
        fits(item.data(), "horizontalTimer");
        capture(window, QStringLiteral("panel-long-stopwatch"));
        item->setProperty("vertical", true);
        item->setSize(QSizeF(48, item->implicitHeight()));
        window.resize(48, qCeil(item->height()));
        QTest::qWait(30);
        fits(item.data(), "verticalTimer");
        capture(window, QStringLiteral("panel-vertical"));
    }

    void keyboardActivation()
    {
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("DesktopTimer.qml"), {{"connected", true}}));
        QVERIFY(item);
        display(window, item.data(), QSize(40, 40));
        QSignalSpy clicked(item.data(), SIGNAL(clicked()));
        item->forceActiveFocus();
        QTest::keyClick(&window, Qt::Key_Space);
        QCOMPARE(clicked.count(), 1);
    }

    void narrowVerticalPanel_data()
    {
        QTest::addColumn<int>("width");
        QTest::addColumn<bool>("showTimer");
        QTest::newRow("24px-icon-only") << 24 << false;
        QTest::newRow("32px-icon-only") << 32 << false;
        QTest::newRow("48px-hour-timer") << 48 << true;
    }

    void narrowVerticalPanel()
    {
        QFETCH(int, width);
        QFETCH(bool, showTimer);
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("PanelTimer.qml"), {
            {"connected", true}, {"activeSession", true}, {"vertical", true}, {"timeText", "1:00:00"},
        }));
        QVERIFY(item);
        display(window, item.data(), QSize(width, 48));
        QCOMPARE(item->findChild<QQuickItem *>(QStringLiteral("verticalTimer"))->isVisible(), showTimer);
        fits(item.data(), showTimer ? "verticalTimer" : "idleGlyph");
        capture(window, QString::fromLatin1(QTest::currentDataTag()));
    }

    void timerFitsLongStopwatch()
    {
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("DesktopTimer.qml"), {
            {"connected", true}, {"activeSession", true}, {"paused", true},
            {"timeText", "123:45:59"}, {"stateText", "A very long translated session state"},
            {"projectName", "PomoCLI"}, {"taskName", "Stopwatch session"},
        }));
        QVERIFY(item);
        display(window, item.data(), QSize(160, 200));
        fits(item.data(), "sessionTimer");
        fits(item.data(), "taskLabel");
        fits(item.data(), "projectLabel");
        capture(window, QStringLiteral("desktop-long-stopwatch"));
    }

    void lightAndDark()
    {
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("DesktopTimer.qml"), {{"connected", true}}));
        QVERIFY(item);
        display(window, item.data(), QSize(300, 220));
        for (bool dark : {false, true}) {
            const QColor foreground(dark ? "#eff0f1" : "#232629");
            const QColor background(dark ? "#232629" : "#f4f4f4");
            item->setProperty("foregroundColor", foreground);
            item->setProperty("surfaceColor", background);
            window.setColor(background);
            QTest::qWait(60);
            auto *glyph = item->findChild<QQuickItem *>(QStringLiteral("idleGlyph"));
            QVERIFY(glyph);
            const QRect bounds = glyph->mapRectToItem(item.data(), glyph->boundingRect()).toAlignedRect();
            const QImage image = window.grabWindow();
            int inkPixels = 0;
            for (int y = bounds.top(); y <= bounds.bottom(); ++y)
                for (int x = bounds.left(); x <= bounds.right(); ++x) {
                    const QColor pixel = image.pixelColor(x, y);
                    if (qAbs(pixel.red() - foreground.red()) < 10 && qAbs(pixel.green() - foreground.green()) < 10)
                        ++inkPixels;
                }
            QVERIFY2(inkPixels > 1000, qPrintable(QStringLiteral("Invisible SVG: source=%1, local=%2, original=%3, color=%4, pixels=%5")
                .arg(glyph->property("source").toString(), glyph->property("statusIcon").toString())
                .arg(glyph->property("showStatusIcon").toBool())
                .arg(glyph->property("color").value<QColor>().name()).arg(inkPixels)));
            capture(window, dark ? QStringLiteral("desktop-dark") : QStringLiteral("desktop-light"));
        }
    }

private:
    QQmlEngine m_engine;
};

QTEST_MAIN(TimerViewsTest)
#include "test_timer_views.moc"
