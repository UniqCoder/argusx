# SETUP.md — Running Unigraph Locally

For anyone cloning this repo to work on the frontend, or to run the full stack locally. Read `docs/PRD.md` first for what the system actually does — this file is just "how do I get it running on my machine."

## 1. Prerequisites

- Docker + Docker Compose
- Git
- (Only if you're running Phase 6 / FIR NER) Ollama — see step 4

## 2. Clone and start the core stack

```bash
git clone <repo-url>
cd unigraph-backend
docker-compose up
```

This starts Postgres, Neo4j, Redis, and the FastAPI backend. Confirm it worked:

- `http://localhost:8000/health` → should return 200
- `http://localhost:8000/docs` → interactive API docs (this is also the live source of truth for every request/response shape — check here before building against an endpoint, not just `contracts/openapi.yaml`, since the code is what actually runs)

## 3. Frontend integration notes

- Build against `contracts/openapi.yaml` — if anything there looks incomplete or wrong versus what `/docs` actually returns, flag it rather than guessing; the contract is meant to stay in sync with the running code but can lag during active backend work.
- No auth complexity to worry about yet for most routes beyond whatever `/docs` shows — ask if a route's auth requirement isn't obvious.
- `/check-wallet` is API-key auth (not JWT) since it's meant for an external VASP caller, not a logged-in user — don't wire this one the same way as user-facing routes.

## 4. Optional: local LLM for FIR entity extraction (Phase 6, stretch feature)

This is **not required** to run or build against the rest of the system — if it's skipped, the complaint-detail response just won't include LLM-extracted entities (spaCy-only fallback still works). Only set this up if you're specifically working on that feature.

**Before installing anything, check your own machine's capability:**

```bash
nvidia-smi   # check available GPU and VRAM (Linux/Windows with NVIDIA GPU)
```

| Your available VRAM                      | Recommended model             | Notes                                                                                                          |
| ---------------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
| ~16GB+                                   | `llama3:8b`                   | Full quality, matches original PRD spec                                                                        |
| ~6-8GB                                   | `llama3:8b` (4-bit quantized) | Should fit, verify actual usage                                                                                |
| ~2-4GB (e.g. RTX 2050, laptop GPUs)      | `llama3.2:3b`                 | **This is what the current codebase is configured for**                                                        |
| No usable GPU / integrated graphics only | Skip Ollama entirely          | CPU-only inference is too slow (20-35s per FIR) to be usable — spaCy-only extraction is the practical fallback |

**Right now, the code expects `llama3.2:3b` specifically** — that's what was tested and wired into `nlp/` on the current dev machine (RTX 2050, ~4GB VRAM). If your machine can run something bigger, you're welcome to try swapping the model name in the Ollama config, but confirm with Rehan before changing it in a way others will pull, since the extraction prompt was tuned against this specific model's output format.

Install:

```bash
ollama pull llama3.2:3b
```

## 5. Reporting issues

If a contract shape doesn't match what the backend actually returns, or an endpoint behaves unexpectedly, note it — don't silently work around it on the frontend side, since that tends to hide the actual bug until much later.
