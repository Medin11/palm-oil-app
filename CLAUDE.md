# Palm Oil Supply Chain Checker (working title)

## About this project
University course project (Supply Chain Digitalization & Sustainability + Startups & Innovative Entrepreneurship).
Deliverables due 31 January 2027: a working installer for macOS (and Windows if possible), a demo video (max. 5 min), and a pitch.

## The problem
From 30 December 2026 the EU Deforestation Regulation (EUDR) requires companies that import palm oil to prove it was
not produced on land deforested after 31 December 2020, and that it was produced legally.
Small and medium EU companies (food, cosmetics, specialty traders) cannot afford expensive compliance platforms.
In 2026, severe fires on Borneo and Sumatra, new plantation expansion and illegal plantations make this risk very real.

## What the app does
A desktop app that screens palm oil suppliers for three risk signals:
1. **Fire** – fire hotspots on or near supplier plots (NASA FIRMS data)
2. **Clearing** – forest loss since 2021 on plots that were forest on 31 Dec 2020
3. **Legality** – plots inside state forest area (kawasan hutan) or outside the supplier's concession

Main user flow (should take three clicks):
1. Drag a supplier file (CSV/Excel/GeoJSON) into the app
2. Click "Check suppliers"
3. See green / amber / red results on a map and list, then click "Export report" (PDF)

## MVP scope (build only this unless I say otherwise)
- Supplier, mill and plot register (drag-and-drop import + manual entry)
- If only a mill location is known: draw a 50 km sourcing radius and mark "plot data missing"
- Fire hotspot check
- Forest loss check
- Protected/state forest area overlap check
- Traffic-light dashboard + map
- PDF due diligence report export
- Offline demo data for Ketapang, West Kalimantan, with a "Load example data" button

Later / nice-to-have (do NOT build yet): supplier red-flag register, burn-then-plant detection, automated news monitoring.

## Tech stack
- Python 3
- pywebview for the desktop window, with the interface built in HTML/CSS/JavaScript
- Leaflet for the map (bundled locally, so the app works offline)
- SQLite for local storage (all data stays on the user's computer)
- Shapely + plain GeoJSON for geometry (avoid GDAL and other heavy libraries that are hard to package)
- A simple PDF library (e.g. reportlab) for the report
- PyInstaller to build the macOS app; Windows build later

## Design rules
- Apple-like: clean, calm, lots of white space, rounded cards, one main action per screen
- Slim left sidebar with: Overview, Suppliers, Map, Reports, Settings
- Green, nature-inspired palette (forest green accents, warm neutral backgrounds); red/amber/green are reserved for traffic-light meanings:
  risk status, and certification badges (RSPO + ISPO = green, one of them = amber, none = red). Use neutral grey for everything else (e.g. "Demo", "Plot data missing")
- Light and dark mode following the system setting
- English only
- Plain language in the interface (e.g. "Fires detected nearby", not technical terms); technical details behind a "Details" button
- Indonesian terms get a short English explanation, e.g. "HGU (land use permit)"
- Formats: 19 Oct 2026, hectares, km

## Data rules
- Demo data uses fictional company names on realistic coordinates. Never label real companies as risky.
- API keys (NASA FIRMS, Global Forest Watch) are entered on the Settings screen and stored locally, never hard-coded.
- The app must still work in offline demo mode if an API is unavailable.
- Add a Credits screen listing data sources.

## Honest claims
The app is a risk-screening tool, not a legal guarantee or certification. Avoid wording like "100% deforestation-free"
or "saves the rainforest". Satellite data has limits (haze, clouds, small clearings).

## How to work with me
- I am a beginner learning Claude Code and Python. Explain what you are doing in simple words.
- Before writing code for a new feature, show me a short plan and wait for my OK.
- Work in small steps: one feature at a time.
- After each step, tell me exactly how to run and test it on my Mac.
- When a step works, commit it with Git with a clear message.
- Keep the project folder tidy and explain any new file or folder you create.
