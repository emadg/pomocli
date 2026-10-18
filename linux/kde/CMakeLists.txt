set(POMO_PLASMOID_ID org.pomocli.timer)
set(POMO_PLASMOID_DIR "${CMAKE_INSTALL_DATADIR}/plasma/plasmoids/${POMO_PLASMOID_ID}")

# Keeping the plugin beside its qmldir makes both system and per-user installs
# work without changing Plasma's global QML import paths.
add_library(pomoclidesktopplugin MODULE
    src/desktopbridge.cpp
    src/desktopbridge.h
    src/plugin.cpp
)
target_link_libraries(pomoclidesktopplugin PRIVATE Qt6::Core Qt6::DBus Qt6::Qml)
target_compile_options(pomoclidesktopplugin PRIVATE -Wall -Wextra -Wpedantic)
set_target_properties(pomoclidesktopplugin PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/package/contents/ui/bridge"
)

file(COPY package/ DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/package")
set(POMO_STATUS_ICON "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/pomocli-status-icon.svg")
configure_file("${POMO_STATUS_ICON}"
    "${CMAKE_CURRENT_BINARY_DIR}/package/contents/images/pomocli-status-icon.svg" COPYONLY)
# Render the same paths directly in either foreground contrast. This also works
# when Plasma's style palette differs from the desktop/application palette.
file(READ "${POMO_STATUS_ICON}" POMO_STATUS_SVG)
string(REPLACE "fill=\"currentColor\"" "fill=\"#eff0f1\"" POMO_LIGHT_STATUS_SVG "${POMO_STATUS_SVG}")
set(POMO_LIGHT_STATUS_ICON "${CMAKE_CURRENT_BINARY_DIR}/package/contents/images/pomocli-status-icon-light.svg")
file(WRITE "${POMO_LIGHT_STATUS_ICON}" "${POMO_LIGHT_STATUS_SVG}")
# Canvas uses the SVG's intrinsic dimensions. Bound its decoded image size
# instead of retaining the full 981x833 source bitmap for a small glyph.
set(POMO_CANVAS_STATUS_ICONS)
foreach(contrast IN ITEMS dark light)
    if(contrast STREQUAL "light")
        set(POMO_CANVAS_STATUS_SVG "${POMO_LIGHT_STATUS_SVG}")
    else()
        set(POMO_CANVAS_STATUS_SVG "${POMO_STATUS_SVG}")
    endif()
    string(REGEX REPLACE "width=\"[0-9]+\" height=\"[0-9]+\"" "width=\"256\" height=\"217\""
        POMO_CANVAS_STATUS_SVG "${POMO_CANVAS_STATUS_SVG}")
    set(POMO_CANVAS_STATUS_ICON "${CMAKE_CURRENT_BINARY_DIR}/package/contents/images/pomocli-status-icon-${contrast}-canvas.svg")
    file(WRITE "${POMO_CANVAS_STATUS_ICON}" "${POMO_CANVAS_STATUS_SVG}")
    list(APPEND POMO_CANVAS_STATUS_ICONS "${POMO_CANVAS_STATUS_ICON}")
endforeach()
install(DIRECTORY package/ DESTINATION "${POMO_PLASMOID_DIR}")
install(FILES "${POMO_STATUS_ICON}" "${POMO_LIGHT_STATUS_ICON}" ${POMO_CANVAS_STATUS_ICONS}
    DESTINATION "${POMO_PLASMOID_DIR}/contents/images")
# The widget manager reads KPlugin.Icon, independently of the panel's QML.
# Give the widget its own icon so widget-only installs never depend on the
# desktop companion's launcher icon or an older cached image under that name.
install(FILES "${POMO_STATUS_ICON}"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/icons/hicolor/scalable/apps"
    RENAME "${POMO_PLASMOID_ID}.svg")
install(TARGETS pomoclidesktopplugin
    LIBRARY DESTINATION "${POMO_PLASMOID_DIR}/contents/ui/bridge"
)

if(POMO_BUILD_TESTS)
    find_package(Qt6 6.4 REQUIRED COMPONENTS Test Quick)
    add_executable(test_desktopbridge
        tests/test_desktopbridge.cpp
        src/desktopbridge.cpp
        src/desktopbridge.h
    )
    target_include_directories(test_desktopbridge PRIVATE src)
    target_link_libraries(test_desktopbridge PRIVATE Qt6::Core Qt6::DBus Qt6::Qml Qt6::Test)
    target_compile_definitions(test_desktopbridge PRIVATE
        POMO_TEST_QML_DIRECTORY="${CMAKE_CURRENT_BINARY_DIR}/package/contents/ui/"
    )
    add_dependencies(test_desktopbridge pomoclidesktopplugin)
    find_program(DBUS_RUN_SESSION dbus-run-session REQUIRED)
    add_test(NAME desktopbridge COMMAND "${DBUS_RUN_SESSION}" -- $<TARGET_FILE:test_desktopbridge>)

    add_executable(test_timer_views tests/test_timer_views.cpp)
    target_link_libraries(test_timer_views PRIVATE Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick Qt6::Test)
    target_compile_definitions(test_timer_views PRIVATE
        POMO_TEST_QML_DIRECTORY="${CMAKE_CURRENT_BINARY_DIR}/package/contents/ui/"
    )
    add_dependencies(test_timer_views pomoclidesktopplugin)
    add_test(NAME timer_views COMMAND "${DBUS_RUN_SESSION}" -- $<TARGET_FILE:test_timer_views>)
    set_tests_properties(timer_views PROPERTIES ENVIRONMENT
        "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/test-cache")
endif()
