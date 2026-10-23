# Proton Drive Verified Backups

*An MIT-licensed Phoebie Agent reference implementation.*

> **Unofficial project.** This is independent software. It is not made, endorsed, sponsored or supported by Proton AG, and uses only Proton's publicly available Drive CLI as a separate, separately installed tool. "Proton" and "Proton Drive" are trademarks of Proton AG, used here only to name the service this works with.

**Back up your self-hosted apps to Proton Drive, and know for certain that it worked.**

Most home-server backups fail quietly: the job "ran", the file never landed or was half-written, and nobody finds out until the day they need it. This tool is the last mile that closes that gap. It uploads with Proton's official command-line tool, then **lists the file back from Proton and checks its size before counting the backup as done**. A separate monitor tells you if no verified backup has happened for 48 hours. A restore check proves the data inside is intact.

It is a handful of plain Python scripts (standard library only) and systemd timers. You say which apps to back up in a config file; it does the rest.

## What problem does it solve?

The usual advice for self-hosting is: dump your databases, archive your files, push them off-site, test restores, and monitor the whole thing. Most guides stop after "push them off-site". This project does the unglamorous remaining steps:

| You already do this | This adds |
| --- | --- |
| Run a nightly script that uploads a backup | Proof the upload landed with the right size, not just that the script exited 0 |
| Back up several apps | One all-or-nothing backup, so you never restore a database from Tuesday next to files from Friday |
| Keep old copies | Retention that only deletes old backups *after* the new one is verified |
| Hope you'd notice a failure | A dead-man alert that fires if there has been no verified backup for 48 hours, independent of your apps |
| Mean to test a restore someday | One command that downloads a backup, checks every file's hash and opens the databases |

## What could I use it for?

It backs up whatever you can express as "a command that writes some files". A few realistic setups (illustrations; see [RECIPES.md](RECIPES.md) for the configs):

- **A self-hosted Hermes Agent, and its memory.** The author's own use, and the best-documented one. [Hermes Agent](https://github.com/NousResearch/hermes-agent) is backed up with its own full `hermes backup`, and a [Hindsight](https://github.com/vectorize-io/hindsight) memory bank with its export API, together as one verified backup in Proton Drive. See [HERMES.md](HERMES.md).
- **A household paperwork server.** Paperless-ngx (a database plus a folder of scanned bills and tax papers), Vaultwarden (family passwords, one SQLite file) and Home Assistant (a config folder), all captured together into one verified backup in Proton Drive, which suits your most private documents.
- **A club or volunteer organisation.** A membership database and a folder of signed waivers, run by a treasurer who changes every couple of years. The restore check is a single command the next volunteer can run without knowing the system.
- **A small game server.** A world folder and a few plugin databases, backed up nightly, with a phone alert if it stops.
- **A one-person business.** Bookkeeping or CRM databases plus an invoices folder, where "I think the backup is running" is not good enough.

## Is it a good fit?

**Good fit**
- App state from a few megabytes to a few gigabytes (databases, config, documents, scans, game worlds). The hard limit is 20 GiB per backup, expanded.
- Several apps that should be backed up as one consistent set.
- You use Proton Drive, or want an encrypted off-site copy you control.
- You want to be told when backups stop, and want a restore check you can actually run.

**Not a good fit**
- Large media libraries (photo or video archives, a NAS full of films). Every run builds and uploads one full archive. There are no incremental backups, so use a deduplicating tool such as restic or Borg for bulk data.
- File sync or continuous mirroring.
- Whole-machine or bare-metal images.
- Windows, macOS, or setups without systemd and root. It targets Linux servers.
- Automatic restore or failover. It validates a backup; it does not reinstall your apps.

