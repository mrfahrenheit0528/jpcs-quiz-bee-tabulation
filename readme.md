# 🏆 Quiz Bee Tabulation System  
**Automated Tournament Logic Engine for Academic Competitions**

A specialized, enterprise-grade tabulation system designed to handle complex academic competition rules, including Hybrid Scoring (Cumulative + Clean Slate), Recursive Tie-Breaking, and Real-time Leaderboards.  
Built for the **Junior Philippine Computer Society – CSPC Chapter**.

---

## 🌟 Key Features

### ⚙️ Advanced Scoring Engine
- **Hybrid Logic:** Automatically switches between Cumulative Scoring (eliminations) and Back-to-Zero/Clean Slate (final round).  
- **Flexible Configuration:** Supports strict "Cumulative" or simple "Per Round" modes.

### ⚔️ Iterative & Recursive Tie-Breaking
- **Smart Detection:** Detects ties at qualifying cutoffs (e.g., 3 schools tied for the last slot).  
- **Recursive Clincher Rounds:** If tied again, the system auto-creates Clincher 2, 3, etc.  
- **Strict Final Ranking:** Enforces Gold–Silver–Bronze by forcing tie-breakers until all positions are unique.

### 🖥️ Role-Based Dashboards
- **Admin Mission Control:** Real-time monitor, round lock/unlock, and instant “Sudden Death” (+1 Q).  
- **Tabulator Panel:** Secure parallel scoring interface for rapid data entry.  
- **Live Leaderboard:** Auto-updates, hides cumulative info in finals, highlights active teams and winners.

### 📄 Official Reporting
- **Automated PDF Generation** using FPDF.  
- **Dynamic Layout:** Adjusts automatically based on rounds played.  
- **Digital Signatories:** Auto-generated blocks for Tabulators and Head Admin.

---

## 🛠️ Tech Stack

**Backend:** Python, Flask, SQLAlchemy  
**Database:** SQLite (Development)  
**Frontend:** HTML5, CSS3, Bootstrap 5, Jinja2  
**PDF Engine:** FPDF  
**Icons:** FontAwesome  

---

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/jpcs-quiz-bee-tabulation.git
cd jpcs-quiz-bee-tabulation
````

### 2. Create a Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
python main.py
```

The app will run at **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

---

## 📖 User Guide

### 1. **Admin (Mission Control)**

* Login via `/login` (Role: Admin)
* Create Event → Choose **Hybrid**
* Define rounds (Easy/Average/Difficult/Final)
* Set number of qualifiers
* Register schools + assign Tabulator accounts
* Use **Live Round Control** to start rounds and evaluate scores

### 2. **Tabulator (Data Entry)**

* Login with assigned credentials
* Wait for Admin to start the round
* Enter scoring (Correct/Wrong toggles)

### 3. **Viewer (Audience)**

* Open `/leaderboard`
* Auto-refreshes every 3–5 seconds

---

## 📸 System Screenshots

*(Insert Mission Control, Scoring Page, Leaderboard images here)*

---

## 👥 Credits & Acknowledgements

**Developed By:**
Guiller Angelo Hermoso – Director for Projects 2025

**Powered By:**
Junior Philippine Computer Society – CSPC Chapter
*“Excellence in Technology, Leadership in Action.”*

---

## 📄 License

This project is proprietary software developed for JPCS-CSPC.

```
