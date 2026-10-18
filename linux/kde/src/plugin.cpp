#include "desktopbridge.h"

#include <QQmlExtensionPlugin>
#include <qqml.h>

class PomoCLIDesktopPlugin final : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)

public:
    void registerTypes(const char *uri) override
    {
        qmlRegisterType<DesktopBridge>(uri, 1, 0, "DesktopBridge");
    }
};

#include "plugin.moc"
