# UCSB Basketball Live Analytics Toolkit

A real-time basketball analytics dashboard built for **UC Santa Barbara Men's Basketball broadcasters, commentators, and producers**. It pulls live play-by-play, 2026–27 season stats, shot charts, and recent games from ESPN so broadcast teams can quickly spot scoring runs, player impact (PIE), hot/cold streaks, and matchup trends during live games without hunting through stat sheets.

The app consists of a **Python HTTP API** (`apps/api`, port `8000`) and a **React + Vite dashboard** (`apps/web`, port `5173`).

---

## Requirements & Packages

### System Requirements
- **Python** `3.9+`
- **Node.js** `18+` and **npm**

### Python Packages (`requirements.txt`)
- `requests >= 2.31.0`
- `beautifulsoup4 >= 4.12.0`
- `pdfplumber >= 0.11.0`
- `pandas >= 3.0.3`

### Frontend Packages (`apps/web/package.json`)
- `react` `^18.3.1` / `react-dom` `^18.3.1`
- `vite` `^5.4.11` / `@vitejs/plugin-react` `^4.3.4`
- `recharts` `^3.8.1`
- `d3` `^7.9.0`
- `react-resizable-panels` `^2.1.7`

---

## How to Run on Windows

From the repository root in **Command Prompt** or **PowerShell**:

1. **First-time setup** (creates `.venv`, installs Python & npm packages, creates `.env`):
   ```powershell
   npm run setup
   ```

2. **Start both servers**:
   ```powershell
   npm run dev
   ```
   *(Or run separately: `npm run dev:api` and `npm run dev:web`.)*

3. Open **`http://localhost:5173`** in your browser.

---

## How to Run on macOS (and Linux)

> Root `package.json` uses Windows `.bat` scripts, so on macOS/Linux run the `.sh` scripts in `scripts/`.

From the repository root in **Terminal**:

1. **First-time setup**:
   ```bash
   bash scripts/ensure-python.sh
   bash scripts/ensure-web.sh
   cp -n .env.example .env
   ```

2. **Start both servers**:
   ```bash
   bash scripts/dev.sh
   ```
   *(Or run separately in two terminals: `bash scripts/dev-api.sh` and `bash scripts/dev-web.sh`.)*

3. Open **`http://localhost:5173`** in your browser. Press `Ctrl+C` to stop.
