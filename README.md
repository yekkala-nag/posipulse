# 🌱 PosiPulse — Verified Constructive News Platform
### English + 15 Indian Languages • Multi-Platform (Web, iOS, Android)

PosiPulse is a multi-agent constructive news application that digests articles from many publishers across **English and 15 Indian languages** and delivers **only positive outcomes** (breakthroughs, solutions, community wins, recoveries).

---

## ⚡ Quick Start: Running Locally

### Option 1: Using the Local Runner Script (Recommended)
```bash
./run_local.sh
```
The script automatically activates the virtual environment, installs any missing dependencies, and boots the FastAPI server.

- **Web Reader UI**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **OpenAPI Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Prometheus Metrics**: [http://127.0.0.1:8000/metrics?format=prometheus](http://127.0.0.1:8000/metrics?format=prometheus)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### Option 2: Using Makefile
```bash
make install   # Creates .venv and installs requirements
make run       # Launches local development server
make test      # Runs all 64 automated test suites
```

### Option 3: Manual Startup
```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🚀 Deploying to Vercel

PosiPulse is configured for 1-click deployment on Vercel Serverless Functions.

### Step 1: Install Vercel CLI (if not already installed)
```bash
npm install -g vercel
```

### Step 2: Deploy
From the repository root directory, run:
```bash
vercel
```
For production release:
```bash
vercel --prod
```

### How Vercel Configuration Works
- [vercel.json](file:///Users/nyakkala/Documents/GitHub/posipulse/vercel.json): Routes all incoming traffic to `api/index.py` using `@vercel/python`.
- [api/index.py](file:///Users/nyakkala/Documents/GitHub/posipulse/api/index.py): Serverless ASGI bridge that exports the FastAPI gateway.
- [requirements.txt](file:///Users/nyakkala/Documents/GitHub/posipulse/requirements.txt): Pinned runtime dependencies automatically installed by Vercel's build worker.
- [.vercelignore](file:///Users/nyakkala/Documents/GitHub/posipulse/.vercelignore): Excludes unnecessary files (`.venv/`, `tests/`, etc.) keeping lambda bundle sizes under 15MB.

---

## 📱 Mobile App (iOS & Android)

The cross-platform React Native / Expo mobile app is located in `src/mobile`:
```bash
cd src/mobile
npm install
npx expo start
```
Native platform code:
- **iOS**: SwiftUI reference view at `src/mobile/ios/PosiPulse/ContentView.swift` with `SFSafariViewController` and RTL layout.
- **Android**: Jetpack Compose reference view at `src/mobile/android/app/src/main/java/com/posipulse/MainActivity.kt` with `CustomTabsIntent`.

---

## 🏷️ Controlled News Category Taxonomy (v1)

PosiPulse organizes constructive news according to the controlled taxonomy specified in [ADR 0006](file:///Users/nyakkala/Documents/GitHub/posipulse/docs/adr/0006-controlled-news-category-taxonomy.md) and [v1.json](file:///Users/nyakkala/Documents/GitHub/posipulse/config/taxonomy/v1.json):
- **13 Visible Launch Categories**: Agriculture, Science & Tech, Education & Skills, Environment & Climate, Sports, Society & Community, Arts & Culture, Lifestyle & Travel, Economy & Business, Health & Wellness, Infrastructure & Transport, Entertainment & Media, World & Diplomacy.
- **5 Hidden Reserved Categories (Option A Policy)**: Governance, Law & Justice, Religion, Defence, Disaster. Articles falling into these categories are held from public distribution.
- **IPTC Media Topics 2024.1 Compliance**: Full crosswalk with standard QCodes.
- **16 Languages**: Complete human-localized display names across English and 15 Indian languages.

---

## 🧪 Running Tests
```bash
.venv/bin/python -m pytest -v
```
Runs all 99 test cases covering:
- Legal non-retention invariants (raw publisher body is never stored in DB or API)
- Controlled Category Taxonomy v1 & Option A holding policies
- RSS parser tolerance, timeout retries, and exponential backoff
- 16-language golden datasets & quality gate verifications
- Bi-directional RTL layout for Urdu
- Dynamic substance length band meters
- DPDP Act 2023 delisting workflows and database audit
- Vercel serverless entrypoint and configuration schema

