# Phoebie Agent: two-host disaster recovery

Phoebie is a personal-agent ecosystem: Hermes is its runtime, Hindsight its durable semantic memory, Finance/Fitness own specialist state, and an auth service owns authentication. Personal identities, endpoints, accounts, bank names, paths, key IDs and operator receipts are omitted here.

```text
Home: Hermes + Hindsight
          | supported captures, restricted private transport
          v
VPS: Finance + Fitness + auth service
     DR controller assembles all five participants
          | daily upload + independent expected-size listing
          v
Proton Drive: off-provider encrypted storage

VPS timers: daily generation + separate half-hour dead-man
Reviewed source repositories: rebuild/deployment authority
External identities/credentials: deliberate recommissioning
```

Home is the ordinary authoritative agent/memory host. VPS emergency Hermes/Hindsight are normally dormant. Home loss has a gated recovery path on the surviving VPS. VPS loss requires rebuilding its controller/domain services from reviewed deployment authority and restoring verified off-provider state while preserving Home authority. The architecture is **designed to survive loss of either host, with verified round trips and a gated recovery rehearsal**. A full replacement-VPS/clean-host rebuild was deliberately waived by the system owner and remains unproven. This packaging exercise establishes no current live-host health.

Finance uses its supported online database backup; Fitness its own backup primitive; Hermes native full backup; Hindsight a supported provider-neutral bank export including observations/knowledge base; auth a narrow recovery allowlist. Captures are sequential, not a distributed transaction. Daily cadence is an RPO target; failed runs increase actual recoverable age. A 48-hour alarm is not a guaranteed maximum data loss.

Current Hermes capture uses full `hermes backup`, with supported native import on recovery. The retired stop/copy/restart design is not current. Production runs the unmodified backup CLI in an isolated throwaway container using the live image and declared durable-data bind while the live agent stays running. Guards classify foreign mounts, repair known non-`.db` WAL cases, exclude reconstructable credential/browser artifacts and validate a versioned capture receipt. Hindsight export avoids reliance solely on its database engine's private layout. The reference omits this private host/operator implementation and memory logic.

All participants, local validation, upload and independent expected-size listing must pass before freshness/retention. Separate download checks verify hashes and database integrity. Restore rehearsals are periodically **manually triggered**; no timer schedules them. Ordinary generations supply five daily, two weekly and two monthly points, at most nine distinct retained generations.

The CLI is pinned to a release, with installation checksum recorded and checked by status/preflight. Production does not recheck it on every upload; the reference strengthens this to per top-level transport operation. `list --json` already exists. The useful upstream request is a **stable documented JSON schema**, plus structured upload results with node ID, size and hash.

Unattended pass/GPG is an accepted compromise: root-only unlock file, boot/per-use agent preset and enforced **48-hour cache window**, not a never-expiring cache. Compromised root can recover the session. A scoped token/service account could address headless authentication differently; none is implemented here.

The independent dead-man has caught **multiple real failures**, including capture/recovery and transport failures. Later source records include capture visibility and private capture-listener incidents; neither should be called a Proton storage outage. Monitoring is independent of Hermes, but runs on the VPS; controller loss requires external detection.

## Recorded evidence versus untested claims

| Evidence | Supports | Does not prove |
| --- | --- | --- |
| Upload/list and separate download/member-hash/SQLite checks | Recorded off-provider round trips | Clean-host rebuild of every service |
| October 21 gated rehearsal | Native Hermes import, Hindsight import/recall, private text turn, domain reads, isolated backup proof, return dormant | Live channels, positive Home fencing, Voice/GPU/Browser recovery, lossless failback |
| October 22 activation work | Promotion implementation, simulated activation and production negative checks | Tested live Discord activation or production execution of the capture-source switch |
| Failback runbook | One-writer/quarantine/history-preservation design | Commissioned memory merge, automatic sync or tested failback |

October 21 treated Home as unavailable **as a recovery input** after a simulation boundary; it was not destroyed. VPS stayed gated: pause, channel tokens removed/escrowed, jobs held and no second live agent writer. Finance/Fitness/auth remained available. The isolated rehearsal backup used a separate namespace and did not advance canonical freshness or prune.

October 22 added manual incident activation with explicit fencing and manual approval gates. **Live Discord cutover was not tested.** Ping/network loss is insufficient fencing. Voice, GPU speech and persistent browser profiles remain outside proven emergency capability. Historical reboot evidence is not an October 21 reboot test. Hindsight failback remains design-only, not a commissioned reconciliation tool.

The auth exception allows approved auth database/password-hash, session/storage and signing material within the encrypted off-provider generation. It does not broaden host-secret scope. Native Hermes artifacts remain sensitive under their own reviewed application-secret contract. Machine/SSH/deployment identities, Proton access, external OAuth/provider/tunnel sessions and excluded browser state require reauthentication/recommissioning. An archive alone is not everything needed for service recovery.

The runnable package's invented fixtures/offline tests are separate from recorded production evidence. It includes no proprietary perception, personalisation, memory-quality or cross-domain orchestration implementation, and no production control-plane material.
