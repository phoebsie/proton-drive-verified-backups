# Backing up a Hermes Agent with this package

This is the author's own use case, and the one this package was built around. [Hermes Agent](https://github.com/NousResearch/hermes-agent) is an open-source, self-hosted AI agent. Reinstalling its software restores the code; it does not restore what the agent has accumulated: configuration, skills, sessions, scheduled jobs, and learned state. That state is what you are backing up.

## What gets backed up, and how

| Piece | What it holds | How it is captured here |
| --- | --- | --- |
| **Hermes** | Configuration, skills, sessions, scheduled jobs, state databases | Hermes' own full backup command, `hermes backup`, wrapped by `scripts/hermes-capture` |
| **Hindsight** (optional) | Long-term memory, if you run the [Hindsight](https://github.com/vectorize-io/hindsight) memory service | Its document-transfer export API, via `scripts/hindsight-capture` |
| **Your other apps** (optional) | Anything else the agent depends on | Any command that writes files; see [RECIPES.md](RECIPES.md) |

The package does not reach into Hermes' files itself. It asks Hermes to produce its own supported backup, then checks, archives, uploads and verifies the result like any other participant.

## How the Hermes helper works

`scripts/hermes-capture` does four things:

1. Runs `hermes backup --output <dir>/native-full.zip --keep 0` with `HERMES_HOME` pointing at your Hermes home. It is the **full** backup, never `--quick`, which only saves a few state files. `--keep 0` stops Hermes deleting older zips on its own.
2. Runs Hermes without a shell, with a minimal environment, and discards its output.
3. Checks the result is a valid ZIP with safe paths, no links, no unresolved database sidecars (`-wal`, `-shm`, `-journal`) and a clean CRC.
4. Exits non-zero on any problem, which stops the entire backup before anything is uploaded.

The zip then goes into the same archive, manifest, upload, remote-size check, retention and monitoring as everything else.

## A config for Hermes alone

Add this participant to your config (paths are examples):

```json
{
  "id": "hermes",
  "contract": "hermes-native-full-v1",
  "argv": ["/opt/dr-reference/scripts/hermes-capture",
           "--binary", "/usr/local/bin/hermes",
           "--home", "/var/lib/hermes",
           "{output_dir}"],
  "files": {"native-full.zip": "zip"},
  "timeout_s": 1800
}
```

Run it as the same user that owns the Hermes home, because Hermes must read its own files. If Hermes runs in a container, either run the helper where `hermes` can be executed against the data directory, or write a small wrapper that runs `hermes backup` in the container and copies the zip out. The wrapper then becomes your `argv`.

## Adding Hindsight memory

```json
{
  "id": "hindsight",
  "contract": "hindsight-bank-export-v1",
  "argv": ["/opt/dr-reference/scripts/hindsight-capture",
           "--api", "http://127.0.0.1:8888", "--bank", "your-bank",
           "{output_dir}"],
  "files": {"bank-export.zip": "zip"},
  "timeout_s": 3600
}
```

The helper submits an export (including observations and knowledge base), waits for it, downloads it from loopback only and checks the zip. Use your own port and bank name. It has been exercised against synthetic responses and the 0.10.x API shape, so check it against your Hindsight version.

With both participants in one config, the agent and its memory are captured **together** as one all-or-nothing generation. You never restore memory from a different day than the agent that uses it.

## Restoring

1. Install a clean, compatible Hermes and keep it stopped, or paused so it does not talk to your channels.
2. Download and check the backup: `scripts/dr --config <config> verify <object name>`. Do this first; a failed check means do not restore from it.
3. Take `hermes/native-full.zip` from the verified archive (the package gives you the validated files; it does not restore them for you).
4. Import it with Hermes' own command: `hermes import <zip>`.
5. For Hindsight, rebuild the service and load the exported bank with its document-transfer import, then prove recall with a few known queries.
6. Re-enter credentials the backup deliberately leaves out, then switch your channels back on.

Keep exactly one live copy of the agent. If an old host comes back after you have promoted a new one, quarantine it before anything is merged.

## Things to know

- **The Hermes zip contains sensitive material**, such as configuration and provider settings. Proton encrypts it at rest, but the local archive is compressed plaintext. Read [SECURITY.md](SECURITY.md) and keep the working directory private.
- **Credentials you must rebuild.** Machine identities, SSH keys, Proton's own session and external logins are not part of the backup by design.
- **Hermes version matters.** Back up and restore with compatible versions, and record which version produced each backup.
- **WAL files.** The simple helper refuses a zip that contains unresolved database sidecars rather than repairing them.
- **How the author runs it.** The author's Hermes and Hindsight run on a home server, with the backup controller on a separate VPS that pulls captures over a restricted private link. That multi-host bridge is not included here; this package captures from the machine it runs on. See the [case study](CASE_STUDY.md).

## What has and has not been exercised

In the author's setup this approach backs up a live Hermes and Hindsight to Proton Drive daily, and a gated recovery of both onto a second host has been rehearsed. In this package, the Hermes and Hindsight helpers are covered by offline tests with stand-in data, so run them against your own installation and a throwaway Proton folder before relying on them.
