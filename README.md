# Proton Drive Verified Backups

*An MIT-licensed Phoebie Agent reference implementation.*

> **Unofficial project.** This is independent software. It is not made, endorsed, sponsored or supported by Proton AG, and uses only Proton's publicly available Drive CLI as a separate, separately installed tool. "Proton" and "Proton Drive" are trademarks of Proton AG, used here only to name the service this works with.

Daily, **verified** backups of your self-hosted applications to Proton Drive, using Proton's official command-line tool. A backup only counts once the uploaded file has been listed back from Proton with the right size, and a separate monitor alerts you if no verified backup has happened for 48 hours.

It is a set of plain Python scripts (standard library only) plus systemd timers. You tell it which applications to back up in a config file; it handles the archive, the upload, the checks, retention, alerting and restore validation.

## What you get

- **Upload that is checked, not trusted.** The CLI's exit code never counts as success. A separate `filesystem list --json` must show exactly one matching object with the expected size.
- **All-or-nothing generations.** Every application you register is captured, hashed into a manifest and validated locally before anything is uploaded. One failed capture means no upload and no freshness update.
- **Bounded retention.** Keeps up to five daily, two weekly and two monthly generations (at most nine), moves expired ones to trash, and only after the new backup is verified. It never empties your Proton trash.
- **An independent dead-man alert.** A separate systemd timer checks every 30 minutes, does not depend on your applications, and sends an HTTPS notification (ntfy-compatible) if there is no verified backup for 48 hours, after repeated failures, or if its own status file is unreadable.
- **Restore validation.** `verify` downloads a named backup, checks every file's hash and size against the manifest, and runs SQLite and ZIP integrity checks.
- **Safe process handling.** The CLI is run without a shell, with credentials never in arguments, and the CLI binary is checked against a recorded SHA-256 before each operation.

## Who it's for

Anyone running a home server, NAS or VPS who wants encrypted off-site copies in Proton Drive, and wants proof that they exist and can be restored. You do not need any of the applications mentioned below. The example setup happens to back up a self-hosted AI agent, which is why those adapters exist, but the scheduler, verification, retention and alerting work for any application that can write its state to files.

## Try it offline in five minutes

Linux, Python 3.12+ (tested on 3.13 and 3.14) and `zstd` are required. No Python packages, accounts, network calls or privileged installation are needed:

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

A fake CLI stores objects under `.demo/remote` and never contacts Proton. The demo registers five stand-in applications named `finance`, `fitness`, `hermes`, `hindsight` and `auth`. These are only labels taken from the author's own setup; you can name yours anything. The data is invented, and none of it is a backup of a real application.

## Back up your own applications

Each application you want backed up is a **participant** in your config file: a name, a command that writes its state into a directory the runner provides, and an allowlist of the files that command may produce (each marked as `file`, `sqlite`, `zip` or `json`). The runner rejects missing or unexpected files and malformed SQLite or ZIP content, and every participant is mandatory.

Capture helpers included:

