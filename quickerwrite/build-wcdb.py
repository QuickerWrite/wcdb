#!/usr/bin/env python3
"""Rebuild WCDB's native engine with pinned, supported crypto; never use old JNI.

Build Java and JNI from the same checkout, using its pinned SQLCipher revision.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import urllib.request
import zipfile


SOURCES = {
    "sqlcipher": ("https://codeload.github.com/Tencent/sqlcipher/tar.gz/445e1dbe066ee917e4475b028f90ff37efb04541", "8eda236022885af0f9a1448abc6bab6b52a56b1792042da2d97ba412fd42d356"),
    "zstd": ("https://codeload.github.com/facebook/zstd/tar.gz/69036dffe50f385bd3b7b187e3fd230f4b2ef97e", "7311499518b955c7489c5188cb722fdeae1b14d9f8d2266d1e406473abcaef74"),
    "openssl": ("https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz", "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a"),
    "annotations": ("https://repo.maven.apache.org/maven2/org/jetbrains/annotations/13.0/annotations-13.0.jar", "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478"),
}
ABIS = {
    "arm64-v8a": ("android-arm64", "aarch64-linux-android"),
    "armeabi-v7a": ("android-arm", "arm-linux-androideabi"),
    "x86_64": ("android-x86_64", "x86_64-linux-android"),
}


def download(name, cache):
    url, digest = SOURCES[name]
    path = cache / digest
    if not path.exists():
        pending = path.with_suffix(".download")
        with urllib.request.urlopen(url, timeout=120) as src, pending.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        if hashlib.sha256(pending.read_bytes()).hexdigest() != digest:
            pending.unlink()
            raise RuntimeError(f"Source integrity check failed: {name}")
        pending.replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Source integrity check failed: {name}")
    return path


def extract(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            member.name = str(Path(*parts[1:]))
            tf.extract(member, target, filter="data")


def verify_native(data):
    if b"OpenSSL 3.5.9" not in data or re.search(rb"OpenSSL (?:0\.|1\.|3\.[0-4]\.)", data):
        raise RuntimeError("WCDB must contain only the pinned supported OpenSSL")


MANIFEST = "META-INF/qw-native-build.json"
NDK_VERSION = "28.2.13676358"


PROJECT = Path(__file__).resolve().parents[1]


def check_submodule_sources():
    for name in ("sqlcipher", "zstd"):
        revision = subprocess.check_output(
            ["git", "-C", str(PROJECT), "rev-parse", f"HEAD:{name}"], text=True
        ).strip()
        if SOURCES[name][0].rsplit("/", 1)[-1] != revision:
            raise RuntimeError(f"{name} archive does not match the checked-out submodule revision")


def build_java(main_dir, annotations, output):
    sources = sorted((main_dir / "src/main/java").rglob("*.java"))
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        classes = Path(tmp)
        subprocess.run(["javac", "--release", "8", "-encoding", "UTF-8", "-proc:none",
                        "-classpath", annotations, "-d", classes, *sources], check=True)
        with zipfile.ZipFile(output, "w") as jar:
            for path in sorted(classes.rglob("*.class")):
                entry = zipfile.ZipInfo(path.relative_to(classes).as_posix())
                jar.writestr(entry, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)


def android_manifest(main_dir):
    android = "http://schemas.android.com/apk/res/android"
    ET.register_namespace("android", android)
    manifest = ET.parse(main_dir / "src/main/AndroidManifest.xml").getroot()
    manifest.set("package", "com.tencent.wcdb.core")
    sdk = manifest.find("uses-sdk")
    if sdk is None:
        sdk = ET.SubElement(manifest, "uses-sdk")
    sdk.set(f"{{{android}}}minSdkVersion", "24")
    return ET.tostring(manifest, encoding="utf-8", xml_declaration=True)


def provenance():
    return {"commit": subprocess.check_output(["git", "-C", str(PROJECT), "rev-parse", "HEAD"], text=True).strip(),
            "script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "sources": {name: digest for name, (_, digest) in SOURCES.items()},
            "ndk": NDK_VERSION}


def read_verified(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("Duplicate AAR entries")
        manifest = json.loads(archive.read(MANIFEST))
        if manifest["provenance"] != provenance():
            raise RuntimeError("Stale WCDB source/toolchain provenance")
        files = {name: archive.read(name) for name in names if name != MANIFEST}
        if {name: hashlib.sha256(data).hexdigest() for name, data in files.items()} != manifest["files"]:
            raise RuntimeError("WCDB artifact integrity mismatch")
        abis = manifest["abis"]
        if not abis or len(abis) != len(set(abis)) or any(abi not in ABIS for abi in abis):
            raise RuntimeError("Invalid artifact ABI list")
        expected = {f"jni/{abi}/{lib}" for abi in abis for lib in ("libWCDB.so", "libc++_shared.so")}
        if {name for name in files if name.startswith("jni/")} != expected:
            raise RuntimeError("Incomplete or unexpected native libraries")
        for abi in abis:
            verify_native(files[f"jni/{abi}/libWCDB.so"])
        return files, abis


def seal(path, abis):
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as archive:
        manifest = {"provenance": provenance(), "abis": abis,
                    "files": {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}}
        archive.writestr(MANIFEST, json.dumps(manifest, sort_keys=True))


def assemble(directory, output, abis):
    common = None
    native = {}
    for abi in abis:
        files, actual = read_verified(directory / f"{abi}.aar")
        if actual != [abi]:
            raise RuntimeError("Artifact ABI does not match requested ABI")
        base = {name: data for name, data in files.items() if not name.startswith("jni/")}
        if common is not None and base != common:
            raise RuntimeError("Inconsistent WCDB Java/resources")
        common = base
        native.update({name: data for name, data in files.items() if name.startswith("jni/")})
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(".tmp")
    with zipfile.ZipFile(pending, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in {**common, **native}.items():
            archive.writestr(name, data)
    seal(pending, abis)
    pending.replace(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path)
    parser.add_argument("--prebuilt-dir", type=Path)
    parser.add_argument("--release", action="store_true", help="Also export verified single-ABI AARs alongside the universal AAR")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--abis", default=",".join(ABIS))
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 2, 6))
    args = parser.parse_args()
    abis = args.abis.split(",")
    if not abis or len(abis) != len(set(abis)) or any(abi not in ABIS for abi in abis):
        parser.error("Unsupported Android ABI")
    output = args.output.resolve()
    if args.verify:
        _, actual = read_verified(output)
        if set(actual) != set(abis):
            parser.error("Artifact ABI mismatch")
        return
    if args.prebuilt_dir:
        assemble(args.prebuilt_dir, output, abis)
        return
    if not args.ndk:
        parser.error("--ndk is required for source builds")
    if not re.search(r"Pkg.Revision\s*=\s*" + re.escape(NDK_VERSION) + r"\s*$", (args.ndk / "source.properties").read_text(), re.M):
        parser.error("Unexpected NDK revision")
    root = output.parent / "wcdb-build"
    root.mkdir(parents=True, exist_ok=True)
    cache = root / "downloads"
    cache.mkdir(exist_ok=True)
    ndk = args.ndk.resolve()
    host = "darwin-x86_64" if os.uname().sysname == "Darwin" else "linux-x86_64"
    toolchain = ndk / "toolchains/llvm/prebuilt" / host
    if not (toolchain / "bin/clang").is_file():
        parser.error("A Linux/macOS Android NDK is required")
    env = dict(os.environ, ANDROID_NDK_ROOT=str(ndk), PATH=f"{toolchain / 'bin'}:{os.environ['PATH']}")
    check_submodule_sources()
    archives = {name: download(name, cache) for name in SOURCES}
    source = PROJECT
    for name in ("sqlcipher", "zstd"):
        extract(archives[name], source / name)
    main_dir = source / "src/java/main"
    classes = root / "classes.jar"
    build_java(main_dir, archives["annotations"], classes)
    libraries = {}
    for abi in abis:
        target, triple = ABIS[abi]
        build = root / abi
        crypto = build / "crypto"
        extract(archives["openssl"], crypto)
        prefix = build / "openssl"
        log = build / "build.log"
        with log.open("w") as stream:
            def run(command, cwd=build):
                subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
            print(f"Building WCDB + OpenSSL 3.5.9: {abi} ({log})", flush=True)
            run(["perl", crypto / "Configure", target, "-D__ANDROID_API__=24", "no-shared", "no-tests", "no-apps", "no-ssl", "no-engine", "no-module", "no-dso", "-fPIC", "-fvisibility=hidden", f"--prefix={prefix}"], crypto)
            run(["make", f"-j{args.jobs}", "build_libs"], crypto)
            run(["make", "install_dev"], crypto)
            native = build / "native"
            run(["cmake", "-S", source / "src/java/main/src/main/cpp", "-B", native, "-G", "Ninja", f"-DCMAKE_TOOLCHAIN_FILE={ndk}/build/cmake/android.toolchain.cmake", f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-24", "-DANDROID_STL=c++_shared", f"-DQW_OPENSSL_ROOT={prefix}", "-DCMAKE_BUILD_TYPE=Release"])
            run(["cmake", "--build", native, f"-j{args.jobs}"])
            library = native / "wcdb/libWCDB.so"
            run([toolchain / "bin/llvm-strip", "--strip-unneeded", library])
            verify_native(library.read_bytes())
            libraries[f"jni/{abi}/libWCDB.so"] = library
            runtime = build / "libc++_shared.so"
            shutil.copyfile(toolchain / "sysroot/usr/lib" / triple / "libc++_shared.so", runtime)
            run([toolchain / "bin/llvm-strip", "--strip-unneeded", runtime])
            libraries[f"jni/{abi}/libc++_shared.so"] = runtime
    pending = output.with_suffix(".tmp")
    with zipfile.ZipFile(pending, "w", zipfile.ZIP_DEFLATED) as rebuilt:
        rebuilt.writestr("AndroidManifest.xml", android_manifest(main_dir))
        rebuilt.writestr("R.txt", "")
        rebuilt.write(classes, "classes.jar")
        rebuilt.write(main_dir / "proguard-rules.pro", "proguard.txt")
        for name, path in libraries.items():
            rebuilt.write(path, name)
        for name, license_path in {
            "WCDB": source / "LICENSE",
            "SQLCipher": source / "sqlcipher/LICENSE",
            "Zstandard": source / "zstd/LICENSE",
            "OpenSSL": crypto / "LICENSE.txt",
            "libc++": ndk / "NOTICE",
        }.items():
            rebuilt.write(license_path, f"META-INF/licenses/{name}.txt")
        version = (source / "VERSION").read_text().strip()
        rebuilt.writestr("META-INF/qw-native-build.txt", f"WCDB {version}; OpenSSL 3.5.9; Android API 24\n")
    seal(pending, abis)
    pending.replace(output)
    if args.release:
        files, included = read_verified(output)
        if set(included) != set(ABIS):
            parser.error("Release builds require all three ABIs")
        for abi in included:
            single = output.with_name(f"{abi}.aar")
            with zipfile.ZipFile(single, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    if not name.startswith("jni/") or name.startswith(f"jni/{abi}/"):
                        archive.writestr(name, data)
            seal(single, [abi])
            read_verified(single)
    print(f"Verified hardened WCDB: {output}")


if __name__ == "__main__":
    main()
