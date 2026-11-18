# Demo Video Script — Research Brief Agent (Cortensor Hackathon #5)

**Target length:** ~4 minutes (limit: 1–5 min). **Format:** screen capture,
terminal + editor, English voice-over. **Everything shown is real:** the run
below is the same question as our captured first run
(`evidence/first-run-2026-11-17.txt`), so the on-camera run should land on
the same sources and the same 5/5 verification result — but record whatever
the live run actually produces; do not stage output.

**Recording notes**
- Record the terminal at a large font (18pt+), 1080p or higher.
- A full brief takes ~3–4 minutes on `gemini-3.5-flash-lite`, most of it in
  the research stage. Shoot the run in one take, then **timelapse the
  waiting** in editing (keep the tool activity visible, compress idle
  seconds). Never fake or pre-type output.
- Before recording, run the agent once off-camera with the same question so
  the session/runtime state is warm and you know the timing.
- Keep the API key out of frame: the config shows `api_key_env` and an empty
  `api_key` — that is the shot we *want* on camera.

---

## Shot list

### Shot 1 — Title & premise (0:00–0:25)
**Visual:** Title card: "Research Brief Agent — built on the OpenMinion 0.1
Python SDK". Cut to the repo tree in the editor.

**Narration:**
> "This is a research brief agent built on the OpenMinion Python SDK,
> version 0.1.22. You give it one research question. It searches the web,
> fetches the sources itself, and writes a structured brief — and then,
> before you ever see it, plain local code verifies every citation against
> the pages it actually fetched. No trust in the model's word."

### Shot 2 — Setup & diagnostics (0:25–0:55)
**Visual:** Terminal: `pip install -r requirements.txt` (already installed —
show `requirements.txt` with the `openminion==0.1.22` pin). Open
`.openminion/agents.json`; linger on `provider: "openai"`, the Gemini
`base_url`, `provider_identity`, and the empty `api_key` with
`api_key_env: GEMINI_API_KEY`. Then run:
`openminion --config .openminion/agents.json doctor --check-turn` and show
the summary line.

**Narration:**
> "Setup is a pinned requirements file and one config. Gemini is wired the
> way OpenMinion's own setup writes it — an OpenAI-kind connection to
> Google's compatible endpoint. The key comes from an environment variable;
> there is no secret in this repo. And the SDK's doctor, with a real turn
> smoke test, passes: twenty-four OK, three warnings, zero failures."

### Shot 3 — The code in 30 seconds (0:55–1:25)
**Visual:** Scroll `research_brief.py`: the two `@tool` functions
(`brief_search`, `brief_fetch`) with `min_scope="READ_ONLY"`,
`idempotent=True`; the source-registry globals; the two `Agent(...)`
blocks (stage 1 with `tools` + `forced_tools`, stage 2 with
`output_type=ResearchBrief`); the `verify_findings` function.

**Narration:**
> "The whole agent is one file. Two decorated tools with read-only
> permission metadata — search and fetch — and every page fetched is
> recorded in a run-scoped registry. The workflow is two SDK runs: a
> research stage with tools, then a separate typed synthesis stage. And
> this function — the verifier — is deterministic Python. No model
> involved."

### Shot 4 — The live run (1:25–3:10, timelapsed waiting)
**Visual:** Terminal:
`python research_brief.py "What is OpenMinion and what does it provide to agent builders?"`
Show the run progressing — the forced `brief_search` call, the fetches of
`openminion.com` and the multi-provider patterns page — then the brief
printing to stdout with the `[meta]` line (session, research run ID,
synthesis run ID).

**Narration (over the start of the run):**
> "The demo question is the one from our first captured run: 'What is
> OpenMinion, and what does it provide to agent builders?' The search tool
> is in forced_tools, so the run must start by actually searching — it
> can't answer from memory. One search, six results; then it fetches the
> two most relevant pages and drafts only from what it fetched."

**Narration (as output lands):**
> "Stage two restructures that draft into the typed brief schema — and
> then the local verifier checks each finding against the fetched text."

### Shot 5 — The brief & the verification (3:10–4:00)
**Visual:** Open `output/brief.md`. Highlight the Summary, the five
Findings with their source URLs, then the Verification section: five
`SUPPORTED` rows with overlap values (first run: 0.79, 0.73, 0.79, 0.77,
0.80). Side-by-side with `evidence/first-run-2026-11-17.txt` for a beat.

**Narration:**
> "Five findings, each with its source. And the part we care about: the
> verification section — computed locally, not by the model. In the first
> captured run, all five findings came back SUPPORTED, with claim-to-source
> overlap between 0.73 and 0.80. If a citation hadn't been fetched, or the
> words didn't match the page, it would be flagged right here — never
> silently trusted."

### Shot 6 — What we learned & close (4:00–4:35)
**Visual:** Open `FEEDBACK.md`; scroll the seven findings briefly. End card:
repo URL placeholder + "OpenMinion SDK 0.1.22 · Cortensor Hackathon #5".

**Narration:**
> "Building this surfaced seven real findings about the SDK — including
> two that will bite every new user: the Gemini preset isn't a runtime
> provider kind, and the default stub-first tool exposure breaks small
> SDK apps, including the repo's own example. All seven, with reproduction
> steps, are in FEEDBACK dot md. The agent works end to end, the citations
> check out — and the SDK feedback is part of the submission. Thanks for
> watching."

---

## Claim discipline (do not exceed the evidence)

Supported by `evidence/first-run-2026-11-17.txt` / `output/brief.json`:
- 1 search (DuckDuckGo Lite), 6 results; 2 pages fetched; 5 findings;
  5/5 SUPPORTED, overlap 0.73–0.80.
- Session `research-brief-demo`; research run
  `c42fe57eae6545fbb400cede6e73d601`; synthesis run
  `27c048fb96b04275b622d7f40049b767`.
- `doctor --check-turn`: 24 ok / 3 warn / 0 fail.
- Model: `gemini-3.5-flash-lite` via the Gemini preset.

Not claimed anywhere in this script: speed benchmarks, accuracy rates
beyond the single captured run, memory/skills/tasks/delegation usage
(not exercised), or any Cortensor Portal/Router integration.
