# Executable participant contract

A **participant** is one application (or one part of a system) that you want backed up. Names are free labels of your choosing. Each participant declares a unique ID, fixed argv, timeout, contract label and exact output allowlist. `{output_dir}` must be a standalone token. The runner creates an empty private directory and replaces that token with its absolute path. Return zero only after a supported consistent capture is complete. Missing/extra files, links/special files, malformed SQLite/JSON/ZIP, unresolved ZIP WAL sidecars or a nonzero exit abort the entire generation.

Adapters and configuration are administrator-trusted code, not sandboxed inputs. No credentials belong in argv/config. Use protected files or an already commissioned service identity inside an adapter. Stdout/stderr are suppressed. Sequential captures do not provide a transactionally consistent cross-service instant.

## SQLite

Prefer the application's own backup routine where it has one (the author's finance and fitness apps each expose one). `scripts/sqlite-capture` demonstrates SQLite's online backup API and integrity validation, including committed WAL data:

```json
{
  "id": "my-app",
  "contract": "sqlite-online-backup-v1",
  "argv": ["/opt/dr-reference/scripts/sqlite-capture", "--source", "/srv/example-app/state.sqlite3", "{output_dir}"],
  "files": {"state.sqlite3": "sqlite"},
  "timeout_s": 1800
}
```

Paths are fictional. Integrity checks prove structure, not business correctness or completeness of external files/media.

## Hermes (optional)

Only relevant if you run [Hermes Agent](https://github.com/NousResearch/hermes-agent), an open-source AI agent. `scripts/hermes-capture --binary /your/absolute/hermes --home /your/hermes/home OUTPUT_DIR` runs full `hermes backup --output .../native-full.zip --keep 0`, never `--quick`, and checks the ZIP. Use the application's correct identity and compatible native CLI version, through a reviewed identity-switch wrapper if required. No identity-switch credentials are distributed.

This simple installed-Hermes adapter does **not** reproduce production's isolated-container wrapper, foreign-mount census, non-`.db` WAL repair, browser-profile pre-exclusion, backup-credential stripping, operator adjunct or split-host capture receipt. It rejects sidecars and obvious host credential/browser paths instead of repairing/stripping them. Review the native artifact and version-specific secret contract before use. Native exports may include sensitive application config/provider material. The sample ZIP contains only invented JSON.

## Hindsight (optional)

Only relevant if you run [Hindsight](https://github.com/vectorize-io/hindsight), an open-source memory service for AI agents. `scripts/hindsight-capture --api http://127.0.0.1:YOUR_PORT --bank YOUR_BANK OUTPUT_DIR` submits document-transfer export including observations/knowledge base, polls its operation, restricts the download endpoint and checks `bank-export.zip`. Use `files: {"bank-export.zip":"zip"}`.

This is the production 0.10.x API shape, tested with synthetic responses; live service/version compatibility is not claimed. Only administrator-chosen unauthenticated loopback HTTP is supported. No public-network/bearer-token adapter, import/recall or memory-quality/policy code is included. Execute it on the bank-owning host or supply a separately secured bridge. The small adapter holds the complete export in memory; large banks need a reviewed streaming extension.

## Authentication services and other recovery files

In the author's setup one participant is a login (authentication) service, which needs recovery files beyond its database. There is no generic “copy /etc” adapter. Write a small reviewed command that snapshots the database through its supported primitive and copies only approved stable recovery files. Declare every file; never `cp` a changing SQLite database. Keep signing/session/storage material within the auth participant's exact reviewed allowlist. The sample `auth/signing-material.txt` is an invalid literal stand-in, not a key or broad auth-tree exemption.

GPG/pass stores, Proton sessions, SSH identities and browser sessions stay outside the payload. Path exclusion is a guard against known mistakes, not a content-secrecy proof. Privately review actual exported content against your secret contract.

## Multiple hosts

In the author's production setup, captures from the agent host are streamed to a second host using restricted private transport. That operator/control-plane implementation is intentionally absent. A third party can supply a reviewed SSH bridge with fixed commands, dedicated restricted identity, pinned host checking and bounded streams/receipts. Do not interpolate untrusted shell input, disable host checking or stream a whole host filesystem. Until implemented and tested, the reference supports local command captures only.
