#!/usr/bin/env python3
"""Private-bus tray/notification host for smoke tests; never a real desktop service.

Run ONLY inside dbus-run-session. Requires the distro python3-dbus/python3-gi.
"""
import json
import os
import select
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
if not os.environ.get("POMOCLI_TEST_DESKTOP"):
    sys.exit("Set POMOCLI_TEST_DESKTOP=1 and run on a private D-Bus session")


class Watcher(dbus.service.Object):
    def __init__(self):
        self.name = dbus.service.BusName("org.kde.StatusNotifierWatcher", bus)
        super().__init__(bus, "/StatusNotifierWatcher")
        self.items = []

    @dbus.service.method("org.kde.StatusNotifierWatcher", in_signature="s", sender_keyword="sender")
    def RegisterStatusNotifierItem(self, service, sender=None):
        item = str(sender) + str(service) if str(service).startswith("/") else str(service) + "/StatusNotifierItem"
        self.items.append(item)
        self.StatusNotifierItemRegistered(item)

    @dbus.service.method("org.kde.StatusNotifierWatcher", in_signature="s")
    def RegisterStatusNotifierHost(self, service):
        pass

    @dbus.service.signal("org.kde.StatusNotifierWatcher", signature="s")
    def StatusNotifierItemRegistered(self, service):
        pass

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, name):
        return self.GetAll(interface)[name]

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return {"RegisteredStatusNotifierItems": dbus.Array(self.items, signature="s"),
                "IsStatusNotifierHostRegistered": dbus.Boolean(True), "ProtocolVersion": dbus.Int32(0)}


class Notifications(dbus.service.Object):
    def __init__(self):
        self.name = dbus.service.BusName("org.freedesktop.Notifications", bus)
        super().__init__(bus, "/org/freedesktop/Notifications")
        self.count = 0

    @dbus.service.method("org.freedesktop.Notifications", out_signature="as")
    def GetCapabilities(self):
        return ["body", "actions", "sound"]

    @dbus.service.method("org.freedesktop.Notifications", in_signature="susssasa{sv}i", out_signature="u")
    def Notify(self, app, replace, icon, summary, body, actions, hints, timeout):
        self.count += 1
        print(json.dumps({"notification": self.count, "summary": str(summary), "body": str(body), "sound": str(hints.get("sound-name", ""))}), flush=True)
        return dbus.UInt32(self.count)

    @dbus.service.method("org.freedesktop.Notifications", in_signature="u")
    def CloseNotification(self, notification_id):
        pass

    @dbus.service.method("org.freedesktop.Notifications", out_signature="ssss")
    def GetServerInformation(self):
        return ("PomoCLI isolated test host", "PomoCLI", "1", "1.2")


class Request(dbus.service.Object):
    def __init__(self, path, values):
        super().__init__(bus, path)
        GLib.idle_add(self.respond, values)

    def respond(self, values):
        self.Response(dbus.UInt32(0), values)
        return False

    @dbus.service.signal("org.freedesktop.portal.Request", signature="ua{sv}")
    def Response(self, code, values):
        pass


class Portal(dbus.service.Object):
    def __init__(self):
        self.name = dbus.service.BusName("org.freedesktop.portal.Desktop", bus)
        super().__init__(bus, "/org/freedesktop/portal/desktop")
        self.requests = []
        self.session = "/org/freedesktop/portal/desktop/session/pomo_test_" + str(os.getpid())
        self.registered = set()
        self.bindings = []

    def request(self, sender, token, values):
        path = "/org/freedesktop/portal/desktop/request/" + str(sender).lstrip(":").replace(".", "_") + "/" + str(token)
        self.requests.append(Request(path, values))
        return dbus.ObjectPath(path)

    @dbus.service.method("org.freedesktop.host.portal.Registry", in_signature="sa{sv}", sender_keyword="sender")
    def Register(self, app_id, options, sender=None):
        if app_id != "org.pomocli.Desktop" or sender in self.registered:
            raise dbus.exceptions.DBusException("Invalid or duplicate application registration", name="org.freedesktop.portal.Error.NotAllowed")
        self.registered.add(sender)

    @dbus.service.method("org.freedesktop.portal.GlobalShortcuts", in_signature="a{sv}", out_signature="o", sender_keyword="sender")
    def CreateSession(self, options, sender=None):
        if sender not in self.registered:
            raise dbus.exceptions.DBusException("Register before portal calls", name="org.freedesktop.portal.Error.NotAllowed")
        return self.request(sender, options["handle_token"], {"session_handle": dbus.String(self.session)})

    @dbus.service.method("org.freedesktop.portal.GlobalShortcuts", in_signature="oa(sa{sv})sa{sv}", out_signature="o", sender_keyword="sender")
    def BindShortcuts(self, session, bindings, parent, options, sender=None):
        self.bindings = [str(binding[0]) for binding in bindings]
        return self.request(sender, options["handle_token"], {"shortcuts": bindings})

    @dbus.service.signal("org.freedesktop.portal.GlobalShortcuts", signature="osta{sv}")
    def Activated(self, session, shortcut, timestamp, options):
        pass

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, name):
        return dbus.UInt32(2)

    @dbus.service.method("org.pomocli.TestPortal", out_signature="as")
    def Bindings(self):
        return self.bindings

    @dbus.service.method("org.pomocli.TestPortal", out_signature="u")
    def Pid(self):
        return os.getpid()


