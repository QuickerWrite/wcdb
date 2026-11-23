#!/usr/bin/env bash
set -euo pipefail
sdk_root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$sdk_root" ]]; then
  echo 'Android SDK root is not configured' >&2
  exit 1
fi
sdkmanager="$sdk_root/cmdline-tools/latest/bin/sdkmanager"
if [[ ! -x "$sdkmanager" ]]; then
  sdkmanager="$(command -v sdkmanager || true)"
fi
if [[ -z "$sdkmanager" || ! -x "$sdkmanager" ]]; then
  echo "Cannot find sdkmanager under $sdk_root/cmdline-tools/latest/bin or PATH" >&2
  exit 1
fi
if [[ ! -f "$sdk_root/platforms/android-35/android.jar" ||
      ! -f "$sdk_root/ndk/28.2.13676358/source.properties" ||
      ! -x "$sdk_root/cmake/3.22.1/bin/cmake" ||
      ! -x "$sdk_root/cmake/3.22.1/bin/ninja" ]]; then
  "$sdkmanager" --sdk_root="$sdk_root" 'ndk;28.2.13676358' 'cmake;3.22.1' 'platforms;android-35'
fi
# Pin CMake instead of accidentally selecting a runner's unrelated version.
if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$sdk_root/cmake/3.22.1/bin" >> "$GITHUB_PATH"
fi
