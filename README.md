# Proton Drive disaster recovery reference

A working Python reference for daily application-state capture to Proton Drive, independent remote listing verification, bounded retention, a separate 48-hour dead-man, and manually triggered restore validation. Derived from an operating personal-agent DR implementation. All included application data is generated from scratch and fictional.

This candidate is prepared privately for review. Publication and licensing require Owner approval. It is not an official Proton product, a complete machine backup or a live failover controller.

## Run the complete offline example

Linux, Python 3.12+ and `zstd` are required. No Python packages, accounts, network calls or privileged installation are needed:

```sh
python3 -m unittest discover -s tests -v
scripts/make-demo-config .demo
scripts/dr --config "$PWD/.demo/config.json" preflight
scripts/dr --config "$PWD/.demo/config.json" run
python3 - <<'PY'
import json, pathlib, subprocess
config = pathlib.Path('.demo/config.json').resolve()
settings = json.loads(config.read_text())
status = json.loads((pathlib.Path(settings['root']) / 'status.json').read_text())
name = next(iter(status['verified']))
subprocess.run(['scripts/dr', '--config', str(config), 'verify', name], check=True)
PY
```

The fake CLI stores objects under `.demo/remote` and never contacts Proton. The five captures include invented SQLite records, stand-in native Hermes and Hindsight ZIPs, and an invalid stand-in signing-material file. These are not backups of live applications.

For your own Proton account, follow [SETUP.md](SETUP.md): pin/login, pass/GPG, real adapters, notification commissioning and systemd installation. [ADAPTERS.md](ADAPTERS.md) specifies the executable capture interface. [RESTORE.md](RESTORE.md) explains validation and application recovery. [SECURITY.md](SECURITY.md) describes the threat boundary.

## Executed workflow

1. Lock against overlapping generations and compare the installed CLI with your recorded SHA-256.
2. Run every registered capture command without a shell. Require exactly the configured regular files and validate SQLite/JSON/ZIP content.
3. Record the complete participant set and member sizes/hashes in `manifest.json`.
4. Stream tar through zstd. Validate archive membership/hashes and participant contracts before upload; the reference also extracts an isolated copy for payload checks.
5. Upload using fixed argv templates. Run a **separate** `filesystem list --json`; require exactly one matching object with the expected size. Missing/wrong size or ambiguous names fail closed.
6. Atomically record verification time, size and archive digest. Upload exit zero alone never advances freshness.
7. Only then retain up to five newest generations, two additional weekly points and two additional monthly points, at most nine distinct verified generations. Only this controller's receipts in its configured destination are eligible. Trash expired objects; never empty account trash.
8. Remove temporary local work after ordinary success or failure.

A separate systemd monitor runs every 30 minutes. It alerts after more than 48 hours without verification, two consecutive failures, invalid status/time, or retention failure. No recorded backup alerts immediately. Healthy checks produce only their JSON result. A persistent condition repeats at most once per 24 hours; failed delivery is not acknowledged. The check does not depend on the agent process or Proton credential store.

Listing proves presence and size, **not remote-content integrity**. `verify` separately downloads the exact named object, compares a trusted archive hash when available, validates member hashes/exact participants and runs SQLite/ZIP checks. Trigger it manually after commissioning, changes and periodically; no restore timer is installed.

## Package

- `dr/`: reusable transport, manifests, archive streaming, retention, captures, receipts and monitor.
- `scripts/`: executable CLI, real capture helpers, synthetic fixtures and optional GPG preset.
- `examples/`: invented configuration; `systemd/`: daily/boot/monitor units; `tests/`: offline fault tests.
- [Phoebie Agent case study](CASE_STUDY.md): supporting production topology and evidence.
- [Differences from production](DIFFERENCES.md): retained code, simplifications and omissions.

No production operator access, deployment logic, proprietary perception, personalisation, memory-quality or cross-domain orchestration implementation is included. The Hindsight adapter is a generic export API client only.
