#!/usr/bin/env bash
set -euo pipefail
: "${OHOS_NDK_HOME:?}" "${QW_OHOS_OPENSSL:?}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
curl --retry 3 -fsSLO https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz
echo '603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a  openssl-3.5.9.tar.gz' | sha256sum -c
tar xf openssl-3.5.9.tar.gz
cd openssl-3.5.9
export PATH="$OHOS_NDK_HOME/llvm/bin:$PATH"
export CC="clang --target=aarch64-linux-ohos --sysroot=$OHOS_NDK_HOME/sysroot"
export AR=llvm-ar RANLIB=llvm-ranlib
perl Configure linux-aarch64 no-asm no-shared no-tests no-apps no-dso no-engine no-module no-ssl \
  -fPIC --prefix="$QW_OHOS_OPENSSL" --libdir=lib
make -j4 build_libs
make install_dev
cp LICENSE.txt "$QW_OHOS_OPENSSL/"
