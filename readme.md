# Quiz Bee Tabulation System

A web-based tabulation system developed for the **Junior Philippine Computer Society – CSPC Chapter** to automate scoring, qualification, tie-breaking, live rankings, and official result generation for academic quiz bee competitions.

The system supports multiple competition formats, including cumulative scoring, clean-slate final rounds, and recursive clincher rounds for unresolved ties.

## LAN event launcher

Use `./quiz start` on Omarchy/Arch with native Docker Engine, or
`powershell -NoProfile -ExecutionPolicy Bypass -File .\quiz.ps1 start` on Windows 11 with Docker Desktop.
First startup imports the existing database into a persistent named volume, preserves existing accounts,
and sets up LAN access. The default URL is **http://jpcs-quiz.local:5000**.

Read [OPERATIONS.md](OPERATIONS.md) for prerequisites, backups, restore, firewall commands and diagnostics.
Read [VERIFICATION.md](VERIFICATION.md) for measured performance and hardware checks still outstanding.
Do not run `seed.py` against event data; it is destructive.

---

## Project Explanation

The Quiz Bee Tabulation System was designed to reduce manual score computation during academic competitions.

It provides a centralized platform where administrators can manage events and rounds, tabulators can record scores, and viewers can monitor live rankings. The system also automatically handles qualification rules, tie detection, clincher rounds, and final placements.

---

## Key Features

### Advanced Scoring Engine
- **Hybrid Scoring:** Supports cumulative scoring during elimination rounds and clean-slate scoring during finals.
- **Flexible Configuration:** Can also use cumulative-only or per-round scoring modes.

### Recursive Tie-Breaking
- Detects ties at qualification cutoffs and ranking positions.
- Automatically supports additional clincher rounds when ties remain unresolved.
- Helps ensure unique final placements for winning teams.

### Role-Based Dashboards
- **Admin Dashboard:** Manage events, rounds, participants, scoring rules, and live competition controls.
- **Tabulator Panel:** Provides a focused interface for recording participant scores.
- **Live Leaderboard:** Displays automatically updated rankings for viewers.

### Official Reporting
- Generates competition result reports in PDF format using FPDF.
- Adjusts report layouts according to the rounds completed.
- Includes signatory sections for authorized competition personnel.

---

## Methodology

The system was developed by translating the competition's scoring and qualification rules into automated application logic.

The workflow follows four main stages:

1. **Event Configuration** — administrators create the competition, rounds, participants, and scoring rules.
2. **Score Entry** — tabulators record participant answers during active rounds.
3. **Automated Evaluation** — the system calculates scores, rankings, qualification results, and detects ties.
4. **Result Generation** — final rankings are displayed through the leaderboard and can be exported as official PDF reports.

---

## Results

The completed system can manage an end-to-end quiz bee competition, including:

- Multi-round scoring
- Automatic score calculation
- Qualification of teams
- Clean-slate final rounds
- Tie detection and clincher rounds
- Live leaderboard updates
- Final ranking
- PDF result generation

This reduces the need for manual tabulation and helps provide a more consistent and organized competition workflow.

---

## Tech Stack

**Backend:** Python, Flask, SQLAlchemy  
**Database:** SQLite  
**Frontend:** HTML5, CSS3, Bootstrap 5, Jinja2  
**PDF Engine:** FPDF  
**Icons:** Font Awesome  

---

## Installation & Setup

Install Docker Engine with Compose on Linux, or Docker Desktop with Linux containers on Windows 11.
Keep the existing `instance/database.db` in this checkout. Run the event launcher above;
it imports existing accounts and data on the first start only.

For local development and disposable test fixtures, see [OPERATIONS.md](OPERATIONS.md).
`main.py` is the production container entry point and expects a prepared data directory.

---

## User Guide

### Admin

- Log in through `/login` (use an existing event account)
- Create and configure an event
- Define competition rounds
- Set the number of qualifiers
- Register participating schools
- Assign tabulator accounts
- Start and manage active rounds
- Evaluate scores and rankings

### Tabulator

- Log in using the assigned account
- Wait for the administrator to activate a round
- Record correct and incorrect answers through the scoring interface

### Viewer

- Open `/leaderboard`
- View automatically refreshed competition standings

---

## Developer

**Guiller Angelo Hermoso**

Developed for the **Junior Philippine Computer Society – CSPC Chapter**.

---

## License

This project is proprietary software developed for **JPCS-CSPC Chapter**.
