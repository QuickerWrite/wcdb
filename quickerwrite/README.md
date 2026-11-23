# QuickerWrite Android builds

This branch is based on Tencent WCDB v2.1.15. Android links against OpenSSL 3.5.9 built for the target ABI. The upstream Java API, SQLCipher revision and database settings are preserved. The release includes WCDB, dependency license notices and a build manifest inside each AAR.

A maintainer publishes by pushing a new `qw-*` tag on this branch. GitHub builds the three native architectures once and exports single-ABI and universal AARs with SHA-256 digests. A reviewed app update pins those digests before consuming the new library.
