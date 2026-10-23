# Restore validation and recovery

`verify` downloads into private temporary work, compares a trusted archive digest if available, validates exact manifest membership/hashes/sizes and configured participants, then checks SQLite structure and ZIP CRC/path policy. It removes temporary work and records a bounded receipt. It does not advance backup freshness, import application state, start an agent or connect channels.

```sh
scripts/dr --config /your/private/config.json verify YOUR_GENERATION_OBJECT_NAME --sha256 YOUR_TRUSTED_ARCHIVE_DIGEST
```

Choose the exact canonical generation appropriate to the incident. Obtain its name/digest from separately protected receipts. After controller loss, reconstruct CLI access/config independently. Without a trusted digest, `trusted_archive_hash_matched: false` explicitly limits the result to internal consistency.

Use reviewed config/runtime versions corresponding to the generation. An old archive fails against a different required participant/file set. Preserve versioned config and application deployment provenance outside mutable state. The manifest's provenance fields are placeholders; automatic runtime discovery/version selection is not implemented.

For actual recovery, first fence old writers and hold channels/schedulers/proactive actions. Rebuild clean compatible services from reviewed deployment authority, recommission external credentials, download/verify the chosen object, then materialise only validated regular files into an isolated private directory. `dr.archive.extract_archive` is reusable after full `validate_archive`; no arbitrary restore-to-root command is provided. Application-supported imports/restores and their semantic checks remain necessary.

Then restore each participant through its own application's supported procedure, and validate representative reads before exposing it. Examples from the author's setup: Hermes Agent is restored with its native import into a gated target; a Hindsight memory bank is rebuilt and loaded with its document-transfer import, then recall is proven; SQLite-backed apps are restored through their supported procedures; the login service is restored and proven before the apps that depend on it. This package does not automate imports, service activation, credential installation or failover.

Trigger download/validation manually after commissioning, important changes and periodically. Stronger rehearsals prove application semantics, memory recall, schedules, reauthentication and monitoring; a full clean-host rebuild is a further separate proof. Report actual execution and distinguish synthetic, gated and live evidence.

If you run a standby host that can take over (as the author does for an AI agent), then after a real promotion retain one authoritative writer and back up its new state. Quarantine a returning old host, preserve both histories and commission a reviewed reconciliation before failback. Rehearsal cleanup must never discard promoted state; whole-bank replacement is not automatically a lossless memory merge.
