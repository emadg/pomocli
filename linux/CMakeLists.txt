cmake_minimum_required(VERSION 3.22)
project(PomoCLILinux VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)
option(POMO_BUILD_KDE_WIDGET "Build the optional Plasma 6 panel widget" ON)
option(POMO_BUILD_TESTS "Build the bridge D-Bus integration tests" OFF)

if(POMO_BUILD_TESTS)
    enable_testing()
endif()

if(POMO_BUILD_KDE_WIDGET)
    find_package(Qt6 6.4 REQUIRED COMPONENTS Core DBus Qml)
    set(CMAKE_CXX_STANDARD 17)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    set(CMAKE_AUTOMOC ON)
    add_subdirectory(kde)
endif()
