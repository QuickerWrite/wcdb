# QuickerWrite Android builds

The maintenance branch retains its original name, `qw-2.1.15`. It includes Tencent’s 2.1.16 sources and subsequent fixes on master. Android links against OpenSSL 3.5.9 built for the target ABI. Each AAR builds the upstream main and compat Java classes and the JNI library from the same commit. The build checks that the SQLCipher and Zstandard archives match the submodule revisions and preserves the upstream database settings. The release includes WCDB, dependency license notices and a build manifest inside each AAR.

A maintainer publishes by pushing a new `qw-*` tag on this branch. GitHub builds the three native architectures once and exports single-ABI and universal AARs with SHA-256 digests. Each mobile build resolves the latest published release and verifies the selected asset and its source commit.
