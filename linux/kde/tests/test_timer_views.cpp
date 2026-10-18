#include <QDir>
#include <QJSValue>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickItemGrabResult>
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

    QImage grabItem(QQuickItem *item)
    {
        const auto result = item->grabToImage();
        if (!result)
            return {};
        QSignalSpy ready(result.data(), &QQuickItemGrabResult::ready);
        if (result->image().isNull() && !ready.wait(2000))
            return {};
        return result->image();
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
        QTest::newRow("idle-strip") << QSize(212, 36) << false << true << false << true << false << false << false;
        QTest::newRow("idle-medium") << QSize(180, 96) << false << true << false << true << true << false << false;
        QTest::newRow("idle-large") << QSize(300, 220) << false << true << false << true << true << false << false;
        QTest::newRow("idle-huge") << QSize(600, 400) << false << true << false << true << true << false << false;
        QTest::newRow("disconnected") << QSize(300, 220) << false << false << false << true << true << false << false;
        QTest::newRow("active-tiny") << QSize(56, 56) << true << true << true << false << false << false << false;
        QTest::newRow("active-short") << QSize(300, 44) << true << true << true << false << false << false << false;
        QTest::newRow("active-narrow") << QSize(48, 240) << true << true << true << false << false << false << false;
        QTest::newRow("active-recorded-strip") << QSize(212, 36) << true << true << true << false << false << false << false;
        QTest::newRow("active-minimum") << QSize(96, 36) << true << true << true << false << false << false << false;
        QTest::newRow("active-small") << QSize(150, 85) << true << true << true << false << false << false << false;
        QTest::newRow("active-medium") << QSize(260, 180) << true << true << true << false << false << true << true;
        QTest::newRow("active-recorded-portrait") << QSize(180, 212) << true << true << true << false << false << true << true;
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
        QVERIFY(item->property("idleIconSize").toReal() <= 128);
        QVERIFY(item->property("timerFontSize").toReal() <= 112);
        for (const char *name : {"idleGlyph", "pomoTitle", "readyCaption", "sessionHeader", "sessionTimer", "taskLabel", "projectLabel"})
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
        QVERIFY(!item->findChild<QQuickItem *>(QStringLiteral("panelTimer"))->isVisible());
        QVERIFY(item->property("idleExtent").toReal() > 16);
        const qreal previousExtent = 40 - item->property("edge").toReal() * 2;
        QVERIFY(qAbs(item->property("idleExtent").toReal() / previousExtent - 0.85) < 0.001);
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
        fits(item.data(), "panelTimer");
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
        fits(item.data(), "panelTimer");
        capture(window, QStringLiteral("panel-long-stopwatch"));
        item->setProperty("vertical", true);
        item->setSize(QSizeF(48, item->implicitHeight()));
        window.resize(48, qCeil(item->height()));
        QTest::qWait(30);
        fits(item.data(), "panelTimer");
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

    void stackedPanel_data()
    {
        QTest::addColumn<int>("height");
        QTest::addColumn<QString>("time");
        QTest::addColumn<bool>("dark");
        QTest::newRow("panel-stack-24") << 24 << QStringLiteral("24:56") << false;
        QTest::newRow("panel-stack-32") << 32 << QStringLiteral("24:56") << false;
        QTest::newRow("panel-stack-40") << 40 << QStringLiteral("24:56") << false;
        QTest::newRow("panel-stack-48") << 48 << QStringLiteral("24:56") << true;
        QTest::newRow("panel-stack-hour") << 48 << QStringLiteral("1:00:00") << true;
        QTest::newRow("panel-stack-long") << 48 << QStringLiteral("123:45:59") << true;
        QTest::newRow("panel-stack-64") << 64 << QStringLiteral("24:56") << true;
    }

    void stackedPanel()
    {
        QFETCH(int, height);
        QFETCH(QString, time);
        QFETCH(bool, dark);
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("PanelTimer.qml"), {
            {"connected", true}, {"activeSession", true}, {"timeText", time},
            {"foregroundColor", QColor(dark ? "#eff0f1" : "#232629")},
        }));
        QVERIFY(item);
        display(window, item.data(), QSize(160, height));
        window.setColor(QColor(dark ? "#232629" : "#f4f4f4"));
        item->setWidth(qCeil(item->implicitWidth()));
        window.resize(qCeil(item->width()), height);
        QTest::qWait(30);
        auto *glyph = item->findChild<QQuickItem *>(QStringLiteral("sessionGlyph"));
        auto *timer = item->findChild<QQuickItem *>(QStringLiteral("panelTimer"));
        QVERIFY(glyph);
        QVERIFY(timer);
        const QRectF glyphBounds = glyph->mapRectToItem(item.data(), glyph->boundingRect());
        const QRectF timerBounds = timer->mapRectToItem(item.data(), timer->boundingRect());
        QVERIFY(glyphBounds.bottom() <= timerBounds.top() + 1);
        QVERIFY(qAbs(glyphBounds.center().x() - timerBounds.center().x()) < 1);
        fits(item.data(), "sessionGlyph");
        fits(item.data(), "panelTimer");
        QVERIFY(timer->property("contentWidth").toReal() <= timer->width() + 1);
        if (height >= 48) {
            const QJSValue fontInfo = timer->property("fontInfo").value<QJSValue>();
            QVERIFY2(fontInfo.property(QStringLiteral("pixelSize")).toNumber() >= 20,
                "Use the panel's height for a larger, readable timer");
        }
        capture(window, QString::fromLatin1(QTest::currentDataTag()));
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
        QCOMPARE(item->findChild<QQuickItem *>(QStringLiteral("panelTimer"))->isVisible(), showTimer);
        fits(item.data(), showTimer ? "panelTimer" : "idleGlyph");
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

    void resizeKeepsTimerVisible()
    {
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("DesktopTimer.qml"), {
            {"connected", true}, {"activeSession", true}, {"stateText", "Focus session"},
            {"taskName", "Task"}, {"projectName", "Project"},
        }));
        QVERIFY(item);
        auto *timer = item->findChild<QQuickItem *>(QStringLiteral("sessionTimer"));
        QVERIFY(timer);
        for (const QString &time : {QStringLiteral("24:58"), QStringLiteral("1:00:00"), QStringLiteral("123:45:59")}) {
            item->setProperty("timeText", time);
            for (const QSize &size : {QSize(240, 180), QSize(212, 36), QSize(48, 180), QSize(56, 56),
                     QSize(96, 36), QSize(132, 111), QSize(132, 112), QSize(143, 143), QSize(144, 144),
                     QSize(144, 72), QSize(143, 71), QSize(180, 212), QSize(320, 240), QSize(300, 44)}) {
                display(window, item.data(), size);
                QVERIFY(timer->isVisible());
                QCOMPARE(timer->property("text").toString(), time);
                fits(item.data(), "sessionTimer");
                QVERIFY(timer->property("contentWidth").toReal() <= timer->width() + 1);
                for (const char *name : {"sessionHeader", "taskLabel", "projectLabel"})
                    fits(item.data(), name);
            }
            const QSize minimum(qCeil(item->property("minimumWidth").toReal()),
                qCeil(item->property("minimumHeight").toReal()));
            display(window, item.data(), minimum);
            const QJSValue fontInfo = timer->property("fontInfo").value<QJSValue>();
            QVERIFY(fontInfo.property(QStringLiteral("pixelSize")).toNumber() >= 16);
            fits(item.data(), "sessionTimer");
        }
    }

    void sessionHierarchy()
    {
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("DesktopTimer.qml"), {
            {"connected", true}, {"activeSession", true}, {"stateText", "Focus session"},
            {"timeText", "24:36"}, {"taskName", "Test"}, {"projectName", "Test Project"},
        }));
        QVERIFY(item);
        display(window, item.data(), QSize(320, 280));
        const auto bounds = [&](const QString &name) {
            auto *child = item->findChild<QQuickItem *>(name);
            return child->mapRectToItem(item.data(), child->boundingRect());
        };
        const QRectF header = bounds(QStringLiteral("sessionGlyph")).united(bounds(QStringLiteral("sessionState")));
        const QRectF timer = bounds(QStringLiteral("sessionTimer"));
        const QRectF task = bounds(QStringLiteral("taskLabel"));
        const QRectF project = bounds(QStringLiteral("projectLabel"));
        QVERIFY(qAbs(header.center().x() - item->width() / 2) < 1);
        QVERIFY(header.bottom() < timer.top());
        QVERIFY(timer.bottom() < task.top());
        QVERIFY(task.bottom() < project.top());
        QVERIFY(project.top() - task.bottom() < task.top() - timer.bottom());
        auto *timerItem = item->findChild<QQuickItem *>(QStringLiteral("sessionTimer"));
        QVERIFY(timerItem->property("contentWidth").toReal() > item->width() * 0.8);
        capture(window, QStringLiteral("active-session-hierarchy"));
    }

    void transparentDisconnect_data()
    {
        QTest::addColumn<bool>("dark");
        QTest::addColumn<QColor>("background");
        QTest::newRow("disconnected-light") << false << QColor("#f4f4f4");
        QTest::newRow("disconnected-dark") << true << QColor("#232629");
        QTest::newRow("disconnected-color") << true << QColor("#377a97");
    }

    void transparentDisconnect()
    {
        QFETCH(bool, dark);
        QFETCH(QColor, background);
        QQuickWindow window;
        QScopedPointer<QQuickItem> item(create(QStringLiteral("DesktopTimer.qml"), {
            {"connected", true}, {"foregroundColor", QColor(dark ? "#eff0f1" : "#232629")},
            {"surfaceColor", background},
        }));
        QVERIFY(item);
        display(window, item.data(), QSize(300, 220));
        window.setColor(background);
        QTest::qWait(30);
        auto *glyph = item->findChild<QQuickItem *>(QStringLiteral("idleGlyph"));
        QVERIFY(glyph);
        const QImage original = grabItem(glyph);
        QVERIFY(!original.isNull());
        item->setProperty("connected", false);
        QTest::qWait(60);
        auto *stroke = glyph->findChild<QQuickItem *>(QStringLiteral("disconnectSlashStroke"));
        QVERIFY(stroke);
        const QImage image = grabItem(glyph);
        QVERIFY(!image.isNull());
        QVERIFY(image.hasAlphaChannel());
        QCOMPARE(image.size(), original.size());
        const QColor red = stroke->property("color").value<QColor>();
        QList<QPoint> erased;
        int gapAbove = 0;
        int gapBelow = 0;
        int redPixels = 0;
        int outsidePixels = 0;
        int changedOutside = 0;
        const qreal clearRadius = glyph->property("slashThickness").toReal() / 2 + glyph->property("slashGap").toReal();
        for (int y = 0; y < image.height(); ++y)
            for (int x = 0; x < image.width(); ++x) {
                const QColor pixel = image.pixelColor(x, y);
                const int originalAlpha = original.pixelColor(x, y).alpha();
                const qreal distance = qAbs(x + y + 1 - (image.width() + image.height()) / 2.0) / qSqrt(2.0);
                if (distance > clearRadius + 2) {
                    if (originalAlpha > 240 || pixel.alpha() > 240)
                        ++outsidePixels;
                    if ((originalAlpha > 240 && pixel.alpha() < 10) || (originalAlpha < 10 && pixel.alpha() > 240))
                        ++changedOutside;
                }
                if (originalAlpha > 240 && pixel.alpha() < 10) {
                    erased.append(QPoint(x, y));
                    if (x + y < (image.width() + image.height()) / 2)
                        ++gapAbove;
                    else
                        ++gapBelow;
                }
                if (pixel.alpha() > 200 && qAbs(pixel.red() - red.red()) < 5
                    && qAbs(pixel.green() - red.green()) < 5 && qAbs(pixel.blue() - red.blue()) < 5)
                    ++redPixels;
            }
        QVERIFY2(gapAbove > 50 && gapBelow > 50, "Both sides of the slash must erase the logo's alpha");
        QVERIFY2(changedOutside < outsidePixels * 0.02, "The cutout must preserve the logo's shape outside the slash");
        QVERIFY2(redPixels > 150, "Disconnected slash needs a visible red stroke");
        capture(window, QString::fromLatin1(QTest::currentDataTag()));
        const QString directory = qEnvironmentVariable("POMO_WIDGET_PREVIEW_DIR");
        if (!directory.isEmpty()) {
            QVERIFY(image.save(directory + u'/' + QString::fromLatin1(QTest::currentDataTag()) + QStringLiteral("-alpha.png")));
            QVERIFY(original.save(directory + u'/' + QString::fromLatin1(QTest::currentDataTag()) + QStringLiteral("-original-alpha.png")));
        }
        const QImage composited = window.grabWindow();
        const QPointF origin = glyph->mapToItem(item.data(), QPointF());
        const QPoint gap = erased.at(erased.size() / 2);
        const QColor through = composited.pixelColor(qRound(origin.x()) + gap.x(), qRound(origin.y()) + gap.y());
        QVERIFY(qAbs(through.red() - background.red()) < 5 && qAbs(through.green() - background.green()) < 5
            && qAbs(through.blue() - background.blue()) < 5);
        item->setProperty("connected", true);
        QTest::qWait(30);
        const QImage restored = grabItem(glyph);
        QVERIFY(!restored.isNull());
        for (const QPoint &point : erased)
            QVERIFY(restored.pixelColor(point).alpha() > 240);
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
