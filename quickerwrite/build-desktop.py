"""Package the tagged WCDB C++ shared library, import library and public headers."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["linux-x86_64", "windows-x86_64", "openharmony-arm64"])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    build = Path("out") / args.target
    options = ["-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"]
    crypto = Path("tools/prebuild/openssl")
    zlib = Path("tools/prebuild/zlib")
    if args.target == "windows-x86_64":
        deps = Path(os.environ["VCPKG_INSTALLATION_ROOT"]) / "installed/x64-windows-static-md"
        shutil.copytree(deps / "include/openssl", crypto / "include/openssl", dirs_exist_ok=True)
        shutil.copy2(deps / "lib/libcrypto.lib", crypto / "windows/win64")
        shutil.copy2(deps / "lib/zlib.lib", zlib / "windows/win64/zlibstatic.lib")
        options += ["-A", "x64", "-DCMAKE_SHARED_LINKER_FLAGS=Advapi32.lib User32.lib Bcrypt.lib"]
    elif args.target == "linux-x86_64":
        # Use the runner distribution's maintained OpenSSL 3 and zlib.
        for directory in (crypto / "include", crypto / "linux", zlib / "linux", zlib / "include"):
            shutil.rmtree(directory)
        options += ["-G", "Ninja", "-DCMAKE_C_COMPILER=clang", "-DCMAKE_CXX_COMPILER=clang++",
                    "-DCMAKE_SHARED_LINKER_FLAGS=-fuse-ld=lld"]
    else:
        sdk = Path(os.environ["OHOS_NDK_HOME"])
        prefix = Path(os.environ["QW_OHOS_OPENSSL"])
        shutil.copytree(prefix / "include/openssl", crypto / "include/openssl", dirs_exist_ok=True)
        shutil.copy2(prefix / "lib/libcrypto.a", crypto / "ohos/arm64-v8a")
        options += ["-G", "Ninja", f"-DCMAKE_TOOLCHAIN_FILE={sdk}/build/cmake/ohos.toolchain.cmake",
                    "-DOHOS_ARCH=arm64-v8a", "-DOHOS_STL=c++_shared"]
    run("cmake", "-S", "src", "-B", build, *options)
    run("cmake", "--build", build, "--config", "Release", "--parallel", "4")
    files = {"licenses/WCDB.txt": Path("LICENSE"), "licenses/Zstandard.txt": Path("zstd/LICENSE"),
             "licenses/SQLCipher.txt": Path("sqlcipher/LICENSE")}
    if args.target == "windows-x86_64":
        files.update({"lib/WCDB.dll": build / "Release/WCDB.dll", "lib/WCDB.lib": build / "Release/WCDB.lib",
                      "licenses/OpenSSL.txt": deps / "share/openssl/copyright",
                      "licenses/zlib.txt": deps / "share/zlib/copyright"})
    else:
        library = build / "libWCDB.so"
        if args.target == "linux-x86_64":
            run("strip", "--strip-unneeded", library)
            run("ldd", "-r", library)
        else:
            run(sdk / "llvm/bin/llvm-strip", "--strip-unneeded", library)
            files["licenses/OpenSSL.txt"] = prefix / "LICENSE.txt"
        files["lib/libWCDB.so"] = library
    headers = build / "export_headers"
    for header in headers.rglob("*"):
        if header.is_file():
            files["include/" + header.relative_to(headers).as_posix()] = header
    if "include/WCDB/WCDBCpp.h" not in files:
        raise RuntimeError("WCDB public headers missing")
    with zipfile.ZipFile(output / f"wcdb-{args.target}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            archive.write(path, name)
        archive.writestr("SOURCE_COMMIT", subprocess.check_output(["git", "rev-parse", "HEAD"]))


if __name__ == "__main__":
    main()
