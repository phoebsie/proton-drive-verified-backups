# Third-party notices and dependency scope

The scripts, tests, example data/configuration, systemd examples and documentation in this repository are Phoebie Agent project material under [LICENSE](LICENSE), including the DR plumbing extracted from Phoebie Agent's own production implementation. The package contains no vendored third-party source, copied upstream application implementation, third-party binaries or runtime distributions. No third-party copyright or licence notice was removed from copied material.

The project invokes separately installed tools or uses published interfaces. Their licences are not replaced by this project's MIT grant. Obtain those tools from their official sources and retain their accompanying licences/notices if you separately redistribute them. The references below acknowledge the upstream projects and describe the dependency boundary; they do not claim endorsement.

| External project | Role here | Upstream licence/reference |
| --- | --- | --- |
| Proton Drive CLI / SDK | Official CLI invoked as a separate process; no CLI or SDK code bundled | [SDK MIT licence](https://github.com/ProtonDriveApps/sdk/blob/main/LICENSE.md), [CLI documentation](https://github.com/ProtonDriveApps/sdk/blob/main/cli/README.md). Hosted-service access remains subject to Proton's service terms, independently of source-code licensing. |
| Hermes Agent, Nous Research | Optional supported native backup command; no Hermes implementation copied | [MIT licence, copyright 2025 Nous Research](https://github.com/NousResearch/hermes-agent/blob/main/LICENSE) |
| Hindsight, Vectorize AI, Inc. | Optional document-transfer API client; no Hindsight implementation or memory-policy code copied | [MIT licence, copyright 2025 Vectorize AI, Inc.](https://github.com/vectorize-io/hindsight/blob/main/LICENSE) |
| Python | Interpreter and standard-library imports; no interpreter/library source distributed | [Python licensing](https://docs.python.org/3/license.html), including PSF License Version 2 and component notices |
| SQLite | Used through Python's sqlite3 binding; no SQLite source/binary distributed | [Public-domain dedication](https://sqlite.org/copyright.html) |
| Zstandard | External `zstd` command; no library/CLI code distributed | [BSD licence](https://github.com/facebook/zstd/blob/dev/LICENSE) or [GPLv2](https://github.com/facebook/zstd/blob/dev/COPYING), per [upstream's dual-licence statement](https://github.com/facebook/zstd/blob/dev/README.md) |
| GnuPG | External agent/preset commands; no GnuPG implementation copied | [Upstream licence policy](https://gnupg.org/faq/HACKING.html): GPLv3+ with component-specific terms |
| pass / Password Store | External credential store; no pass implementation copied | [GPLv2 or later and upstream copyright notice](https://git.zx2c4.com/password-store/plain/COPYING) |
| systemd | Host scheduler runs project-authored unit examples; no systemd implementation copied | [Upstream licensing overview](https://github.com/systemd/systemd/blob/main/README), primarily LGPL-2.1-or-later with component-specific terms |

The generic capture/export/transport helpers implement command and API contracts; they are not source extracts from these upstream applications. If a future change bundles upstream source, binaries or documentation extracts, review the exact component's licence and preserve all required notices before distributing it. Do not assume this MIT licence grants rights to a new third-party addition.
