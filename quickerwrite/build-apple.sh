#!/usr/bin/env bash
set -euo pipefail
# Run from the tagged checkout, with its sqlcipher and zstd submodules.
platform=${1:?ios or macos}
output=${2:?output directory}
mkdir -p "$output"
temp=$(mktemp -d)
trap 'rm -rf "$temp"' EXIT
case "$platform" in
  ios) sdks=(iphoneos iphonesimulator) ;;
  macos) sdks=(macosx) ;;
  *) exit 2 ;;
esac
args=()
for sdk in "${sdks[@]}"; do
  case "$sdk" in
    iphoneos) archs=arm64 ;;
    *) archs='arm64 x86_64' ;;
  esac
  products="$temp/$sdk"
  xcodebuild -quiet -project src/WCDB.xcodeproj -scheme WCDBSwift -configuration Release -sdk "$sdk" \
    -derivedDataPath "$temp/build-$sdk" CONFIGURATION_BUILD_DIR="$products" \
    "ARCHS=$archs" ONLY_ACTIVE_ARCH=NO CODE_SIGNING_ALLOWED=NO \
    IPHONEOS_DEPLOYMENT_TARGET=15.0 MACOSX_DEPLOYMENT_TARGET=11.0 \
    BUILD_LIBRARY_FOR_DISTRIBUTION=YES ENABLE_USER_SCRIPT_SANDBOXING=NO \
    'OTHER_CPLUSPLUSFLAGS=$(inherited) -Wno-invalid-specialization' build
  framework="$products/WCDBSwift.framework"
  lipo -verify_arch $archs "$framework/WCDBSwift"
  args+=(-framework "$framework")
done
xcodebuild -create-xcframework "${args[@]}" -output "$temp/WCDBSwift.xcframework"
mkdir "$temp/licenses"
cp LICENSE "$temp/licenses/WCDB.txt"
cp sqlcipher/LICENSE "$temp/licenses/SQLCipher.txt"
cp zstd/LICENSE "$temp/licenses/Zstandard.txt"
git rev-parse HEAD > "$temp/SOURCE_COMMIT"
(cd "$temp" && /usr/bin/zip -q -r -y "$output/wcdb-$platform.zip" WCDBSwift.xcframework licenses SOURCE_COMMIT)
