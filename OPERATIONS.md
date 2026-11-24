# Quiz Bee event operations

Run one quiz host on the event router. Use a router that permits client-to-client traffic and multicast. Docker must be installed first. Internet is needed for initial image/package provisioning; the event application serves its own CSS, fonts, icons, JavaScript, QR codes and reports.

## Start and stop

Linux / Omarchy (native Docker Engine):

```bash
./quiz start
./quiz status
./quiz doctor
./quiz logs
./quiz backup
./quiz stop
```

Windows 11 (Docker Desktop, Linux containers):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 doctor
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 logs
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 backup
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 stop
```

The terminal may close after `start`. The application container and discovery companion run in the background. Keep the host awake and logged in. Neither component is configured to start automatically at boot; run `start` again after reboot. `stop` withdraws discovery and stops the application without deleting the volume. Existing event accounts are imported; the destructive `seed.py` is never invoked.

First startup builds the image (including a checksum-pinned SQLite 3.51.3 shared library containing the upstream WAL-reset fix) and requests administrator authentication for the selected LAN's firewall/discovery setup. Linux uses `sudo` in an interactive terminal or `pkexec` from a graphical caller; Windows uses UAC. The Windows helper sets the selected event network to **Private**. Use this only on your trusted event router. After initial provisioning, an unchanged build is reused. Changes to application sources, assets, requirements or Dockerfile trigger a rebuild. Run an initial start/stop rehearsal while internet is available.

Default addresses:

- `http://jpcs-quiz.local:5000`
- `http://<host LAN IPv4>:5000` as the direct-IP fallback.

The admin dashboard's **Connect Tabulators** dialog shows both addresses, discovery status and selectable QR codes. Its direct-IP address refreshes when the host companion reports an address change.

## Configuration

Copy `quiz.env.example` to `quiz.env`, then edit its plain `KEY=value` settings. No shell interpolation or quotes are used.

| Key | Default | Meaning |
| --- | --- | --- |
| `QUIZ_HOSTNAME` | `jpcs-quiz.local` | One lowercase DNS label plus `.local` |
| `QUIZ_PORT` | `5000` | HTTP TCP port, 1024–65535 |
| `QUIZ_INTERFACE` | empty | Physical Linux interface name / Windows adapter alias; otherwise active physical LAN is selected |
| `QUIZ_VOLUME` | `jpcs-quiz-data` | Docker named volume containing database, backups and persistent session key |

Environment variables override the file. Restart with `start` after changing settings. Only one host/container/discovery companion is supported. Linux uses host networking so host INPUT firewall rules apply. Windows publishes the configured port through Docker Desktop. Remote Docker contexts and Linux Docker Desktop are not supported by the Linux launcher.

## Data protection and migration

The original `instance/database.db` stays outside the image and is mounted read-only only during initial import. A consistent SQLite backup is imported **only when `/data/database.db` is absent**. Later starts never copy over the operational database. Stop the legacy application before first import. If the legacy database is in WAL mode, use a consistent standalone SQLite backup (DELETE journal mode); do not copy a live `.db` file while omitting its WAL. A read-only WAL source without its required sidecars fails safely rather than dropping data.

The named volume stores:

- `/data/database.db`, with WAL enabled during operation, `synchronous=FULL`, and a five-second busy timeout;
- `/data/session.key`, randomly generated on first import and reused across restarts/recreation;
- `/data/backups/`, including automatic pre-migration snapshots.

Schema migration 1 adds a unique `(round_id, school_id, question_number)` index and lookup indexes. Migration checks integrity, rejects newer schema versions and lists duplicate keys without changing rows. If duplicates exist, reconcile a **copy** with the event administrator, retaining all conflicting originals for review. No duplicate is chosen or deleted automatically.

Saves are acknowledged after commit. Each scoring page sends one save at a time and retains unsaved changes in browser local storage through disconnects/reloads. A fair writer queue serializes application mutations before reading round state, so stopping a round cannot race a save inside this single-server deployment. Retried identical answers update the same score row. Question locks retain their original device-local behavior. One tabulator should use one scoring tab/device per school; simultaneous editors still use last-committed-write behavior.

