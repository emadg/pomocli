// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PomoCLITimer",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "PomoCLITimer",
            path: "Sources/PomoCLITimer",
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("Carbon"),
            ]
        )
    ]
)
