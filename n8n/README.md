# AIFOS — n8n YouTube Strategy Extraction

An **AI-assisted strategy *extraction & validation*** pipeline. It does **not** invent
profitable strategies or claim hidden edge — it extracts the *educational* strategy
logic a video describes, structures it, maps it to a **tested** AIFOS strategy
template, backtests that template, and queues it for **human review**.

```
YouTube transcript ──▶ LLM (structured JSON) ──▶ AIFOS /api/strategies/extracted
                                                   ├─ stores it for review
                                                   ├─ maps it to a tested template
                                                   └─ backtests that template (real history)
```

## Import
1. n8n → **Workflows → Import from File** → `youtube-strategy-extraction.json`.
2. In **Extract via LLM**, set your LLM key (`Authorization: Bearer …`). Any
   OpenAI-compatible endpoint works (OpenAI, Groq, local Ollama, etc.) — swap the URL.
3. In **Inputs**, paste a transcript (or wire a YouTube-transcript / Whisper node
   into the `transcript` field). Set `video_url`.
4. Make sure n8n can reach AIFOS. **Send to AIFOS** points at `http://localhost:8000`
   — fine if n8n runs on the same machine; if n8n is cloud-hosted, expose AIFOS via a
   tunnel (e.g. ngrok/cloudflared) and update that URL.
5. Run it. The extracted strategy appears in AIFOS at `GET /api/strategies/extracted`
   with its **mapped template + clarity score + backtest** — pending your approval.

## Honest boundaries
- The LLM extracts **only what the video states**; the system prompt forbids inventing
  rules or edge.
- AIFOS maps the concept to an **existing, already-tested** strategy template (it does
  not auto-generate novel executable code) and shows that template's **real backtest**.
- Nothing is auto-deployed. A human reviews, and the go-live readiness gates still
  apply before any real money.