class ScreenSaver(dbus.service.Object):
    def __init__(self):
        self.name = dbus.service.BusName("org.freedesktop.ScreenSaver", bus)
        super().__init__(bus, "/ScreenSaver")
        self.active = False

    @dbus.service.method("org.freedesktop.ScreenSaver", out_signature="b")
    def GetActive(self):
        return self.active

    @dbus.service.signal("org.freedesktop.ScreenSaver", signature="b")
    def ActiveChanged(self, active):
        pass


class Login(dbus.service.Object):
    def __init__(self):
        self.name = dbus.service.BusName("org.freedesktop.login1", bus)
        super().__init__(bus, "/org/freedesktop/login1")
        self.pipes = []
        self.active = bool(os.environ.get("POMOCLI_TEST_PREPARING_SLEEP"))

    @dbus.service.method("org.freedesktop.login1.Manager", in_signature="ssss", out_signature="h")
    def Inhibit(self, what, who, why, mode):
        print(json.dumps({"inhibit": str(what), "preparing_for_sleep": self.active}), flush=True)
        read, write = os.pipe()
        exported = dbus.types.UnixFd(read)
        os.close(read)  # UnixFd duplicates it; retain no server-side reader.
        self.pipes.append(write)
        return exported

    def open_inhibitors(self):
        count = 0
        for write in self.pipes:
            poll = select.poll()
            poll.register(write, select.POLLERR)
            if not poll.poll(0):
                count += 1
        return count

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, name):
        print(json.dumps({"property": str(name), "preparing_for_sleep": self.active}), flush=True)
        return dbus.Boolean(self.active)

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return {"PreparingForSleep": dbus.Boolean(self.active)}

    @dbus.service.signal("org.freedesktop.login1.Manager", signature="b")
    def PrepareForSleep(self, active):
        pass


class Controller(dbus.service.Object):
    def __init__(self, portal, screen, login):
        self.name = dbus.service.BusName("org.pomocli.TestDesktop", bus)
        super().__init__(bus, "/org/pomocli/TestDesktop")
        self.portal, self.screen, self.login = portal, screen, login

    @dbus.service.method("org.pomocli.TestDesktop", in_signature="b")
    def Lock(self, active):
        self.screen.active = bool(active)
        self.screen.ActiveChanged(active)

    @dbus.service.method("org.pomocli.TestDesktop", in_signature="b")
    def Sleep(self, active):
        self.login.active = bool(active)
        self.login.PrepareForSleep(active)

    @dbus.service.method("org.pomocli.TestDesktop", in_signature="s")
    def Shortcut(self, name):
        self.portal.Activated(dbus.ObjectPath(self.portal.session), name, dbus.UInt64(1),
                              {"activation_token": dbus.String("pomo-private-activation")})

    @dbus.service.method("org.pomocli.TestDesktop", out_signature="as")
    def Bindings(self):
        return self.portal.bindings

    @dbus.service.method("org.pomocli.TestDesktop", out_signature="u")
    def InhibitorsOpen(self):
        return self.login.open_inhibitors()


if "--portal-only" in sys.argv:
    portal = Portal()
else:
    watcher = Watcher()
    notifications = Notifications()
    if os.environ.get("POMOCLI_TEST_INTEGRATIONS"):
        portal = None if os.environ.get("POMOCLI_TEST_NO_PORTAL") else Portal()
        screen = ScreenSaver()
        login = Login()
        controller = Controller(portal, screen, login)
print("ready", flush=True)
GLib.MainLoop().run()