| Helper | Backs up | Notes |
| --- | --- | --- |
| `scripts/sqlite-capture` | Any SQLite database | Uses SQLite's online backup API, includes committed WAL data, checks integrity. Works for most self-hosted apps. |
| `scripts/hermes-capture` | [Hermes Agent](https://github.com/NousResearch/hermes-agent) (open-source AI agent) | Runs its native full `hermes backup`. A simple adapter; see [ADAPTERS.md](ADAPTERS.md) for limits. |
| `scripts/hindsight-capture` | A [Hindsight](https://github.com/vectorize-io/hindsight) memory bank (open-source agent memory) | Calls its export API on loopback. Tested against synthetic responses only. |
| Your own command | Anything else | Any executable that writes the allowed files and exits 0 only when the capture is complete. |

The Hermes and Hindsight helpers are optional. Ignore them if you do not run those tools. [ADAPTERS.md](ADAPTERS.md) specifies the capture interface in full.

## How a backup runs

1. Lock against overlapping runs and compare the installed CLI with your recorded SHA-256.
2. Run every participant's capture command without a shell. Require exactly the configured regular files and validate SQLite, JSON and ZIP content.
3. Record all participants, with member sizes and hashes, in `manifest.json`.
4. Stream tar through zstd. Validate archive membership and hashes before upload, and extract an isolated copy for payload checks.
5. Upload using fixed argument templates. Run a **separate** `filesystem list --json`; require exactly one matching object with the expected size. Missing, wrong-sized or ambiguous results fail closed.
6. Atomically record the verification time, size and archive digest. An upload exit code of zero alone never advances freshness.
7. Only then apply retention, using only this controller's own receipts in its configured destination.
8. Remove temporary local work after success or failure.

The monitor alerts after more than 48 hours without verification, two consecutive failures, an invalid status or time, or a retention failure. If no backup has ever been recorded it alerts immediately. Healthy checks produce only their JSON result. A persistent condition repeats at most once per 24 hours, and failed delivery is not treated as acknowledged.

Listing proves presence and size, **not remote-content integrity**. `verify` separately downloads the exact named object, compares a trusted archive hash when you provide one, validates member hashes and runs SQLite and ZIP checks. Run it after setup, after changes and periodically. No restore timer is installed.

For your own Proton account, follow [SETUP.md](SETUP.md): install and pin the CLI, set up the credential store, register your applications, configure notifications and enable the systemd units. [RESTORE.md](RESTORE.md) explains validation and recovery. [SECURITY.md](SECURITY.md) describes the threat boundary.

## Worked example: how the author uses it

This package was extracted from the disaster-recovery pipeline of **Phoebie Agent**, a personal AI-agent setup running across a home server and a VPS. In that deployment the registered participants are:

| Participant | What it is | How it is captured |
| --- | --- | --- |
| `hermes` | The AI agent runtime (Hermes Agent): its configuration, sessions and learned state | Native full backup |
| `hindsight` | The agent's long-term memory (Hindsight) | Memory-bank export |
| `finance` | The author's personal finance app | The app's own consistent SQLite backup |
| `fitness` | The author's fitness-coaching app | The app's own SQLite backup |
| `auth` | The login service in front of those apps | Narrow allowlist: database and recovery material |

Finance, Fitness and the auth service are the author's own applications and are not included here. They stand in for "your other applications". The production multi-host bridge, operator control plane, container capture guards and application activation are deliberately omitted. The [case study](CASE_STUDY.md) describes this deployment in detail, and [DIFFERENCES.md](DIFFERENCES.md) lists what changed when it was extracted.

## Evidence and boundaries

In the author's production use: the independent dead-man alert has caught multiple real failures, off-provider round trips and restore checks have been run manually, and a gated, text-only recovery of the agent and its memory onto a surviving host was rehearsed on 21 October 2026.

Not proven: a full clean-host rebuild, live failover and failback, and voice, GPU or browser capability after recovery. The standalone scripts in this repository have not been run against a live Proton account or live applications; their offline tests are separate evidence from the production results above. The [case study](CASE_STUDY.md) has the precise claims and caveats.

## Headless authentication and CLI feedback

The sample uses the official CLI's pass-backed credential store. An optional root-only unlock file presets GPG at boot and before the daily backup, with a 48-hour cache window. This enables unattended operation but lets a compromised root recover the Proton session. Local archives are compressed plaintext. The monitor survives application failure but shares the controller host; detecting complete host loss needs an external monitor. Review [SECURITY.md](SECURITY.md) before relying on this.

Two improvements to the Proton CLI would make workflows like this easier to maintain:

- A **stable, documented JSON schema** for listing and errors. `list --json` already exists; scripts need predictable names, sizes and failure representations across versions.
- **Structured upload metadata** with node ID, stored size and hash, including what the hash covers, plus machine-readable errors. An independent remote read would still be valuable.

Scoped headless token or service-account authentication would also avoid the local GPG-unlock compromise if supported. This is a requested alternative, not an implemented capability.

## What's in the repository

- `dr/`: the transport, manifests, archive streaming, retention, captures, receipts and monitor.
- `scripts/`: the command-line tool, capture helpers, synthetic demo fixtures and the optional GPG preset.
- `examples/`: invented configuration. `systemd/`: daily, boot and monitor units. `tests/`: offline fault tests.
- [CASE_STUDY.md](CASE_STUDY.md): the author's deployment as a worked example. [DIFFERENCES.md](DIFFERENCES.md): changes from the author's production code.

No production operator access, deployment logic or application-specific intelligence from the author's system is included. The Hindsight helper is a generic export API client only.

## Licence and acknowledgements

Copyright (c) 2026 Phoebie Agent contributors. Distributed under the [MIT licence](LICENSE). External tools are installed separately and retain their own terms; see [third-party notices and dependency scope](THIRD_PARTY_NOTICES.md). No upstream applications or binaries are bundled.