If a round closes with pending answers, the page keeps the draft and tells the tabulator to ask for reopening. It does not claim those answers were saved. If local storage is unavailable, changes remain in memory only until the page closes.

## Backup and restore

Run `backup` before an event and after results are finalized. It uses SQLite's online backup API and exports a standalone `backups/quiz-<timestamp>.db` plus `quiz-<timestamp>.session.key`. Copy both to a separate secure drive. Normal stop/recreation preserves the named volume. **Do not run `docker compose down -v` or remove the named volume.**

Restore requires stopping the application first. The restore helper refuses while the application holds its volume lock, validates/migrates a staged copy, and backs up the existing database before replacement. Replace the filenames below with your matching backup pair. Use the same `QUIZ_VOLUME` and other settings as the launcher (export them in the shell, or supply `--env-file quiz.env` after `docker compose`).

Linux:

```bash
./quiz stop
docker compose -f compose.yaml -f compose.linux.yaml run --rm --no-deps \
  -v "$PWD/backups:/restore:ro" app python -m website.manage restore \
  /restore/quiz-TIMESTAMP.db --secret /restore/quiz-TIMESTAMP.session.key
./quiz start
```

Windows PowerShell:

```powershell
.\quiz.ps1 stop
docker compose -f compose.yaml -f compose.windows.yaml run --rm --no-deps `
  -v "${PWD}\backups:/restore:ro" app python -m website.manage restore `
  /restore/quiz-TIMESTAMP.db --secret /restore/quiz-TIMESTAMP.session.key
.\quiz.ps1 start
```

To roll back code, stop the launcher, retain an exported backup pair, and restore a compatible code version on a separate local branch/worktree. The pre-migration database is in the volume's `backups` directory. Run old code against a restored **copy**, never overwrite the protected original during rollback. This branch and all implementation work remain local; no push is part of these commands.

## Discovery, firewall and diagnostics

Run `doctor` on the host, then test from another device in this order:

1. Open the direct-IP URL. If it fails, inspect firewall rules, the chosen LAN interface/subnet, guest Wi-Fi/client isolation and VLAN routing. A host-local HTTP 200 does not prove external access.
2. Open the hostname URL. If direct IP works but hostname fails, inspect mDNS multicast, hostname collision messages and the companion's status. Direct-IP and direct-IP QR remain usable.
3. In the admin dialog, confirm the displayed address matches the host's current address. Allow up to roughly six seconds for discovery address-change detection, plus three seconds for dashboard refresh. Initial hostname probes can add two seconds. Resolver caches may retain withdrawn names briefly even after the companion removes its registrations.

Linux publishes the address and `_http._tcp` service with Avahi through its native D-Bus API on the selected interface (host packages `avahi` and `python-dbus`), supervised by a transient **systemd user unit** `jpcs-quiz-discovery.service`. Windows uses the native DNS-SD registration API, supervised by a manually started **scheduled task** `JPCS Quiz Discovery` with no triggers. Address changes withdraw old registrations before publishing new ones. Collision/registration errors are shown explicitly; the application remains accessible by IP. If the interface/subnet changes, rerun `start` to update firewall scoping. The companion does not silently widen rules.

Linux inspection:

```bash
systemctl --user status jpcs-quiz-discovery.service
journalctl --user -u jpcs-quiz-discovery.service -n 50
cat .quiz/network.json
cat .quiz/discovery.log # present if discovery reported an error
sudo ufw status numbered
ss -ltnp 'sport = :5000'
avahi-resolve -4 -n jpcs-quiz.local
avahi-browse -rt _http._tcp
```

The helper manages only rules commented `jpcs-quiz http` and `jpcs-quiz mdns`. For the example interface `wlp1s0`, subnet `192.168.0.0/24` and port `5000`, the exact UFW allowances are:

