# QuickerWrite WCDB releases

The maintenance branch retains its original name, `qw-2.1.15`. The package version comes from the tagged source. A new `qw-X.Y.Z-N` tag builds all libraries on GitHub-hosted runners and publishes one release after checking the source commit in every package.

| Target | Release asset | Contents |
| --- | --- | --- |
| Android API 24+ | `armeabi-v7a.aar`, `arm64-v8a.aar`, `x86_64.aar`, `universal.aar` | Java main and compat, JNI, libc++, OpenSSL 3.5.9 |
| iOS 15+ | `wcdb-ios.zip` | WCDBSwift XCFramework for ARM64 devices and ARM64/x86-64 simulators |
| macOS 11+ | `wcdb-macos.zip` | WCDBSwift XCFramework for Apple Silicon and Intel |
| Windows x64 | `wcdb-windows-x86_64.zip` | C++ headers, WCDB DLL and MSVC import library |
| Linux x86-64 | `wcdb-linux-x86_64.zip` | C++ headers and shared library built on Ubuntu 24.04, using system OpenSSL 3 and zlib |
| OpenHarmony ARM64 | `wcdb-openharmony-arm64.zip` | API 12 native C++ library and headers. Link with the SDK's shared libc++ runtime. |

`SHA256SUMS.txt` covers every downloadable library. Android packages include `META-INF/qw-native-build.json`. Each ZIP includes `SOURCE_COMMIT` and license notices.

Mobile release builds resolve the latest published tag once, use that same version across Android and iOS, and verify the downloaded bytes against GitHub's SHA-256. The libraries are compiled when WCDB is released.
