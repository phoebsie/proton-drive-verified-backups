# Setup with your own Proton Drive account

Start with a disposable destination and synthetic captures on your own Linux host. These instructions do not authorise deployment of this private candidate into its source production system.

## Dependencies and installation

Use Python 3.12+, zstd, GnuPG, `pass`, CA certificates and systemd. For Debian/Ubuntu:

```sh
sudo apt-get install python3 zstd gnupg pass ca-certificates
sudo install -d -m 0755 /opt/dr-reference
sudo install -d -m 0700 /etc/dr-reference /var/lib/dr-reference
```

Copy only the reviewed package's `dr`, `scripts`, `tests` and `examples` directories into `/opt/dr-reference`, preserving executable modes. Make code/config root-owned and non-writable by service clients. Never copy a private source/review workspace. There are no pip dependencies. Run the tests from the package root first.

## Pin and authenticate the CLI

Obtain the Linux binary from [Proton's official downloads](https://proton.me/drive/download). Verify publisher provenance and any available publisher checksum/signature before installing. A self-calculated hash detects later changes; it does not prove authenticity. Keep your exact release/version and verified digest in private commissioning notes. No binary is bundled or downloaded automatically.

```sh
sudo install -d -m 0755 /opt/dr-reference/bin
# ./proton-drive means your verified downloaded binary.
sudo install -o root -g root -m 0755 ./proton-drive /opt/dr-reference/bin/proton-drive
sudo /opt/dr-reference/bin/proton-drive version
sudo sha256sum /opt/dr-reference/bin/proton-drive
```

The reference uses the production `filesystem list/upload/download/trash` argv contract. Releases can change interfaces: inspect your binary's `--help` and subcommand `--help`, then commission its behavior. The parser accepts name strings or encrypted `name.value` and several production-observed size keys, including `activeRevision.claimedSize`. Unknown schemas fail closed.

For the root service example, prepare a **dedicated** GPG encryption key/pass store as root; initialise pass with your own fingerprint, then login interactively. Never put passphrases, account passwords or MFA codes in argv, environment files or Git:

```sh
sudo -H gpg --full-generate-key
# Replace YOUR_FINGERPRINT with your own public key fingerprint.
sudo -H pass init YOUR_FINGERPRINT
sudo -H env PROTON_DRIVE_CREDENTIALS_STORE=pass /opt/dr-reference/bin/proton-drive auth login
```

The [official CLI guide](https://proton.me/support/drive-cli) documents browser login, filesystem commands and `--json`. The pass backend/session-entry convention below comes from the source implementation. Confirm your installed version supports it; stop if it selects another backend. Do not silently fall back to plaintext credentials.

Create an empty dedicated `DR Reference` folder in your Drive using your own client. Confirm unattended listing as the exact account/HOME/GNUPGHOME that will run systemd. Never point this example at another workflow's folder.

## Opt in to unattended GPG unlock

Read [SECURITY.md](SECURITY.md). This arrangement stores the GPG unlock phrase in a root-only local file. Compromised root can decrypt the pass store and use the Proton session. File permissions do not protect against root or unencrypted disk theft.

Copy `examples/gpg.json` to `/etc/dr-reference/gpg.json`, mode `0600`. Replace the placeholder with your encryption-subkey keygrip (`sudo -H gpg --list-secret-keys --with-keygrip` prints no private key). Check your local preset binary and pass session entry. The source uses `ch.proton.drive/drive-sdk-cli/auth-session`, a software path, not a personal account identifier.

In the **dedicated** `/root/.gnupg/gpg-agent.conf`, configure exactly one active line each:

```text
allow-preset-passphrase
default-cache-ttl 172800
max-cache-ttl 172800
```

This 48-hour window exceeds daily cadence. Boot and daily units seed the agent. Default GPG TTLs can expire before a daily run; zero can mean immediate expiry. This is not a never-expiring cache.

Create `/etc/dr-reference/gpg-passphrase` interactively using a secure local editor/input method, root-owned mode `0600`, containing only your GPG key passphrase and newline. Do not use `echo actual-passphrase` or put it in a command. Restart only that dedicated agent to load policy:

```sh
sudo -H gpgconf --kill gpg-agent
sudo /opt/dr-reference/scripts/preset-gpg /etc/dr-reference/gpg.json
```

The helper checks file permissions, policy and keygrips, supplies the phrase on stdin, and probes `pass show` with output discarded. It never logs a keygrip or secret. Package tests mock its processes with invented inputs; real GPG/pass/Proton commissioning remains necessary. Hardware-sealed unlock or a scoped service token would be alternatives if available and compatible; neither is implemented.

## Configure and commission

Copy `examples/config.json` to `/etc/dr-reference/config.json`, mode `0600`. Set your verified binary digest (all-zero intentionally fails), destination and paths. **Replace synthetic captures with supported application backups before counting outputs as DR.** See [ADAPTERS.md](ADAPTERS.md). Every registered participant is mandatory.

Copy `examples/notify.json` to `/etc/dr-reference/notify.json`, mode `0600`, and enter your own HTTPS notification URL/optional bearer token locally. The `.invalid` sample cannot deliver. The endpoint must accept POSTed text and return 2xx; ntfy-compatible endpoints work. Redirects are refused. Choose a destination independent of the agent gateway and confirm real delivery.

```sh
sudo /opt/dr-reference/scripts/dr --config /etc/dr-reference/config.json preflight
sudo /opt/dr-reference/scripts/preset-gpg /etc/dr-reference/gpg.json
sudo /opt/dr-reference/scripts/dr --config /etc/dr-reference/config.json run
# Replace the placeholder with the exact object from your private status receipt:
sudo /opt/dr-reference/scripts/dr --config /etc/dr-reference/config.json verify YOUR_GENERATION_OBJECT_NAME
sudo /opt/dr-reference/scripts/dr --config /etc/dr-reference/config.json check
```

`verify` and `preflight` do not reseed GPG themselves: preset first after an agent restart/cache expiry. Preserve trusted receipts/digests separately from this controller for clean-host recovery. For alert proof, use a disposable config/root with empty status and confirm a real notification; never manufacture failures by editing live status. Reboot-test unattended access in your own safe context.

## Install and enable units

From the package root:

```sh
sudo install -m 0644 systemd/dr-reference*.service systemd/dr-reference*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start dr-reference.service
sudo systemctl start dr-reference-monitor.service
sudo systemctl enable --now dr-reference-gpg.service dr-reference.timer dr-reference-monitor.timer
sudo systemctl list-timers 'dr-reference*'
```

The daily job runs at 03:00 UTC plus up to 30 minutes jitter; monitoring runs every 30 minutes. A six-hour service timeout bounds the entire generation and kills its process group. Overlap exits 75 without counting a backup failure. No application restart or restore timer is installed. Restore validation is manually triggered.

The monitor survives agent failure, but shares the controller host/network. Detecting total controller loss requires a separately commissioned external heartbeat monitor, not provided here.

An unclean kill/host crash can leave plaintext work or an unreceipted remote upload. Inspect leftover `capture-*`/`restore-*` only while no operation holds `run.lock`; do not delete arbitrary paths. Retention ignores unknown/unreceipted objects. Trash/orphans can consume quota; the bound covers managed verified live objects, not account-wide storage. After losing the receipt ledger, reconcile ownership manually; old objects are not automatically adopted/pruned.
