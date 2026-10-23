# Derivation and intentional differences

Transport, manifest, streaming tar+zstd and retention modules are adapted from Phoebie Agent production DR code and distributed under this project's MIT licence. This is a standalone reference; production operator and private agent implementations are not included.

| Area | Retained behavior | Reference changes/unsupported features |
| --- | --- | --- |
| Transport | Fixed argv, no shell, separate JSON listing, required size, observed listing shapes, trash-only delete | Private probes removed; diagnostics discarded instead of best-effort redaction; duplicate-name rejection; per-operation binary digest |
| Manifest | Schema-v1 provenance, participants, sizes/hashes, recommission list | Empty provenance placeholders; exact config participant/file set additionally required; no runtime discovery |
| Archive | Stream tar through zstd, member/hash verification, no tar sidecar | Additional isolated extraction for payload checks; stricter names/duplicates/bounds; larger working set than production |
| Capture | All participants required; supported snapshots/exports | Local argv contract; executable SQLite, simple Hermes and 0.10.x Hindsight adapters; no private bridge/receipt/operator adjunct/container authority implementation |
| Retention | Production naming and exact 5 daily/2 weekly/2 monthly algorithm; verify before prune | Same-controller receipt eligibility only; no old-ledger adoption; trash not emptied |
| Monitor | Separate host timer, >48h stale, 2 failures, 24h re-alert, healthy silence | Generic HTTPS notifier; separate alert file/lock; invalid time/status/retention alerts; no production operator recovery class |
| Restore | Separate download, member hashes, SQLite, private work | Explicit object required; no imports/start; whole-archive trust requires separate receipt/digest |
| Units/auth | Daily host timer, independent half-hour monitor, boot/per-run GPG seed | Generic paths/units; agent policy prepared explicitly; helper refuses drift instead of rewriting/restarting automatically |

The reference is bounded to 20 GiB expanded payload, 100,000 entries and 1 MiB manifest. The simple Hermes adapter refuses unresolved WAL sidecars instead of production repair. Neither it nor the bank exporter was commissioned against a live application in this packaging exercise. Service activation, complete clean-host rebuild, live Discord cutover, memory merge and failback are not bundled or claimed.

Synthetic examples and the invalid all-zero binary digest are deliberate gates. `make-demo-config` provides a runnable offline environment; using your Proton account needs real binary/auth setup, and real applications need reviewed capture commands. These are working scripts with explicit configuration requirements, not pseudocode.
