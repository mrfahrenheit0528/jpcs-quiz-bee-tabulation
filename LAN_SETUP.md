# Set up Quiz Bee on another Windows PC

This guide covers one host PC and tabulator phones, tablets, or laptops connected
to the same router. Only the host needs the project and server software. Tabulators
use a browser.

LAN access must be configured on each new host. The IP address and firewall rule
from the previous PC do not carry over.

## Choose a setup

| Setup | Use it for | Default port | Connection method |
| --- | --- | --- | --- |
| Docker event launcher | Running an event with persistent data | 5000 | Hostname or direct-IP QR |
| Native Python preview | Development and rehearsal | 5059 | Direct-IP QR |

The Python preview does not publish `jpcs-quiz.local`. Starting it without
`--lan-ip` makes it accessible only on the host PC.

## Before starting

1. Copy or clone the updated project onto the new host PC.
2. Connect the host to the event router through Ethernet or Wi-Fi.
3. Connect tabulator devices to the same LAN. Avoid guest Wi-Fi or router settings
   that isolate devices from each other.
4. Open PowerShell in the project folder. Run all commands below from that folder.
5. Keep the host awake while the event runs. Use one active host for the event.

Internet is needed for initial software installation and dependency/image downloads.
The application serves its own assets during the event.

## Option A: Docker event launcher

### 1. Prepare Docker and the database

Install and start Docker Desktop with Linux containers enabled.

Before the first launch, ensure `instance/database.db` contains the accounts and
event data you intend to import. The launcher imports this file only when its Docker
data volume has no database yet. It does not import the native preview's database
from `tmp/` automatically.

