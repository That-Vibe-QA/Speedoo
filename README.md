# Speedoo ⚡
> **Type fast. Compete. Win.**

Speedoo is a full-featured, responsive, and precision-scored typing speed test web application designed for both individual typing practice and competitive multi-user typing contests. Built with a lightweight, modular architecture using Python, Flask, SQLite/SQLAlchemy, and modern vanilla JavaScript.

Developed and maintained by **PazhaTholi**.

---

## 🌟 Key Features

### 1. Core Experience & Design
- **Modern, Accessible UI**: High-contrast, dark-mode-first aesthetic with clean typography, visible focus rings, and responsive mobile-ready layout.
- **Accessible Character States**: Correct characters, incorrect characters, and the active cursor are clearly differentiated through colors, backgrounds, and distinct styling (such as wavy underlines) without relying on color alone.
- **Dynamic Footer & Branding**: Consistent branding featuring "Speedoo", tagline *"Type fast. Compete. Win."*, and a dynamic year copyright:
  `© [current year] PazhaTholi. All rights reserved.`

### 2. Individual Practice
- **Test Formats**:
  - **Timed Tests**: 30 seconds, 1 minute (60s), 2 minutes (120s), and 5 minutes (300s).
  - **Paragraph Completion**: Finish a given passage completely and accurately.
- **Graded Passages**: Easy, Medium, and Hard difficulty categories with live word and character counts.
- **Zero Registration Needed**: Jump right in and practice typing without signing up.
- **Live Metrics**: Real-time Words Per Minute (WPM), accuracy percentage, elapsed/remaining time, and completion progress.
- **Anti-Cheat Restrictions**: Paste, drag-and-drop text insertion, browser autocomplete, autocorrect, and spellcheck are disabled on the typing input.
- **Interactive Results**: Detailed breakdown of WPM, Accuracy, Completion Time, Incorrect Keystrokes, and Backspaces, with an instant retry action.

### 3. Organized Competitions
- **Competition Formats**:
  1. **Timed Sprint**: Participants race for a fixed duration. Ranked by WPM, then accuracy, then fewer incorrect attempts.
  2. **First-to-Complete**: Race to complete the exact passage. Ranked by lowest server-measured elapsed time, then higher accuracy, then fewer incorrect attempts.
- **Fairness & Server as Source of Truth**:
  - Client timestamps and browser WPM claims are never blindly trusted.
  - Ordered typing events (`insert` / `backspace`) are sent in sequence to the server for validation against the passage.
  - Monotonic browser clock (`performance.now()`) is used for smooth local display and synchronized with the server.
  - The competition passage is strictly hidden on the server until the competition officially starts.
  - Synchronized waiting lobby with countdown timer.
  - **Single Attempt Guarantee**: Disconnections or browser reloads do not create duplicate attempts or wipe progress—participants reconnect to their active attempt seamlessly.
  - **Tie Handling**: Exact ties produce a shared rank and joint winners (e.g. Rank 1, 1, 3). Winners are never selected randomly.
  - **Provisional vs. Final**: Shows live provisional leaderboards during the race, switching to frozen final rankings upon administrator finalization.

### 4. Administration Dashboard
- Create, edit, and cancel competitions before they start.
- Configure title, format, duration, difficulty, scheduled UTC start time, participant limit, and minimum accuracy threshold.
- Automatically generates unique, human-friendly 6-character join codes (e.g. `SPRINT`, `MORNING`).
- Manage the passage library (add new custom passages with difficulty ratings).
- Launch competitions manually or let scheduled start times trigger them.
- Finalize results and export comprehensive performance data to CSV.

---

## 📐 Scoring Rules

Scoring rules are strictly standardized across both solo practice and organized competitions:
1. **WPM** = `(correctly typed characters / 5) / elapsed minutes`
2. **Accuracy** = `(correct keystrokes / total scored keystrokes) * 100`
3. **Backspace Handling**: Backspace is a correction action, not a scored character keystroke. It does not increment total scored keystrokes.
4. **Incorrect Attempts**: Tracked every time an erroneous character is struck at an index, even if the user subsequently backspaces and fixes it.
5. **Edge Cases**: Cleanly handles empty inputs, zero elapsed seconds, punctuation, symbols, and unfinished passages.

---

## 📁 Project Structure

