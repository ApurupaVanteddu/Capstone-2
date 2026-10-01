# IncidentIQ architecture and retrieval

## Application layout

- `frontend/` contains the React and Vite single page application. Client routes use browser history (`/user`, `/admin/users`, and related paths); browser back and forward update the rendered view. All page data is fetched from the FastAPI API.
- `app/main.py` defines the HTTP API and access dependencies.
- `app/auth.py` owns password hashing, signed session tokens, and role checks.
- `app/store.py` owns SQLite schema setup and persistence for accounts, feedback, escalations, settings, history, notifications, and audit logs.
- `app/data.py` normalizes the supplied incident dataset and combines it with administrator contributed incidents.
- `app/retrieval.py` builds local lexical and semantic indexes.
- `app/intelligence.py`, `app/agents.py`, `app/llm.py`, and `app/guardrails.py` implement triage, resolution orchestration, provider selection, and input/output safety checks.
- `app/evaluation.py` and `scripts/evaluate.py` implement the repeatable retrieval benchmark.

## Incident preparation and indexing

The source file is `data/incidents.csv`. At startup, records are normalized into the common incident fields (identifier, description, resolution, priority, category, state, affected configuration item, and assignment). The retrieval text joins the incident description and resolution with useful metadata. Administrator-created records in SQLite are merged into the same collection. Creating, updating, or deleting an administrator-managed record rebuilds the in-memory index.

The index is entirely local and uses scikit-learn. Word n-gram TF-IDF, character n-gram TF-IDF, and token overlap provide lexical matching. A TruncatedSVD projection of the word TF-IDF matrix provides corpus-local latent semantic vectors, requiring no hosted embedding API or model download. Results are filtered by metadata before ranking and reranked with a weighted combination of word similarity (0.42), character similarity (0.18), token Jaccard overlap (0.18), and latent semantic similarity (0.22). Returned scores are used for ordering and confidence context; they are not calibrated probabilities.

## Resolution, providers, and fallback

The resolution endpoint classifies and retrieves incident records before synthesizing guidance grounded in those records. OpenRouter, Gemini, and OpenAI providers can be configured by an administrator and independently disabled to exercise fallback behavior. When no provider is configured, disabled, or reachable, resolution synthesis uses the local deterministic domain engine. The instant-summary route returns the matched local incident evidence when no hosted model is enabled, instead of failing due to missing credentials. The retrieval and API therefore remain usable offline.

## Authorization, feedback, and escalation

Public registration creates user accounts. Administrator privileges are assigned by an existing administrator through user management. Admin APIs enforce the signed session role on the server. Feedback submissions require authentication and are stored with the submitting account and referenced incident; administrators can review all submissions while users can retrieve their own. Escalations are stored with the requester, source and target support tier, reason, diagnostic notes, timestamp, and status. Users see their own handoffs and administrators can inspect the complete escalation set.

## Evaluation

`scripts/evaluate.py` runs the representative retrieval cases in `app/evaluation.py` and reports Precision@1, Hit Rate@3/5, MRR, MAP, and query latency. Results depend on the current dataset and local index implementation; regenerate results after replacing or materially editing the incident corpus.

On 2026-09-30, the seven-case benchmark against the supplied 2,500 incident rows measured Precision@1 **100%**, Hit Rate@3 **100%**, Hit Rate@5 **100%**, MRR **1.0000**, MAP **0.8243**, and average query latency **78.66 ms** (grade: **EXCELLENT**). Relevance judgments include four additional IDs after verifying they duplicate the symptom and resolution of an already relevant record (`INC-5100` through `INC-5103`); this prevents equivalent historical fixes from being counted as retrieval failures. Inspect `evaluation_results.json` for each retrieved list and judged relevant IDs. Treat this as a small representative benchmark, not a production quality guarantee.
