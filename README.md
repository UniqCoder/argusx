<div align="center">

# 🔱 A R G U S

### *Real-Time Blockchain Intelligence & Crypto Fraud Attribution System*

![SIH26183](https://img.shields.io/badge/SIH2026-SIH26183-4B32C3?style=for-the-badge&logo=sih&logoColor=white)
![MHA I4C](https://img.shields.io/badge/MHA-I4C%20Cyber%20Crime-FF3B5C?style=for-the-badge)
![Blockchain](https://img.shields.io/badge/Blockchain-Intelligence-00D4FF?style=for-the-badge&logo=ethereum&logoColor=white)
![Status](https://img.shields.io/badge/Status-✅%20All%20Phases%20Complete-00E676?style=for-the-badge)

![React](https://img.shields.io/badge/React_19-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-008CC1?style=for-the-badge&logo=neo4j&logoColor=white)
![Three.js](https://img.shields.io/badge/Three.js-000000?style=for-the-badge&logo=three.js&logoColor=white)

---

**Augmented Real-time Graph-based Unified Surveillance**

*Trace the money. Identify the exchange. Build the case. Stop the fraud — before the cash-out.*

</div>

---

## 📖 What is ARGUS?

> **ARGUS** is a **full-stack, real-time blockchain intelligence platform** built for India's **Ministry of Home Affairs (MHA) / Indian Cyber Crime Coordination Centre (I4C)** under Smart India Hackathon 2026.

When a citizen falls victim to cryptocurrency fraud — an investment scam, ransomware payment, or task-based fraud — the clock starts ticking. Stolen funds move through dozens of wallets, hop across chains via bridges, pass through mixers, and land at exchanges within minutes. **ARGUS gives law enforcement the ability to follow the money in real time.**

```
Victim Reports Fraud  →  ARGUS traces the wallet  →  Follows the fund flow
                              ↓                           ↓
                     Risk Analysis with            Multi-hop tracing across
                     explainable ML (XGBoost)      BTC, ETH, TRON, BSC
                              ↓                           ↓
                     Identifies the nearest          Generates court-ready
                     exchange / VASP                 evidence trail & reports
                              ↓                           ↓
                     💰 FREEZE THE FUNDS before cash-out 💰
```

---

## 🎯 Use Cases

| Scenario | How ARGUS Helps |
|----------|----------------|
| 🚨 **Investment Scam** | Victim reports a wallet → ARGUS traces fund flow through mixers and bridges → identifies Binance deposit → freeze request generated |
| 🔒 **Ransomware Payment** | BTC payment traced across 8 hops → nearest VASP identified → evidence package assembled for prosecution |
| 💸 **Task-Based USDT Fraud** | TRON/USDT trail across 6 wallets → cross-victim correlation links 7 complaints → network signal: HIGH |
| 🌉 **Cross-Chain Laundering** | ETH → TRON bridge interaction detected → Poly Bridge event correlated → destination wallet flagged |
| 📊 **Mass Fraud Operations** | 128 victims across 4 states → single wallet cluster identified → geographic spread mapped |
| ⚡ **Real-Time Deposit Watch** | Exchange monitoring detects incoming deposit → risk check runs in <200ms → alert fired |

---

## ✨ Features

### 🎨 Immersive 3D Landing Experience
> *Not your boring government dashboard.*

An interactive, scroll-driven 3D experience powered by **Three.js** and **React Three Fiber**. Watch 420 blockchain nodes morph through deep corridors, shell formations, chain clusters, and vast universes as you scroll. Animated particles trace transaction paths. A coin scene with glitch effects introduces the crisis — $12.4B stolen in crypto globally in 2024.

### 🔍 Wallet Tracing Engine
Paste any wallet address or transaction hash. Select the blockchain. Hit trace. ARGUS performs **multi-hop graph traversal** across on-chain data, automatically detecting:
- 📤 **Fan-out patterns** (layering)
- 🌉 **Bridge interactions** (cross-chain movement)
- 🌀 **Mixer proximity** (obfuscation)
- 🏦 **VASP attribution** (exchange identification)

### 📁 Investigation Workspace
A three-panel command center where investigators:
- **Left panel:** Case context, risk score, network signal strength
- **Center panel:** Live animated money trail with play/pause/speed/scrub controls
- **Right panel:** Intelligence inspector — click any node or edge for detailed evidence

### 🧠 Explainable Risk Intelligence
No black boxes. Every risk score is decomposed into **contributing signals**, each backed by verifiable data:
- Multiple victim complaints (+28 pts)
- Rapid-hop pattern (+18 pts)
- Cross-chain movement (+16 pts)
- Known high-risk cluster (+12 pts)
- Transaction velocity (+9 pts)

Score composition bar shows exactly how each factor contributes to the final risk rating.

### 🔗 Cross-Victim Correlation
The same wallet targeting multiple victims across states? ARGUS links them automatically:
- **Victim count** — unique people targeted
- **Complaint correlation** — NCRP complaint matching
- **Geographic spread** — state-by-state breakdown
- **Signal strength** — HIGH / MEDIUM / LOW confidence

### 📡 Network Signals
Live transaction and complaint network graphs with animated particle flows showing data moving between wallets, bridges, mixers, and exchanges.

### ⚠️ Live Alert Feed
Real-time operational intelligence timeline:
- 🔴 **CRITICAL** — Deposit alerts, VASP proximity
- 🟠 **HIGH** — Network signals, cross-victim links
- 🟡 **MEDIUM** — Cross-chain events, rapid-hop patterns
- ⚪ **INFO** — Trace updates, hop resolution

### 💰 Deposit Watch
**Stop the money before cash-out.** Enter a wallet, amount, and chain. ARGUS runs a 4-step verification:
1. Wallet Registry Check (NCRP database)
2. Risk Intelligence Score (XGBoost model)
3. Complaint Correlation
4. Network Signal Analysis

### 📜 Evidence Trail
Append-only chronological investigation log. Every event — from complaint receipt to VASP identification — is timestamped, sourced, and confidence-rated. Click any event for detailed supporting evidence.

### 📄 Court-Ready Reports
Generate forensic PDF reports with 10 sections: Case Details, Complaint Information, Fund Flow Summary, Hop-by-Hop Trace, Risk Analysis, VASP Attribution, Evidence Sources, Methodology, and more.

### 🔐 Role-Based Authentication
JWT-based auth with Supabase. Three roles:
- **Admin** — Full system access
- **Investigator** — Active case management
- **Compliance Viewer** — Read-only intelligence access

---

## 🛠️ Technology Stack

### Frontend

| Layer | Technology | Purpose |
|-------|-----------|---------|
| ⚛️ **Framework** | React 19 | Component architecture |
| 🧭 **Routing** | TanStack Router | File-based routing with auth guards |
| 📡 **Data Fetching** | TanStack React Query | Server state management |
| 🎨 **Styling** | Tailwind CSS 4 | Utility-first design system |
| 🧩 **UI Components** | Radix UI | Accessible headless components |
| 🎮 **3D Graphics** | Three.js + React Three Fiber + Drei | Immersive blockchain visualization |
| 🎬 **Animation** | GSAP | Scroll-driven animations |
| 📊 **Charts** | Recharts | Data visualization (crime stats, risk breakdown) |
| 📝 **Forms** | React Hook Form + Zod | Validated form handling |
| 🗃️ **State** | Zustand | Lightweight global state |
| 🔤 **Fonts** | Space Grotesk + IBM Plex Mono | Modern technical typography |
| 🔐 **Auth** | Supabase Auth | JWT-based authentication |

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| 🚀 **API Framework** | FastAPI (Python) | REST API with auto-docs |
| 🗄️ **Relational DB** | PostgreSQL 15 | Structured data (cases, complaints, wallets) |
| 🕸️ **Graph Database** | Neo4j 5 | Blockchain relationship traversal |
| ⚡ **Cache & Queue** | Redis 7 | Risk registry (<200ms p95), Celery broker |
| 🧠 **ML Model** | XGBoost + SHAP | Risk scoring (Test AUC-PR = 0.954) |
| 📊 **Training Data** | Elliptic++ Dataset | Labeled crypto transaction data |
| 🤖 **LLM** | Llama 3.2 3B (Ollama) | Named Entity Recognition from complaint text |
| 🔍 **NLP Fallback** | spaCy | Deterministic NER when LLM unavailable |
| 📦 **Task Queue** | Celery | Async blockchain tracing jobs |
| 🔗 **Blockchain APIs** | Etherscan, Trongrid, Blockchain.com | Multi-chain on-chain data |

### Infrastructure

| Service | Technology |
|---------|-----------|
| 🐳 **Containerization** | Docker Compose |
| 🔄 **Reverse Proxy** | Nginx (production) |
| 📝 **Specs** | OpenAPI 3.1 (`contracts/openapi.yaml`) |
| 🔒 **Auth** | JWT (FastAPI) + API Key (check-wallet endpoint) |

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React 19)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │
│  │ 3D Landing│ │Dashboard │ │Investigate│ │Evidence & Reports  │ │
│  │ (Three.js)│ │(Command) │ │(Trace/   │ │(Trail/PDF/Export)  │ │
│  │          │ │          │ │ Cases)   │ │                    │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬───────────┘ │
│       └─────────────┴────────────┴────────────────┘             │
│                          │ TanStack Router                       │
└──────────────────────────┼──────────────────────────────────────┘
                           │ REST API
┌──────────────────────────┼──────────────────────────────────────┐
│                    BACKEND (FastAPI)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │
│  │ Auth     │ │ Correlation│ │ Tracing  │ │ Risk Scoring       │ │
│  │ (JWT)   │ │ Engine    │ │ Engine   │ │ (XGBoost+SHAP)    │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬───────────┘ │
│       └─────────────┴────────────┴────────────────┘             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │
│  │ PostgreSQL│ │  Neo4j   │ │  Redis   │ │ Ollama (Llama 3.2)│ │
│  │ (Cases)  │ │ (Graphs) │ │(Registry)│ │ (NER Extraction)  │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Project Structure

```
argus/
├── src/                          # Frontend source
│   ├── components/
│   │   ├── auth/                 # Authentication overlays
│   │   ├── dashboard/            # Sidebar, TopBar, selectors
│   │   ├── landing/              # 3D hero, gallery, charts
│   │   ├── scene/                # Three.js scenes & particles
│   │   └── ui/                   # Shared UI components (Radix)
│   ├── hooks/                    # Custom React hooks
│   ├── lib/                      # API client, mock data, utilities
│   ├── routes/                   # File-based routes (TanStack)
│   │   ├── dashboard/            # 12 dashboard views
│   │   ├── index.tsx             # Landing page
│   │   └── __root.tsx            # Root layout
│   ├── store/                    # Zustand stores
│   └── styles.css                # Global styles
├── sih-backend/                  # Full backend stack
│   ├── backend/                  # FastAPI application
│   ├── contracts/                # OpenAPI spec + entity definitions
│   ├── infra/                    # Docker Compose configs
│   └── docs/                     # PRD, implementation plan
├── public/                       # Static assets
├── package.json                  # Dependencies
├── vite.config.ts                # Vite build config
└── tsconfig.json                 # TypeScript config
```

---

## 🚀 Getting Started

### Prerequisites

- **Node.js** 20+
- **Docker Desktop** (for backend)
- **Git**

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/UniqCoder/argus.git
cd argus
```

### 2️⃣ Install Frontend Dependencies

```bash
npm install
```

### 3️⃣ Start the Frontend Development Server

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### 4️⃣ Start the Backend (Optional)

```bash
cd sih-backend
cp backend/.env.example backend/.env
cd infra
docker-compose up --build
```

This starts:
| Service | Port | Purpose |
|---------|------|---------|
| FastAPI Backend | `8000` | REST API + Swagger UI |
| PostgreSQL | `5432` | Relational database |
| Neo4j | `7474` | Graph database |
| Redis | `6379` | Risk registry + cache |

### 5️⃣ Verify the Backend

```bash
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0","services":{...}}
```

---

## 📋 Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server |
| `npm run build` | Production build |
| `npm run build:dev` | Development build |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |
| `npm run format` | Format with Prettier |

---

## 📊 API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/auth/login` | — | Login & get JWT tokens |
| `POST` | `/api/v1/auth/refresh` | JWT | Refresh access token |
| `GET` | `/health` | — | System health check |
| `POST` | `/api/v1/wallets/trace` | JWT | Multi-hop wallet trace |
| `GET` | `/api/v1/wallets/:id/risk` | JWT | Risk score + SHAP evidence |
| `POST` | `/api/v1/correlate` | JWT | Cross-victim correlation |
| `GET` | `/api/v1/cases` | JWT | List investigation cases |
| `POST` | `/api/v1/cases` | JWT | Create new case |
| `GET` | `/api/v1/cases/:id/report` | JWT | Generate PDF report |
| `POST` | `/api/v1/check-wallet` | API Key | Real-time wallet check (<200ms) |

---

## 🧪 Backend Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 0 — Scaffolding | ✅ Done | Contracts, FastAPI skeleton, Docker, JWT stubs |
| 1 — Correlation | ✅ Done | Complaint ingestion + Cross-Victim Correlation (NCRP) |
| 2 — Registry | ✅ Done | Redis registry + /check-wallet chokepoint (<200ms p95) |
| 3 — Tracing | ✅ Done | Multi-chain blockchain tracing (BTC, ETH, TRON) |
| 4 — ML Risk | ✅ Done | XGBoost + SHAP evidence (Elliptic++ dataset, AUC-PR=0.954) |
| 5 — Cases | ✅ Done | Case management state machine + Forensic PDF reports |
| 6 — LLM NER | ✅ Done | Air-gapped Llama 3.2 3B + spaCy fallback |
| 7 — Hardening | ✅ Done | Integration hardening, CORS, audit logging |

---

## 🎨 Visual Showcase

The landing page features a **scroll-driven 3D experience** with:

- 🌀 **420 animated blockchain nodes** forming dynamic layouts
- 🔗 **520 interconnected links** with flowing particles
- 🪙 **3D coin scene** with perspective camera and glitch effects
- 📈 **Interactive charts** (crime by year, fraud typology, chain distribution, frozen funds)
- 🎭 **Story overlay** with progressive reveal sections
- 🧲 **Magnetic cursor button** with magnetic hover physics

---

## 🔒 Security

- **JWT Authentication** with refresh tokens via Supabase
- **Role-Based Access Control** (Admin / Investigator / Compliance Viewer)
- **API Key authentication** for the /check-wallet chokepoint
- **FIR narrative data** never leaves the local network (air-gapped Ollama)
- **Environment variables** for all secrets (never committed)

> ⚠️ **Important:** Override `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and `NEO4J_PASSWORD` before any non-dev deployment.

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project was built for **Smart India Hackathon 2026** — SIH26183, MHA/I4C, Blockchain & Cybersecurity track.

---

## 🙏 Acknowledgments

- **Smart India Hackathon 2026** — MHA/I4C for the problem statement
- **Elliptic++ Dataset** — For ML model training
- **Etherscan, Trongrid, Arkham Intel, Forta Network** — Blockchain intelligence sources
- **NCRP Database** — National Cyber Crime Reporting Portal integration

---

<div align="center">

**Built with 💜 to protect citizens from crypto fraud**

*ARGUS — Because every stolen rupee deserves to be traced.*

![Made with React](https://img.shields.io/badge/Made_with-React_19-61DAFB?style=flat-square)
![Made with Three.js](https://img.shields.io/badge/Made_with-Three.js-000000?style=flat-square)
![Made with FastAPI](https://img.shields.io/badge/Made_with-FastAPI-009688?style=flat-square)
![Made with ❤️ for India](https://img.shields.io/badge/Made_with_%E2%9D%A4%EF%B8%8F_for-India-FF9933?style=flat-square)

</div>
