# Proton Drive Verified Backups

*An MIT-licensed Phoebie Agent reference implementation.*

> **Unofficial project.** This is independent software. It is not made, endorsed, sponsored or supported by Proton AG, and uses only Proton's publicly available Drive CLI as a separate, separately installed tool. "Proton" and "Proton Drive" are trademarks of Proton AG, used here only to name the service this works with.

An executable reference for daily application-state backups to Proton Drive: capture every participant, validate locally, upload, independently confirm the remote object, then advance freshness and prune. It includes systemd scheduling, a separate 48-hour dead-man and manually triggered restore validation.

**Phoebie Agent** is a persistent personal-agent ecosystem. Hermes runs the agent, Hindsight holds durable semantic memory, and Finance, Fitness and an auth service own specialist state. Reinstalling software restores code; it does not recover the agent's accumulated memory, durable workflows or domain records. Those need consistent, recoverable state backups, with credentials deliberately recommissioned where required.

This reference extracts the reusable DR plumbing from that running ecosystem. It includes working scripts and entirely fictional sample data, with the production-specific boundaries documented in [DIFFERENCES.md](DIFFERENCES.md). It is not an official Proton product, a complete machine backup or a live failover controller.

## From agent state to an off-provider backup

```text
Home: Hermes + Hindsight
          | supported captures through restricted private transport
          v
VPS: Finance + Fitness + auth + DR controller
          | one daily generation; upload, then separate size listing
          v
Proton Drive: encrypted off-provider storage

VPS systemd: daily generation + independent half-hour monitor
```

Proton Drive CLI supplies the storage transport, independently of the VPS provider. Reviewed source/deployment configuration rebuilds services; the off-provider generation preserves mutable state. The production capture registry has five mandatory participants:

| Participant | Recoverable state |
| --- | --- |
| Finance | Supported consistent database backup |
| Fitness | Supported domain-state backup |
| Hermes | Native full agent-state backup |
| Hindsight | Supported provider-neutral bank export, including observations and knowledge base |
| Auth service | Narrowly allowlisted database, password hashes and recovery/signing material |

The standalone runner accepts local capture commands. The production private multi-host bridge, operator control plane, container capture guards and application activation are deliberately omitted. [ADAPTERS.md](ADAPTERS.md) explains the real SQLite, simple native Hermes and Hindsight export helpers and their limits; the default demo uses synthetic captures instead.

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

## Production evidence and boundaries

Recorded production results include independent off-provider round trips and manually triggered restore checks. The October 21, 2026 rehearsal recovered gated text-only Hermes/Hindsight on the surviving VPS, including native import, memory recall and domain reads, while Finance, Fitness and auth stayed available. The dead-man has caught multiple real failures.

A full clean-host rebuild remains unproven. October 22 activation work was tested with simulation and negative gates; **live Discord cutover was not tested**, and failback remains design-only. Voice/GPU/browser capability is outside the proven emergency target. The reference's offline tests are separate evidence from these historical production results. Read the [case study](CASE_STUDY.md) for the precise claims and caveats.

## Headless authentication and CLI feedback

The sample uses the official CLI's pass-backed credential store. An optional root-only unlock file presets GPG at boot and before daily backup, with a 48-hour cache window. This enables unattended operation but lets compromised root recover the Proton session. Local archives are compressed plaintext. The monitor survives agent failure but shares the controller host; detecting complete host loss needs an external monitor. Review [SECURITY.md](SECURITY.md) and commission your own account using [SETUP.md](SETUP.md).

Two improvements would make this workflow easier to maintain:

- A **stable, documented JSON schema** for listing and errors. `list --json` already exists; scripts need predictable names, sizes and failure representations across versions.
- **Structured upload metadata** with node ID, stored size and hash, including a documented hash algorithm/meaning and machine-readable errors. This would improve evidence and diagnostics; an independent remote read remains valuable.

Scoped headless token/service-account authentication would also avoid the local GPG-unlock compromise if supported. It is a requested alternative, not an implemented capability.

## Package

- `dr/`: reusable transport, manifests, archive streaming, retention, captures, receipts and monitor.
- `scripts/`: executable CLI, real capture helpers, synthetic fixtures and optional GPG preset.
- `examples/`: invented configuration; `systemd/`: daily/boot/monitor units; `tests/`: offline fault tests.
- [Phoebie Agent case study](CASE_STUDY.md): supporting production topology and evidence.
- [Differences from production](DIFFERENCES.md): retained code, simplifications and omissions.

No production operator access, deployment logic, proprietary perception, personalisation, memory-quality or cross-domain orchestration implementation is included. The Hindsight adapter is a generic export API client only.

## Licence and acknowledgements

Copyright (c) 2026 Phoebie Agent contributors. Distributed under the [MIT licence](LICENSE). External tools are installed separately and retain their own terms; see [third-party notices and dependency scope](THIRD_PARTY_NOTICES.md). No upstream applications or binaries are bundled.
