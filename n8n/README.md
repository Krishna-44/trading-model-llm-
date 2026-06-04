# AIFOS — Video → Strategy pipeline (n8n optional)

> **Note:** AIFOS now processes the queue **natively** — when you paste a link it fetches
> the transcript, extracts the strategy on-device (your Gemini/LLM if reachable, else a
> keyword reader), maps it to a tested template and backtests it. **You do not need n8n.**
> This workflow is an **optional** alternate processor (e.g. to run extraction on a
> separate box, or to use a hosted LLM via n8n). The table↔n8n contract below still works.

The AIFOS dashboard has a **Video → Strategy** table. You paste a link → it becomes a
queued row. n8n can be wired **to that table**: it polls the queue, extracts the strategy,
and writes the result back to the same row.

```
Dashboard table  ──(paste link)──▶  row: queued
        ▲                                  │
        │                          n8n polls /videos/queued  (claims it → processing)
        │                                  │
        │                          transcript ──▶ LLM (structured JSON)
        │                                  │
        └──(writes result back)── POST /videos/{id}/result ──▶ row: done
                                           │
                          AIFOS ingests → maps to a tested template → backtests
                          → strategy appears in the Marketplace "Extracted" inbox (review)
```

This is **AI-assisted extraction & validation**, not auto-profit. Nothing is deployed
automatically — the extracted strategy waits in the review inbox, and the go-live
readiness gates still stand before any real money.

## The table ↔ n8n contract (already live in AIFOS)
| Method | Endpoint | Who calls it |
|---|---|---|
| `POST` | `/api/strategies/videos` `{url}` | dashboard, when you paste a link |
| `GET`  | `/api/strategies/videos` | dashboard, to render the table |
| `GET`  | `/api/strategies/videos/queued?limit=5` | **n8n** — claims queued rows (→ processing) |
| `POST` | `/api/strategies/videos/{id}/result` | **n8n** — writes back `{…strategy json}` or `{error}` |

`/queued` is claim-on-read: it flips the rows it returns to `processing`, so the same
link is never processed twice.

## Import & configure
1. n8n → **Workflows → Import from File** → `youtube-strategy-extraction.json`.
2. **Extract via LLM** node → set your LLM key (`Authorization: Bearer …`). Any
   OpenAI-compatible endpoint works (OpenAI, Groq, local Ollama) — swap the URL.
3. **Get transcript ⚙️ configure** node → this is the one piece you must wire: replace
   it with a real YouTube-transcript source (Apify YouTube Transcript, a RapidAPI
   transcript API, Supadata, or a self-hosted `youtube-transcript-api`). It receives
   `{{ $json.url }}` and must output the transcript text into the `transcript` field.
   *Until you wire it, the LLM returns `{error:"transcript not provided"}` and the row
   shows **error** — by design, so it never fakes a result.*
4. Networking: the HTTP nodes target `http://localhost:8000`. Fine if n8n runs on the
   same machine as AIFOS. If n8n is cloud-hosted, expose AIFOS via a tunnel
   (ngrok/cloudflared) and update the two URLs.
5. **Activate** the workflow (toggle top-right). It now polls every 2 minutes. Paste a
   link in the dashboard table and watch the row walk queued → processing → done.

## Honest boundaries
- The LLM extracts **only what the video states**; the prompt forbids inventing edge.
- AIFOS maps the concept to an **existing, already-tested** template (no auto-generated
  executable code) and shows that template's **real backtest**.
- Auto-deploys nothing. Human review + go-live gates still apply.