```bash
sudo ufw allow in on wlp1s0 from 192.168.0.0/24 to any port 5000 proto tcp comment 'jpcs-quiz http'
sudo ufw allow in on wlp1s0 from 192.168.0.0/24 to any port 5353 proto udp comment 'jpcs-quiz mdns'
```

It preserves unrelated rules and does not enable an inactive firewall. For removal, inspect `sudo ufw status numbered` and delete only the two quiz-labelled rules (highest number first). Avahi is started, not enabled at boot by this project.

Windows inspection and equivalent firewall commands (elevated PowerShell; substitute the selected adapter/subnet):

```powershell
Get-ScheduledTask -TaskName 'JPCS Quiz Discovery'
Get-Content .quiz\network.json
Get-NetTCPConnection -LocalPort 5000 -State Listen
Get-NetFirewallRule -Group 'JPCS Quiz LAN'
Set-NetConnectionProfile -InterfaceIndex 7 -NetworkCategory Private
New-NetFirewallRule -Name 'JPCS-Quiz-HTTP' -DisplayName 'JPCS Quiz HTTP' -Group 'JPCS Quiz LAN' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000 -RemoteAddress 192.168.0.0/24 -InterfaceAlias 'Wi-Fi' -Profile Private
New-NetFirewallRule -Name 'JPCS-Quiz-mDNS' -DisplayName 'JPCS Quiz mDNS' -Group 'JPCS Quiz LAN' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5353 -RemoteAddress 192.168.0.0/24 -InterfaceAlias 'Wi-Fi' -Profile Private
```

The Windows helper replaces only rules in its `JPCS Quiz LAN` group. Remove those rules with `Get-NetFirewallRule -Group 'JPCS Quiz LAN' | Remove-NetFirewallRule`. It never modifies unrelated rules.

## Reproducible verification

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark_lan.py --output output/verification/benchmark
docker compose -f compose.yaml -f compose.linux.yaml build
.venv/bin/python scripts/verify_container.py
```

These use temporary databases and temporary Docker volumes. The benchmark runs its production server in a separate process from the load generator and uses Waitress with eight threads, 15 scorers, one admin poller, five viewer pollers, 450 saves, 45 edits/retries and a concurrent PDF request. Compare the same machine under comparable load. LAN/Wi-Fi latency is separate from loopback latency.

For browser rehearsal, run `.venv/bin/python scripts/serve_fixture.py` on loopback port 5059. Its synthetic accounts are `admin1`, `tab1`–`tab15`, password `test-password`; these exist only in the temporary fixture. `scripts/browser_check.js` runs through Playwright CLI against this fixture. It is never used on the operational event database.

Before the actual event, test on **both Windows 11 and Linux**, then on real **iPad Safari**: login, both QR codes, rapid edits, locks, disconnect/reconnect, sleep/wake, round transitions, DHCP address change, a deliberate hostname collision, and operation with router internet unplugged. See `VERIFICATION.md` for which checks have actually been completed.

References: [SQLite WAL](https://www.sqlite.org/wal.html), [Avahi publishing](https://man.archlinux.org/man/extra/avahi/avahi-publish.1.en), [Windows DNS-SD registration](https://learn.microsoft.com/en-us/windows/win32/api/windns/nf-windns-dnsserviceregister), [Docker firewall behavior](https://docs.docker.com/engine/network/packet-filtering-firewalls/), [Waitress configuration](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html).

To reproduce the original implementation baseline (commit `3225aa2`, with only injectable test configuration added):

```bash
.venv/bin/python scripts/prepare_baseline.py
QUIZ_BENCH_APP_ROOT="$PWD/tmp/baseline-app" .venv/bin/python scripts/benchmark_lan.py --output output/verification/baseline-isolated
.venv/bin/python scripts/benchmark_lan.py --output output/verification/final-isolated
```

The extracted baseline's bundled database is not opened; both runs create their own synthetic databases.
