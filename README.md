# IncidentIQ — AI-Powered Incident Knowledge Base & Autonomous Resolution Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-6.0-646CFF.svg)](https://vitejs.dev/)
[![Evaluation Grade](https://img.shields.io/badge/Evaluation-EXCELLENT_(MRR_1.00)-10b981.svg)](#evaluation-framework--metrics)

IncidentIQ is an enterprise-grade AI knowledge base assistant and autonomous multi-agent incident management platform designed for Site Reliability Engineers (SREs), DevOps squads, and IT Service Desk teams. It ingests and indexes incidents from the **official Google Sheet Knowledge Base**, performing hybrid semantic retrieval, automated classification, root cause analysis (RCA), grounded troubleshooting guidance, and security guardrail verification.

See [the architecture and retrieval notes](docs/architecture-and-retrieval.md) for the current project layout, local indexing and fallback design, feedback/escalation persistence, and evaluation approach.

---

## 🚀 Key Features

- 🔍 **Hybrid Dense & Lexical Semantic Retrieval**: Combines character and word n-gram TF-IDF vectorization with BM25-style lexical overlap and exact metadata inverted indices.
- 🤖 **7-Stage Multi-Agent Orchestration**:
  1. `Input Guardrail Agent`: Prompt injection defense and automatic PII/credential redaction.
  2. `Triage & SLA Agent`: Automatic categorization, severity (P1–P4), squad routing, and SLA deadline estimation.
  3. `Hybrid Retrieval Agent`: Sub-50ms search over indexed historical incidents.
  4. `Root Cause Analysis (RCA) Agent`: 5-Whys pattern extraction and differential diagnostics.
  5. `Resolution Synthesis Agent`: Action plan generation with verified historical resolution steps.
  6. `Safety Auditor Agent`: Prevents destructive commands (`rm -rf /`, `DROP TABLE`) and scores Groundedness.
  7. `Tier Handoff Agent`: Automatically compiles L1/L2/L3 escalation packets with diagnostic logs.
- 📊 **Interactive Live Evaluation Benchmark Suite**: Built-in benchmark harness computing **Precision@1**, **Hit Rate@3**, **Hit Rate@5**, **Mean Reciprocal Rank (MRR)**, **MAP**, and **Latency**.
- 🛡️ **Comprehensive Guardrails**: Real-time screening for prompt injections, credential leakage, destructive bash/SQL commands, and hallucination scoring.
- 🔐 **Role-Based Authentication & Authorization**:
  - Secure registration and login backed by PBKDF2-HMAC-SHA256 password hashing and signed tokens.
  - Granular roles: `Admin` (audit logs, evaluation triggers, incident creation, LLM settings) and `User` (search, resolution, feedback).
  - Pre-seeded 1-click test accounts (`admin@incidentiq.io` / `Admin@123` & `engineer@incidentiq.io` / `User@123`).
- 🌐 **Multi-Provider LLM Integration**: Seamless support for **OpenRouter** (`OPENROUTER_API_KEY` or `OPENROUTE_API_KEY`), **Google Gemini**, **OpenAI**, and an offline high-fidelity **Deterministic Domain Engine**.
- ⚡ **Modern Dark-Mode Glassmorphic Interface**: Built with React, Vite, Lucide Icons, and custom CSS design tokens.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Incident Ingestion & Indexing"]
        A[ServiceNow ITSM Event Log CSV] --> B[Data Normalization & Cleaning]
        S[Curated KB & Custom Tickets] --> B
        B --> C[(Indexed Incident Knowledge Base)]
        C --> D1[Word N-Gram TF-IDF Matrix]
        C --> D2[Char N-Gram TF-IDF Matrix]
        C --> D3[Metadata Inverted Indices]
    end

    subgraph Client["2. User Experience & Auth Layer"]
        U[Support Engineer / Admin] --> UI[IncidentIQ React Glassmorphism Dashboard]
        UI --> Auth[User Auth & Token Verification]
        Auth --> DB[(SQLite: Users, Audit Logs, Feedback)]
    end

    subgraph Backend["3. Multi-Agent Orchestrator & Guardrails"]
        UI --> API[FastAPI Microservice]
        API --> G_IN[Agent 1: Input Guardrail & PII Filter]
        G_IN --> T_AGENT[Agent 2: Automated Triage & SLA Predictor]
        T_AGENT --> R_AGENT[Agent 3: Hybrid Retrieval & Filter Engine]
        D1 --> R_AGENT
        D2 --> R_AGENT
        D3 --> R_AGENT
        R_AGENT --> RCA_AGENT[Agent 4: Root Cause 5-Whys Analyzer]
        RCA_AGENT --> LLM_AGENT[Agent 5: Resolution Synthesizer]
        LLM_AGENT --> Providers[OpenRouter / Gemini / OpenAI / Deterministic Engine]
        Providers --> LLM_AGENT
        LLM_AGENT --> G_OUT[Agent 6: Safety Auditor & Grounding Guardrail]
        G_OUT --> ESC_AGENT[Agent 7: Tier Handoff & Escalation Agent]
    end

    subgraph Evaluation["4. Benchmark & Quality Assurance"]
        BENCH[Ground-Truth Benchmark Suite] --> EVAL_RUNNER[Live Evaluation Engine]
        EVAL_RUNNER --> METRICS[MRR, Precision@1, HitRate@3, MAP, Latency]
        METRICS --> EVAL_UI[Interactive Evaluation Studio]
    end

    ESC_AGENT --> UI
    UI --> FB[Feedback Voting & Rating]
    FB --> DB
```

---

## 📈 Evaluation Framework & Metrics

IncidentIQ includes a rigorous evaluation benchmark suite based on information retrieval standards:

| Evaluation Metric | Score Achieved | Benchmark Standard | Status |
| :--- | :--- | :--- | :--- |
| **Precision @ 1 (Top-1 Match)** | **100.00%** | > 80.0% | ✅ PASS |
| **Hit Rate @ Top-3** | **100.00%** | > 85.0% | ✅ PASS |
| **Hit Rate @ Top-5** | **100.00%** | > 90.0% | ✅ PASS |
| **Mean Reciprocal Rank (MRR)** | **1.0000** | > 0.850 | ✅ PASS |
| **Mean Average Precision (MAP)** | **0.8243** | > 0.500 | ✅ PASS |
| **Average Query Latency** | **78.66 ms** | < 100 ms | ✅ PASS |
| **Overall Quality Rating** | **EXCELLENT** | — | Seven-case benchmark |

### Running the Evaluation Suite
```bash
# Via Python CLI
python scripts/evaluate.py

# Or run pytest
pytest
```
*You can also run the evaluation suite interactively from the UI under the **Live Evaluation Suite** tab.*

---

## 📦 Project Structure

```
Incident-2/
├── app/
│   ├── __init__.py
│   ├── config.py           # Environment & security config
│   ├── store.py            # SQLite storage (Users, Feedback, Audit, Custom Incidents)
│   ├── auth.py             # User registration, login, PBKDF2 hashing, JWT verification
│   ├── data.py             # Incident loader, schema normalizer, deduplicator
│   ├── retrieval.py        # Hybrid Dense TF-IDF & Lexical BM25 search engine
│   ├── intelligence.py     # Rule-based triage classifier & SLA estimator
│   ├── agents.py           # 7-Stage Multi-Agent Orchestrator
│   ├── guardrails.py       # Prompt injection, PII masking, destructive command defense
│   ├── llm.py              # OpenRouter, Gemini, OpenAI, and Deterministic Synthesizer
│   ├── evaluation.py       # Benchmark test suite and evaluation runner
│   └── main.py             # FastAPI REST Microservice endpoints
├── data/
│   ├── incidents.csv                  # 2,500 records: 150 source and 2,350 synthetic examples
│   └── dataset_profile.md             # Dataset provenance, profile & column mapping
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # Full-featured interactive React dashboard
│   │   ├── main.jsx        # Entry point
│   │   └── styles.css      # Dark-mode glassmorphic design system
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── evaluate.py         # CLI Evaluation Benchmark Runner
│   └── prepare_itsm_dataset.py # Data preprocessing pipeline
├── tests/
│   ├── test_smoke.py
│   ├── test_itsm_dataset.py
│   └── test_advanced_features.py
├── architecture.mmd        # Mermaid system architecture diagram
├── evaluation_results.json # Saved benchmark results
├── requirements.txt        # Python backend dependencies
└── README.md
```

---

## 🛠️ Quick Start & Setup

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm**

### 2. Backend Setup
```bash
# Clone or navigate to the directory
cd Incident-2

# Install Python dependencies
pip install -r requirements.txt

# Start FastAPI Backend Server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*Backend API docs available at: `http://localhost:8000/docs`*

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies (if not already installed)
npm install

# Start Vite Development Server
npm run dev
```
*Frontend UI accessible at: `http://localhost:5173`*

---

## 🔑 Default Credentials (Pre-Seeded)

The system automatically seeds two ready-to-use accounts on startup:

| Role | Email | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **Admin SRE** | `admin@incidentiq.io` | `Admin@123` | Full Access (Audit Logs, Benchmark Evaluator, Log Incident, LLM Settings) |
| **Support Engineer** | `engineer@incidentiq.io` | `User@123` | Search, Resolution Studio, Feedback, Knowledge Base Explorer |

*New users can also register freely directly through the **Register** tab.*

---

## 📡 API Reference Overview

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service health and indexed incident count | Public |
| `GET` | `/metadata` | Available filter values (priorities, states, categories) | Public |
| `POST` | `/api/auth/register` | Register new user account | Public |
| `POST` | `/api/auth/login` | Authenticate user & return signed token | Public |
| `GET` | `/api/auth/me` | Get current authenticated user profile | User |
| `POST` | `/api/search` | Hybrid semantic search with metadata filters | Optional |
| `POST` | `/api/resolve` | Multi-Agent incident resolution & RCA pipeline | Optional |
| `POST` | `/api/evaluate/run` | Run retrieval & quality evaluation benchmark | Public |
| `GET` | `/api/incidents` | Paginated incident catalog | Public |
| `POST` | `/api/incidents/create` | Log and auto-index new incident record | User |
| `GET` | `/api/analytics` | Incident distribution and resolution KPIs | Public |
| `POST` | `/api/feedback` | Submit helpfulness rating (1–5) | Optional |
| `GET` | `/api/audit-logs` | Security and guardrail audit history | Admin Only |
| `POST` | `/api/settings` | Update OpenRouter / Gemini API credentials | Admin Only |