```
Speedoo/
├── app.py                  # Application factory, context processors, and error handlers
├── run.py                  # Local development entry point
├── config.py               # Application configuration and environment defaults
├── models.py               # SQLAlchemy database models (User, Passage, Competition, Attempt, Participant)
├── scoring.py              # Centralized scoring engine, event replay, and tie-breaking ranker
├── security.py             # RBAC decorators, input sanitizers, and validation helpers
├── init_db.py              # Database creation & sample data seeder
├── create_admin.py         # Secure CLI script to create administrator accounts
├── requirements.txt        # Python package dependencies
├── .env.example            # Example environment variables
├── .env                    # Local environment config
├── blueprints/             # Modular blueprint architecture
│   ├── auth.py             # Registration, login, logout
│   ├── practice.py         # Solo typing practice API and views
│   ├── competition.py      # Competition lobby, arena, and leaderboards
│   └── admin.py            # Admin dashboard, competition forms, CSV export
├── templates/              # HTML5 templates
│   ├── base.html           # Master layout with navbar and dynamic footer
│   ├── auth/               # Login & Registration views
│   ├── practice/           # Practice typing interface & results screen
│   ├── competitions/       # Join, lobby, arena, and leaderboard views
│   ├── admin/              # Admin dashboard, competition editor, passage creator
│   └── errors/             # 403, 404, 500 custom error pages
├── static/
│   ├── css/
│   │   └── style.css       # Clean, modern, dark-mode CSS styling
│   └── js/
│       └── engine.js       # Client typing engine, monotonic timer, and event sync
└── tests/                  # Automated test suite
    ├── test_scoring.py     # Unit tests for WPM, accuracy, event replay, and ties
    └── test_competition.py # Integration tests for deadlines, RBAC, single-attempt, and secrecy
```

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.10+ (tested with Python 3.10 through 3.15)
- pip

### 1. Clone & Set Up Virtual Environment (Optional but recommended)
```bash
git clone <repo-url> Speedoo
cd Speedoo
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
copy .env.example .env   # Windows
cp .env.example .env     # Linux/macOS
```

### 4. Initialize Database & Seed Demo Data
Run the initializer script to set up tables and load sample passages and demo competitions:
```bash
python init_db.py
```
This automatically seeds:
- 6 sample passages (Easy, Medium, Hard).
- A default administrator (`admin` / `AdminPassword123!`).
- Demo competitor accounts (`alice`, `bob`, `charlie` / `Password123!`).
- Sample competitions with join codes `SPRINT` and `MORNING`.

### 5. Create / Manage Administrators via CLI
To create a new custom administrator account or promote an existing user securely:
```bash
# Interactive mode:
python create_admin.py

# Non-interactive CLI flag mode:
python create_admin.py --username sysadmin --email sysadmin@speedoo.local --password MySecurePassword123!
```

### 6. Run the Application
```bash
python run.py
```
Open your browser and navigate to:
**`http://127.0.0.1:5000`**

---

## 🧪 Running Tests

Speedoo includes an automated test suite verifying scoring accuracy, tie handling, event replay, deadline enforcement, competition secrecy, and access control.

Run tests using Python's test runner:
```bash
python -m unittest discover tests
```

---

## 🛡️ Anti-Cheat & Supervision Notice

Speedoo implements server-side event sequence replay, keystroke validation, paste blocking, drag-and-drop restrictions, and suspicious activity anomaly detection (such as multi-character insertions or superhuman typing bursts).

> **Important Notice for Organizers:**
> While Speedoo validates every keystroke on the server and rejects client-fabricated scores, no web-based browser application can completely prevent external automation (such as hardware-level macro keyboards or headless browser drivers) without client OS-level lockdown software. For high-stakes, official competitive tournaments, we recommend conducting competitions in supervised computer labs or pairing Speedoo with live webcam / proctor supervision.

---

## 🔮 Future Enhancements & Extension Points

The architecture is deliberately modular to facilitate future upgrades:
1. **Multilingual Support (Malayalam, Hindi, Spanish, etc.)**:
   - *Unicode & Input Method Considerations*: Non-Latin scripts (such as Malayalam `മലയാളം`) utilize multi-byte UTF-8 grapheme clusters and Composition Events (`compositionstart`, `compositionupdate`, `compositionend`) via IMEs. The event processor in `scoring.py` should be configured to group composite character keystrokes into unified grapheme events using Python's `unicodedata` library (`unicodedata.normalize('NFD', ...)`).
2. **Real-time WebSockets**:
   - Replace the current lightweight polling mechanism with Flask-SocketIO or Redis Pub/Sub for sub-100ms multi-player live cursor ghosts.
3. **PostgreSQL Migration**:
   - Switch the `DATABASE_URL` in `.env` from SQLite to `postgresql://user:password@host:5432/speedoodb`. The SQLAlchemy models and transactional locking mechanisms are already database-agnostic.
4. **Tournament Brackets & Team Relays**:
   - Extend the `Competition` model with `round_number`, `parent_competition_id`, and `team_id` relations.
5. **Certificates & Progress Analytics**:
   - Automated PDF certificate generation for winners and user profile charts rendering WPM progression over time.
6. **Custom UI Themes**:
   - CSS variables in `style.css` make it straightforward to add user-selectable themes (e.g. Cyberpunk, Solarized, Paper, Monokai).

---

## 📄 License & Attribution

Speedoo is developed by **PazhaTholi**.  
© {{ current_year }} PazhaTholi. All rights reserved.