It is a reference implementation: you review it, adapt the capture commands to your apps and commission it on your own host. See [Evidence and boundaries](#evidence-and-boundaries).

## Try it offline in five minutes

You need Linux, Python 3.12+ (tested on 3.13 and 3.14) and `zstd`. No Python packages, accounts, network access or root:

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

A fake CLI stores objects under `.demo/remote` and never contacts Proton. The demo backs up five stand-in apps named `finance`, `fitness`, `hermes`, `hindsight` and `auth`. Those are only labels from the author's own setup; the data is invented, and you can name yours anything.

## Back up your own apps

Each app you want backed up is a **participant** in your config file: a name, a command that writes its data into a directory the tool provides, and a list of the files that command is allowed to produce, each marked `file`, `sqlite`, `zip` or `json`. Every participant is mandatory: if one capture fails, nothing is uploaded and the freshness clock does not advance.

A participant looks like this (a SQLite-backed app, using the included helper):

```json
{
  "id": "vaultwarden",
  "argv": ["/opt/dr-reference/scripts/sqlite-capture",
           "--source", "/srv/vaultwarden/data/db.sqlite3", "{output_dir}"],
  "files": {"state.sqlite3": "sqlite"},
  "timeout_s": 600
}
```

For anything that is not SQLite, give it any command that writes the allowed files. [RECIPES.md](RECIPES.md) has patterns for a folder of files and for a database dump (such as `pg_dump`), run end to end with stand-in data, plus one trap worth knowing about: **a dump piped into `gzip` can silently produce a truncated backup that still passes every check, unless you use `set -o pipefail`.**

| Helper | Backs up | Notes |
| --- | --- | --- |
| `scripts/sqlite-capture` | Any SQLite database | Uses SQLite's online backup API, includes committed WAL data, checks integrity. |
| Your own command | Folders, `pg_dump`/`mysqldump` output, anything | See [RECIPES.md](RECIPES.md). |
| `scripts/hermes-capture` | [Hermes Agent](https://github.com/NousResearch/hermes-agent) (open-source AI agent) | Runs Hermes' own full `hermes backup` and checks the zip. See [HERMES.md](HERMES.md). |
| `scripts/hindsight-capture` | A [Hindsight](https://github.com/vectorize-io/hindsight) memory bank (open-source agent memory) | Exports through Hindsight's API. See [HERMES.md](HERMES.md). |

If you do not run Hermes or Hindsight, ignore those two helpers. [ADAPTERS.md](ADAPTERS.md) specifies the capture interface in full.

To go live with your own Proton account, follow [SETUP.md](SETUP.md): install and pin the CLI, set up the credential store, register your apps, configure notifications and enable the systemd units. Expect an hour or two if you are comfortable with Linux, GPG and systemd. [RESTORE.md](RESTORE.md) explains validation and recovery, and [SECURITY.md](SECURITY.md) describes the threat boundary.

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

## Worked example: backing up a Hermes Agent

This package grew out of the disaster-recovery pipeline for the author's own self-hosted AI agent, **Phoebie Agent**, which runs across a home server and a VPS. The full guide is [HERMES.md](HERMES.md): the config, how each helper works, how to restore, and what to watch for. In short, the backup is five participants captured together:

| Participant | What it is | How it is captured |
| --- | --- | --- |
| `hermes` | The agent runtime ([Hermes Agent](https://github.com/NousResearch/hermes-agent)): configuration, skills, sessions, scheduled jobs, state | Hermes' own full `hermes backup`, wrapped and checked by `scripts/hermes-capture` |
| `hindsight` | The agent's long-term memory ([Hindsight](https://github.com/vectorize-io/hindsight)) | Bank export through its API, via `scripts/hindsight-capture` |
| `finance` | The author's personal finance app | The app's own consistent SQLite backup |
| `fitness` | The author's fitness-coaching app | The app's own SQLite backup |
| `auth` | The login service in front of those apps | Narrow allowlist: database and recovery material |

Hermes and Hindsight are the two this repository ships helpers for. Finance, Fitness and the auth service are the author's own applications and stand in for "your other apps". The author's multi-host bridge between the home server and the VPS, operator control plane and container capture guards are not included. The [case study](CASE_STUDY.md) describes the full deployment and [DIFFERENCES.md](DIFFERENCES.md) lists what changed when it was extracted.

## Evidence and boundaries

The upload, listing, verification, retention and monitoring approach here comes from the pipeline that backs up the author's own systems to a live Proton Drive account every day. In that use the independent dead-man alert has caught multiple real failures, off-provider round trips and restore checks have been run, and a gated, text-only recovery of the agent and its memory onto a surviving host was rehearsed on 21 October 2026.

This package's own tests and demo run offline against a fake CLI, so you can try everything without an account. Not yet exercised: a full clean-host rebuild and live failover. The [case study](CASE_STUDY.md) has the precise claims and caveats.

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
- [HERMES.md](HERMES.md): backing up a Hermes Agent and its Hindsight memory, step by step.
- [RECIPES.md](RECIPES.md): tested patterns for folders and database dumps, and the `pipefail` trap.
- [CASE_STUDY.md](CASE_STUDY.md): the author's deployment as a worked example. [DIFFERENCES.md](DIFFERENCES.md): changes from the author's production code.

No production operator access, deployment logic or application-specific intelligence from the author's system is included. The Hindsight helper is a generic export API client only.

## Licence and acknowledgements

Copyright (c) 2026 Phoebie Agent contributors. Distributed under the [MIT licence](LICENSE). External tools are installed separately and retain their own terms; see [third-party notices and dependency scope](THIRD_PARTY_NOTICES.md). No upstream applications or binaries are bundled.
