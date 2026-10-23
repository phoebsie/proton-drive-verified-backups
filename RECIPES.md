# Recipes: backing up different kinds of apps

Every app you back up is a **participant** in your config file. The tool runs your command with a private empty directory, replaces the standalone token `{output_dir}` with its path, and then requires that the command produced **exactly** the files you listed in `files`, each passing its type check (`file`, `sqlite`, `zip` or `json`). A non-zero exit, a missing or extra file, or a failed check aborts the whole backup before anything is uploaded.

Participants run in the order you list them. Put databases before the file folders they describe. A database captured first never refers to a file the later folder copy lacks, whereas the reverse order can leave records pointing at files that are missing.

Commands run with a minimal environment (`PATH=/usr/bin:/bin`). Use absolute paths, or add variables under `capture_env` in the config. Output from the command is discarded, so test it by hand first.

## What has been tested

The patterns below were run end to end against the offline fake CLI in this repository: capture, archive, upload, separate size check, then `verify`. They used **stand-in data and a stand-in dump command**. The real `pg_dump`, `mysqldump` and `docker` lines are shown for convenience and were not run. Test your own before relying on them.

## 1. A SQLite app (Vaultwarden, many small web apps)

Uses the included helper, which takes a consistent online snapshot even while the app is writing.

```json
{
  "id": "vaultwarden",
  "argv": ["/opt/dr-reference/scripts/sqlite-capture",
           "--source", "/srv/vaultwarden/data/db.sqlite3", "{output_dir}"],
  "files": {"state.sqlite3": "sqlite"},
  "timeout_s": 600
}
```

Back up the rest of that app's data directory (attachments, keys) as a folder, as in recipe 2.

## 2. A folder of files (scans, configs, a game world)

`{output_dir}` must be a standalone argument, so pass it to a small shell command as `$1`:

```json
{
  "id": "paperless-files",
  "argv": ["/bin/bash", "-c",
           "set -euo pipefail; tar -czf \"$1/scans.tar.gz\" -C /srv/paperless/media .",
           "capture", "{output_dir}"],
  "files": {"scans.tar.gz": "file"},
  "timeout_s": 3600
}
```

For a running service that writes many files at once (a game server, for example), stop it or use its own save-and-flush command first. A `tar` of files that are changing can be internally inconsistent.

## 3. A database dump (Postgres, MySQL)

```json
{
  "id": "paperless-db",
  "argv": ["/bin/bash", "-c",
           "set -euo pipefail; /usr/bin/docker exec paperless-db pg_dump -U paperless paperless | gzip > \"$1/db.sql.gz\"",
           "capture", "{output_dir}"],
  "files": {"db.sql.gz": "file"},
  "timeout_s": 1800
}
```

Notes:
- Do not add `-t` to `docker exec`. It allocates a terminal and can corrupt piped output.
- The tool checks that the file exists and is non-empty, not that the SQL is valid. Check a restored dump into a scratch database from time to time.
- For several databases, use `pg_dumpall`, or one participant per database.

## The pipefail trap (read this one)

In a shell pipeline such as `pg_dump | gzip > file`, the exit status is that of the **last** command. If `pg_dump` fails halfway, `gzip` still finishes cleanly and the shell reports success.

This was tested: with a dump command that printed part of a dump and then failed, **without** `set -o pipefail` the truncated file was accepted, uploaded, size-checked and recorded as a verified backup. With `set -euo pipefail` at the start of the command, the capture failed, nothing was uploaded and the previous backup stayed in place. Always include it, which is why `/bin/bash` (not `/bin/sh`) is used above.

## Putting it together: a household paperwork server

A complete `participants` list for three apps (SQLite password manager, Postgres-backed document manager and its scans) is simply recipes 1, 3 and 2, in that order, in one config file:

```json
"participants": [
  { ...vaultwarden, recipe 1... },
  { ...paperless-db, recipe 3... },
  { ...paperless-files, recipe 2... }
]
```

This exact shape, with a stand-in dump command, was run end to end: the archive contained all three participants plus `manifest.json`, and `verify` passed. Then the failure case above was run to confirm that a broken dump stops the whole backup.

## What not to put here

- **Large media (photo or video libraries).** Every run builds and uploads one full archive, limited to 20 GiB expanded. Use a deduplicating tool such as restic or Borg for bulk data.
- **Secrets you do not want in Proton.** Archives are encrypted by Proton at rest, but the local archive is compressed plaintext. See [SECURITY.md](SECURITY.md).
- **Anything with no way to take a consistent copy.** If you cannot dump it or snapshot it, a backup of it may not restore.