To move an existing Docker event, use the **Backup and restore** procedure in
[OPERATIONS.md](OPERATIONS.md#backup-and-restore). Transfer both the database backup
and its matching session-key file.

**Do not run `seed.py` on event data. It deletes the existing tables.**

### 2. Start the event server

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 start
```

Allow the Windows administrator prompt for host setup. The launcher configures the
selected LAN as Private, adds scoped firewall rules, starts the application, and
starts hostname discovery. Use a trusted event network.

The terminal prints the hostname URL, direct-IP URL, and discovery status.

### 3. Connect devices

Open the dashboard on the host at `http://localhost:5000` and log in with an
existing event account. Select **Connect Tabulators**.

- Use **Hostname QR** when discovery reports ready. The default URL is
  `http://jpcs-quiz.local:5000`.
- Use **Direct-IP QR** if the hostname does not resolve on a device.
- Tabulators scan the selected QR and log in using their assigned accounts.
- The projection leaderboard is available at `/siklab` on the same server.

If `quiz.env` changes the hostname or port, use the addresses printed by the launcher.

### 4. Stop, restart, and back up

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 backup
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 stop
```

Run `start` again after rebooting. Data stays in the Docker volume. Do not delete
that volume or run `docker compose down -v`.

For diagnostics:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 doctor
```

## Option B: Native Python preview over LAN

### 1. Install the dependencies

Install Python 3.13, matching the project's Docker runtime, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

The preview imports the test fixture helper, so it also needs `pytest`.
Recreate `.venv` on the new PC rather than copying it from the old PC.

### 2. Find the new host's LAN address

```powershell
Get-NetIPConfiguration
Get-NetConnectionProfile
```

Find the connected Ethernet or Wi-Fi adapter with a default gateway. Note its
**IPv4 address** and **interface alias**, for example:

```text
IPv4 address:    192.168.1.100
Interface alias: Wi-Fi
```

Replace these examples in the commands below with the new PC's actual values.
Do not use `127.0.0.1`, an address starting with `169.254`, or the old host's IP.

### 3. Allow the preview through Windows Firewall

Open a separate **PowerShell as Administrator**, then change to the project folder.
The selected network must be Private. On your trusted event router, you can set it
with the following command, substituting your interface alias:

```powershell
Set-NetConnectionProfile -InterfaceAlias 'Wi-Fi' -NetworkCategory Private
```

Add the preview firewall exception:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Enable-PreviewLan.ps1 -Port 5059 -Interface 'Wi-Fi'
```

This allows inbound TCP port 5059 only on the selected Private interface and from
its local subnet. It does not disable Windows Firewall.

### 4. Start the preview

For a new, disposable rehearsal with synthetic participants:

```powershell
.\.venv\Scripts\python.exe scripts\serve_fixture.py --lan-ip 192.168.1.100 --port 5059
```

This creates a temporary database. Its accounts are `admin1` and `tab1` through
`tab15`, all with password `test-password`. Changes are discarded when this
temporary fixture is cleaned up.

To resume an existing demo database instead:

```powershell
.\.venv\Scripts\python.exe scripts\serve_fixture.py --database tmp\siklab-demo-preserved.db --lan-ip 192.168.1.100 --port 5059
```

The `--database` file must already exist. This command preserves its existing
accounts, participants, rounds, and scores; it does not reseed the database.
Use those accounts' actual passwords.

Keep this terminal open while using the native preview. Press **Ctrl+C** to stop it.

### 5. Open the preview from other devices

With the example IP above:

- Home/login: `http://192.168.1.100:5059`
- Original leaderboard: `http://192.168.1.100:5059/leaderboard`
- Projection leaderboard: `http://192.168.1.100:5059/siklab`

On the admin dashboard, **Connect Tabulators** shows the direct-IP address and QR
code. Hostname QR is disabled because the native preview does not run hostname
discovery.

### 6. Transfer the current demo data to another PC

The current working demo is stored at `tmp/siklab-demo-preserved.db`. The `tmp/`
folder is ignored by Git, so cloning the repository does not transfer this data.

Pause score entry, then create a consistent standalone backup on the old PC:

```powershell
.\.venv\Scripts\python.exe -c "from website.migrate import backup; print(backup('tmp/siklab-demo-preserved.db', 'backups/demo-transfer.db'))"
```

The destination must be a new file. If it already exists, choose a new filename.
Copy the backup to the new PC, create its `tmp` folder if needed, and place the
backup there as `siklab-demo-preserved.db`. Start it with the `--database` command
above, using the new host's IP.

Use the backup helper instead of copying a live `.db` file that may depend on WAL
sidecars. To transfer a different demo database, substitute its actual source path.

## Verify access before the event

1. Open the direct-IP URL on the host PC.
2. Open that same URL from a separate phone or tablet on the event LAN.
3. Open **Connect Tabulators**, scan the QR, and confirm it reaches the correct host
   and port.
4. During rehearsal, save an answer as a tabulator and check that the leaderboard
   updates on another device.

A successful request from the host alone does not prove that other devices can
connect. Always complete the separate-device check.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Works on the host, fails on phones | Correct host IP and port, same LAN, Private firewall profile, matching firewall rule, no guest/client isolation |
| Native preview only listens on localhost | Restart it with `--lan-ip` and the actual host IPv4 address |
| QR points to the wrong port | Refresh the dashboard after restarting; the native preview normally uses 5059, Docker normally uses 5000 |
| Direct IP works, `.local` fails | Use Direct-IP QR; hostname discovery is provided by the Docker launcher, not the native preview |
| Host IP changed | Restart the native preview with the new IP; for Docker, rerun `start`. Refresh the QR afterward |
| Router, adapter, or subnet changed | Rerun the corresponding LAN/firewall setup for the new interface and subnet |
| Old page layout remains visible | Refresh with Ctrl+Shift+R; restart the server after Python code changes |
| Server stopped after reboot | Start it again; the launchers do not automatically start the event at boot |

For the native preview, inspect its listener and firewall rule:

```powershell
Get-NetTCPConnection -LocalPort 5059 -State Listen
Get-NetFirewallRule -Name JPCS-Quiz-Preview-5059
```

LAN preview mode should listen on `0.0.0.0:5059`. The firewall rule should be enabled
for the Private profile. If you choose a different port, use it consistently in the
server command, firewall command, browser URL, and diagnostic commands.

To remove the preview firewall exception later, run in administrator PowerShell:

```powershell
Remove-NetFirewallRule -Name JPCS-Quiz-Preview-5059
```
