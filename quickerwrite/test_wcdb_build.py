import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('wcdb', Path(__file__).with_name('build-wcdb.py'))
wcdb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcdb)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def artifact(self, abi, classes=b'classes'):
        path = self.root / f'{abi}.aar'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('classes.jar', classes)
            z.writestr(f'jni/{abi}/libWCDB.so', b'OpenSSL 3.5.9')
            z.writestr(f'jni/{abi}/libc++_shared.so', b'runtime')
        wcdb.seal(path, [abi])
        return path

    def rewrite(self, path, update):
        with zipfile.ZipFile(path) as z:
            files = {name: z.read(name) for name in z.namelist()}
        update(files)
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in files.items():
                z.writestr(name, data)

    def test_assemble_exact_abis(self):
        for abi in wcdb.ABIS:
            self.artifact(abi)
        output = self.root / 'all.aar'
        wcdb.assemble(self.root, output, list(wcdb.ABIS))
        _, abis = wcdb.read_verified(output)
        self.assertEqual(abis, list(wcdb.ABIS))

    def test_tampering_rejected(self):
        path = self.artifact('x86_64')
        self.rewrite(path, lambda f: f.update({'classes.jar': b'changed'}))
        with self.assertRaisesRegex(RuntimeError, 'integrity'):
            wcdb.read_verified(path)

    def test_stale_provenance_rejected(self):
        path = self.artifact('x86_64')
        def stale(files):
            manifest = json.loads(files[wcdb.MANIFEST])
            manifest['provenance']['ndk'] = 'old'
            files[wcdb.MANIFEST] = json.dumps(manifest).encode()
        self.rewrite(path, stale)
        with self.assertRaisesRegex(RuntimeError, 'provenance'):
            wcdb.read_verified(path)

    def test_mixed_java_rejected(self):
        self.artifact('x86_64')
        self.artifact('arm64-v8a', b'different')
        with self.assertRaisesRegex(RuntimeError, 'Inconsistent'):
            wcdb.assemble(self.root, self.root / 'out.aar', ['x86_64', 'arm64-v8a'])

    def test_wrong_abi_rejected(self):
        self.artifact('x86_64').rename(self.root / 'arm64-v8a.aar')
        with self.assertRaisesRegex(RuntimeError, 'ABI'):
            wcdb.assemble(self.root, self.root / 'out.aar', ['arm64-v8a'])

    def test_missing_library_rejected_even_with_matching_manifest(self):
        path = self.artifact('x86_64')
        def remove(files):
            del files['jni/x86_64/libc++_shared.so']
            del files[wcdb.MANIFEST]
        self.rewrite(path, remove)
        wcdb.seal(path, ['x86_64'])
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            wcdb.read_verified(path)

    def test_old_crypto_rejected_even_with_matching_manifest(self):
        path = self.artifact('x86_64')
        def old(files):
            files['jni/x86_64/libWCDB.so'] = b'OpenSSL 1.1.1'
            del files[wcdb.MANIFEST]
        self.rewrite(path, old)
        wcdb.seal(path, ['x86_64'])
        with self.assertRaisesRegex(RuntimeError, 'OpenSSL'):
            wcdb.read_verified(path)

    def test_sdkmanager_outside_path(self):
        sdk = self.root / 'sdk with spaces'
        manager = sdk / 'cmdline-tools/latest/bin/sdkmanager'
        manager.parent.mkdir(parents=True)
        manager.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$TEST_ARGS"\n')
        manager.chmod(0o755)
        args = self.root / 'args'
        paths = self.root / 'paths'
        env = dict(os.environ, ANDROID_HOME=str(sdk), PATH='/usr/bin:/bin', TEST_ARGS=str(args), GITHUB_PATH=str(paths))
        subprocess.run(['bash', str(Path(__file__).with_name('prepare-android-native.sh'))], env=env, check=True)
        self.assertEqual(args.read_text().splitlines(), [f'--sdk_root={sdk}', 'ndk;28.2.13676358', 'cmake;3.22.1', 'platforms;android-35'])
        self.assertEqual(paths.read_text().strip(), str(sdk / 'cmake/3.22.1/bin'))


if __name__ == '__main__':
    unittest.main()
