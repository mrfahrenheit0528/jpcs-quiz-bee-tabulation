# Docker / LAN performance verification

Verified locally on 12 November 2026 (Asia/Manila), on branch `improve/docker-lan-performance`, based on `main` commit `3225aa2`. No changes were pushed. Windows, iPad Safari and second-device event-router acceptance remain outstanding.

## Protected original data

The pre-existing modified `instance/database.db` was not used for application tests, benchmarks or browser scoring. Its SHA-256 before and after implementation is:

```text
cdc04ed613067e88711c73450cff8ee09a0ed9ea53b72eb2b7cad1f4480b7de0
```

A consistent SQLite backup was created at `backups/original-20261111T211511Z.db`, with metadata in `backups/original.json`. Integrity check passed; no duplicate score keys were present. Backups, operational state, test artifacts and secrets are excluded from Git and the Docker build context.

The Linux launcher imported a consistent copy into the separate `jpcs-quiz-data` named volume and created a persistent random session key. **Its firewall/startup step still requires operating-system administrator authentication; the unanswered setup prompt was cancelled after verification work finished. Run `./quiz start` to resume setup.** The original database and original accounts were preserved; no seed script ran. The production app has not been declared LAN-ready.

## Automated regression coverage

` .venv/bin/python -m pytest -q `: **27 passed**. Existing SQLAlchemy `Query.get` deprecation warnings remain.

Coverage includes login/logout and role boundaries; event, school and assignment management; round ordering and activation/stopping; answer creation/edits and concurrent duplicate retries; stopped/unauthorized scoring rejection; all three scoring modes; qualification, cutoff tie-breakers, clean-slate hybrid finals and iterative clinchers; report rankings/content; conditional fragments and authentication; constant query counts; WAL/FULL/timeout configuration; duplicate migration rejection and repeatability; online backup/restore; offline assets; health and connection information.

A legacy undefined-variable typo in tie-breaker clean-winner reconstruction was fixed and covered by a regression test. Competition calculations, current screen ordering, device-local question locks, branding and report layout were otherwise preserved. This work does not introduce new competition completion/override rules or a scoring-workflow redesign.

## Controlled production-server benchmark

Both runs used the same disposable 15-school fixture and the same benchmark driver, with Waitress in a **separate process** from the client load generator: Python 3.14 / SQLite 3.54.0, eight server threads, 15 simultaneous scoring sessions, one admin, five viewers, 450 saves, 45 rapid edits/idempotent retries, polling and a concurrent PDF request. The baseline is the original commit plus injectable configuration only.

| Measurement | Original | Optimized | Target |
| --- | ---: | ---: | ---: |
| Save p95 | 2149.58 ms | **206.17 ms** | ≤300 ms |
| Save maximum | 2738.77 ms | 397.22 ms | not specified |
| Poll response p95 | 3595.98 ms | 159.75 ms | not a visual-update measurement |
| PDF during scoring | 14.659 s | **0.307 s** | ≤2 s |
| PDF after scoring | 10.879 s | 0.151 s | ≤2 s |
| Leaderboard queries, 15 schools | 21 | **7** | independent of school count |
| Round-control queries, 15 schools | 21 | **7** | independent of school count |
| Tabulator dashboard queries | 4 | 4 | independent of school count |

All **450 persisted answers** and the resulting standings were checked; no request errors occurred. Query-count tests compared 3 schools with 15 schools and confirmed equal counts.

Artifacts: `output/verification/baseline-isolated/results.json` and `output/verification/final-isolated/results.json`. Reproduction commands are in `OPERATIONS.md`.

These are loopback measurements, not Wi-Fi guarantees. Earlier same-process stress runs under overlapping browser/system work ranged from 187 ms to 381 ms save p95; the latter missed the target. The controlled reference run meets the target, but performance under host contention and on actual event devices still needs rehearsal.

## Browser and report verification

Chromium at tablet dimensions verified:

- login and scoring, sequential rapid edits, a simulated 503 retry, disconnection and local draft recovery;
- per-question locks surviving reload and the unsaved-navigation warning;
- **812 ms** from answer change to a visible leaderboard update, conditional 304 responses, and zero full-page polling fetches;
- hidden-page polling suspension and immediate resume (simulated document visibility, not physical iPad sleep);
- open connection-dialog preservation, focused control preservation and scroll preservation;
- admin stopping a round and activating the next round;
- a round closing with an unsaved draft, retaining that draft without redirecting, and committing it after reopening;
- locally loaded fonts, CSS, icons and JavaScript, with zero external runtime requests and no JavaScript page errors. Injected 503/offline failures produced the expected network-console entries.

Browser results and screenshots are under `output/verification/browser*-results.json` and `output/playwright/`. No horizontal page overflow was observed at 820×1180. This is Chromium testing, not Safari certification.

The synthetic 15-school report remains **four pages**, including the existing table spill and signatory pagination. All page text and word positions match the original exactly. Every final page was rendered and visually inspected; `qpdf --check` passed. Only prepared header/logo image resolution/encoding changed. Mean raster difference was approximately 0.19 on the 0–255 channel scale; geometry, fonts, content, colors and signatories were preserved. See `output/verification/pdf-comparison.json` and `report-page-*.png`.

## Container and native companion verification

A real Docker image was built and exercised using disposable named volumes. The final image uses checksum-pinned upstream SQLite **3.51.3** through Python's standard driver, with a build-time version assertion for the documented WAL-reset fix. Container persistence/restore checks were rerun on this runtime. Verified first import, repeat import, migration backup, health, non-root UID **10001**, a read-only container filesystem, durable saved answers, session survival across application restart and container recreation, and exported database/secret restore into another volume. Temporary verification containers and volumes were removed. Evidence: `output/verification/container.json`.

The host-local Avahi smoke test verified the advertised IPv4 record and `_http._tcp` service, removal of its D-Bus registration group on stop, and detection of a deliberately occupied hostname while keeping direct-IP information. The local resolver retained a cached A record briefly after registration withdrawal; stopping the application still removes HTTP service availability. This test does not prove another device can reach the laptop. Evidence: `output/verification/discovery.json`.

All PowerShell files were parsed with PowerShell 7.4 on Linux, and the C# native DNS-SD declarations compiled. Configuration defaults, mocked Docker argument forwarding and LAN subnet arithmetic passed. Native Windows APIs, Windows PowerShell 5.1 execution, UAC, firewall changes, Docker Desktop forwarding and scheduled-task lifecycle were **not executed on Windows hardware**. Evidence: `output/verification/windows-static.log`.

## Remaining acceptance checks

- Complete the Linux launcher's administrator authentication, inspect the effective scoped firewall rules, and repeat `start`, `status`, `backup` and `stop` on the operational launcher. Container persistence and native discovery were independently verified, but the fully elevated launcher sequence is not yet signed off.
- On another LAN device, test direct IP before hostname. Verify client isolation/VLAN settings and multicast on the actual event router.
- Run the entire launcher sequence on Windows 11, including terminal closure and reboot/manual restart.
- Test actual iPad Safari login, both QR modes, rapid edits, locks, reconnect, sleep/resume and round transitions.
- Change the host's DHCP address and verify new discovery records, direct-IP/QR refresh and stale-record withdrawal on real clients. Rerun `start` after an interface/subnet change to refresh scoped firewall rules.
- Test a real second-host hostname collision and the complete event with router internet disconnected. Browser external-request blocking passed; the physical offline-router test remains open.

The host network diagnosis remains qualified: the saved UFW policy lacks a TCP 5000 allowance and is a plausible cause of the previously reported failure. Effective firewall changes and second-device HTTP reachability have not been confirmed in this run.
