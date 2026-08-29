# ml.md — Unigraph Backend: Dataset, Training & Testing

This supersedes the dataset table in `datasets-and-ml.md` — deliberately narrowed to **one** dataset for training/evaluation so the feature schema stays consistent end to end. Mixing multiple dataset sources with different columns is the most common cause of train/inference feature mismatch — so don't.

---

## The one dataset: Elliptic++ (Actors / Wallets Dataset)

This is a direct match for "wallet risk scoring" (not just transaction classification) — ~822K labeled Bitcoin wallet addresses (`illicit` / `licit` / `unknown`), with per-wallet features (in/out-degree, transaction counts, volume, activity window, etc.) plus wallet–wallet and wallet–transaction edge lists.

**Where:** `github.com/git-disl/EllipticPlusPlus`, folder `Actors Dataset/`
**Files you need:** `wallets_features.csv`, `wallets_classes.csv`, `AddrAddr_edgelist.csv`, `AddrTx_edgelist.csv`, `TxAddr_edgelist.csv`

**How to get it:**

1. `git clone https://github.com/git-disl/EllipticPlusPlus` (or download the `Actors Dataset/` folder directly from the GitHub web UI — no login required).
2. Open `Elliptic++_Actors_Classification.ipynb` in that folder once before writing your own loader — it shows the exact column names and order. Match your feature-engineering code to that layout, don't rename or reorder.
3. Load `wallets_features.csv` + `wallets_classes.csv`, join on `address`.

**Do not also pull the original Kaggle "Elliptic Data Set."** That's the transaction-only predecessor (166 anonymized columns, no wallet-level features) — a different schema entirely. Bringing it in alongside Elliptic++ is exactly how you'd get mismatched/missing columns.

---

## Testing — comes from the same dataset, no second one needed

- **Split by time step, not randomly.** Elliptic++ has ~49 discrete time steps. Train on roughly the first 34, hold out the rest as your test set. This also doubles as your drift check, so there's nothing extra to download for that.
- **Metrics, in priority order:** AUC-PR (primary — illicit wallets are the minority class) → precision/recall at your deployed threshold → false-positive rate at that threshold (target < 1%) → AUC-ROC (secondary) → calibration/reliability curve (the score drives allow/hold/block, not just ranking).
- **The actual feature-mismatch guard:** before every training run, assert that the columns your live feature pipeline computes for a wallet (from your own explorer/graph data at inference time) match `wallets_features.csv`'s schema exactly — same names, same order, same units. A five-line assertion, run every time — this is what prevents the mismatch, not the choice of dataset.

---

## Optional second source — sanity check only, never for training

If you want one more signal beyond the held-out split: pull a handful of addresses from the **OFAC SDN sanctions list** (public, treasury.gov) and run them through your already-trained pipeline — just to confirm known-bad addresses get flagged. Don't import OFAC's data as training rows or extra columns; it never touches your feature schema, so it can't reintroduce the mismatch problem.

---

## Step-by-step, start to finish

1. Clone/download the Elliptic++ `Actors Dataset/` folder.
2. Join `wallets_features.csv` + `wallets_classes.csv` on `address`.
3. Sort by time step, split ~34/15 train/test.
4. Train the XGBoost/LightGBM baseline against that schema.
5. Add the feature-pipeline assertion before wiring the model into `GET /api/v1/wallets/{address}/risk`.
6. (Optional) Spot-check a few OFAC SDN addresses through the trained pipeline as a sanity pass — not a formal benchmark.

---

## Phase 6 Local LLM: Llama-3.2-3B-Instruct (Air-Gapped Ollama)

- **Model:** `llama3.2:3b` (~2.0 GB 4-bit quantized) running locally via Ollama (`http://localhost:11434`).
- **Hardware Rationale:** Fits completely inside 4 GB GPU VRAM (NVIDIA RTX 2050), delivering sub-1.5s per-FIR extraction latency. Full Llama-3-8B requires ~6GB VRAM and is too slow on CPU (~20-35s).
- **Air-Gap Guarantee:** FIR/complaint narrative text is processed strictly on the local Ollama instance without external outbound network calls.
- **Fallback:** Deterministic spaCy/regex entity extraction when Ollama is unavailable or JSON parsing fails.
