# Research Brief Agent — Cortensor Hackathon #5 entry

A small, working agent built on the **OpenMinion 0.1 Python SDK**
(`openminion==0.1.22`). Give it one research question; it searches the web,
fetches the most relevant sources, and produces a structured brief whose
citations are **verified locally** — by deterministic code, not by the
model — against the pages it actually fetched during the run.

Built for **Cortensor Hackathon #5** (DoraHacks). First working run:
`evidence/first-run-2026-11-17.txt` — 5 findings, **5/5 locally verified
SUPPORTED** (claim↔source token overlap 0.73–0.80). A captured example
output lives in `examples/brief.md` / `examples/brief.json`.

## What the agent does

1. **Research (stage 1, tools + free text)** — an OpenMinion `Agent` with
   two decorated tools gathers sources:
   - `brief_search` — web search (DuckDuckGo Lite, Bing HTML fallback),
     returns up to 6 title + URL results.
   - `brief_fetch` — downloads a page and extracts readable text. Every
     fetched page is recorded in a **run-scoped source registry**.
   The stage drafts an answer based only on text it actually fetched.
2. **Synthesis (stage 2, typed output)** — a second `Agent` run with
   `output_type=ResearchBrief` (Pydantic) restructures the gathered source
   texts into the brief schema: `question`, `summary`, `findings`
   (claim + `source_url`), `limitations`. The two stages are separate on
   purpose: a single typed run after a long tool trajectory proved
   unreliable (see `FEEDBACK.md`, Finding 4).
3. **Local verification (no model involved)** — plain Python checks every
   finding: was the cited URL actually fetched this run, and do the
   claim's content words overlap the fetched page text? Each finding is
   labelled `SUPPORTED` (overlap ≥ 0.35), `PARTIAL` (≥ 0.15),
   `WEAK_OVERLAP`, or `SOURCE_NOT_FETCHED`. Anything the sources don't
   back is flagged, never silently trusted.

Outputs: the brief printed to stdout, plus `output/brief.md` and
`output/brief.json` (brief + verification rows + source registry + run IDs).

This mirrors a workflow we use for real work: a fast model drafts, then an
independent, deterministic check verifies before anything is trusted.

## How OpenMinion is used (meaningfully, not decoratively)

Everything goes through the SDK's **public facade** — `from openminion
import Agent, tool, ProviderError, TurnTimeoutError,
AgentOutputValidationError`. No deep imports (`openminion.modules.*` are
outside the 0.1.x compatibility policy).

- **Agent execution** — two composed `Agent` runs (research → synthesis)
  in one repeatable workflow, each with its own instructions and explicit
  `session_id`, so every run is inspectable and reproducible.
- **Decorated tools with permission metadata** — plain Python functions
  with `@tool(min_scope="READ_ONLY", idempotent=True)`, passed via
  `tools=[...]`. `brief_search` is in `forced_tools`, so every run
  demonstrably exercises the tool path instead of answering from memory.
  Tool names are project-prefixed on purpose: generic names such as
  `web_search` normalize onto the runtime's built-in tool IDs and become
  unreachable (FEEDBACK Finding 3).
- **Provider configuration** — `.openminion/agents.json` declares one
  agent profile (`researcher`). Gemini is represented the way the SDK's
  own `setup` writes it: an `openai`-kind connection whose `base_url` is
  Google's OpenAI-compatible endpoint, with a `provider_identity` block
  marking the vendor and `api_key_env` naming the credential variable
  (`GEMINI_API_KEY`). **No secret is stored in this repository** — the
  `api_key` fields are empty strings by design. The config also sets
  `runtime.tool_selection.schema_exposure` to `"full"`; the `stub_first`
  default breaks small SDK apps, including the repo's own `tool_agent.py`
  example (FEEDBACK Finding 2).
- **Typed output** — `output_type=ResearchBrief` on the bounded, tool-free
  synthesis turn, with a `mode="before"` Pydantic validator coercing a
  string `limitations` into a list (validation is all-or-nothing;
  FEEDBACK Finding 5).
- **Error surfaces** — `ProviderError` and `TurnTimeoutError` are caught
  per stage and reported visibly; `AgentOutputValidationError` prints the
  preserved raw model text. Nothing fails silently.
- **Diagnostics** — `openminion doctor --check-turn` passes on this
  configuration (24 ok / 3 warn / 0 fail on our machine), including a real
  turn smoke test against the configured model.

## Architecture

```
                ┌──────────────────────────────────────────────┐
 question ────► │ Stage 1: Agent (tools, free text)            │
                │   brief_search ──► SEARCHES registry         │
                │   brief_fetch  ──► FETCHED registry (url→txt)│
                └──────────────┬───────────────────────────────┘
                               │ draft + source texts digest
                ┌──────────────▼───────────────────────────────┐
                │ Stage 2: Agent (output_type=ResearchBrief)   │
                │   typed synthesis, no tools                  │
                └──────────────┬───────────────────────────────┘
                               │ ResearchBrief (Pydantic)
                ┌──────────────▼───────────────────────────────┐
                │ Local verifier (deterministic, no model)     │
                │   citation ∈ FETCHED? token overlap ≥ 0.35?  │
                └──────────────┬───────────────────────────────┘
                               ▼
                output/brief.md + output/brief.json + stdout
```

The source registry is the key design decision: because the tools record
what they *actually did*, the verification section is evidence-based
instead of model-asserted.

## Setup

Requirements: Python 3.11+ (developed and tested on 3.12.3), an API key
for any OpenMinion-supported provider.

```bash
git clone <this-repo-url>
cd <repo-dir>
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt   # openminion==0.1.22, pydantic>=2.0
export GEMINI_API_KEY="<your key>"
```

The shipped config targets Gemini's OpenAI-compatible endpoint with model
`gemini-3.5-flash-lite`. Any other OpenMinion provider works too: edit the
`providers` block in `.openminion/agents.json` (OpenAI, Anthropic,
OpenRouter, Ollama, Cortensor Portal/Router, …) — the agent code does not
change. Note that providers gate model availability per account; if the
configured model returns 404, pick a model your account can actually call.

Optional sanity check before a run:

```bash
openminion --config .openminion/agents.json doctor --check-turn
```

## Run

```bash
python research_brief.py "What is OpenMinion and what does it provide to agent builders?"
python research_brief.py "Your question" --session my-session --timeout 300
```

Exit codes: `0` success · `1` provider/timeout failure · `2` synthesis
output failed schema validation (raw text printed) · `3` research stage
fetched no sources.

## Repository layout

| Path | Contents |
|---|---|
| `research_brief.py` | The whole agent: tools, two-stage workflow, local verifier |
| `.openminion/agents.json` | Provider/agent config (no secrets; key via env var) |
| `requirements.txt` | Pinned dependencies (`openminion==0.1.22`) |
| `FEEDBACK.md` | "Building Blocks Tested" + "What We Learned" log (submission note) |
| `evidence/` | Captured runs: the first successful run + three preserved failed attempts |
| `examples/` | Example output (`brief.md`, `brief.json`) from the first run |
| `DEMO.md` | Script for the 1–5 minute demo video |

## Building Blocks Tested

Exercised so far (full log with reproduction steps in `FEEDBACK.md`):

- [x] SDK installation from PyPI (`openminion==0.1.22`)
- [x] CLI surface (`openminion version`, `setup --list-providers`, `--help`)
- [x] Provider configuration model (`.openminion/agents.json`, Gemini preset)
- [x] `openminion setup --no-chat --provider gemini --check-provider`
- [x] `openminion doctor --check-turn` (24 OK / 3 warn / 0 fail, real turn smoke)
- [x] Agent execution — two composed model-backed runs
- [x] Decorated tools with permission metadata (`min_scope`, `idempotent`)
- [x] `forced_tools`
- [x] Sessions (explicit ID per stage)
- [x] Typed output (`output_type` + Pydantic), `AgentOutputValidationError`
- [x] Error surfaces (`ProviderError` exercised via misconfiguration)

Not yet exercised: memory, skills, tasks, delegation, Portal/Cortensor
models (optional for this entry's workflow).

## What We Learned

Seven substantive findings are logged with reproduction steps, expected vs
actual behavior, and suggestions in `FEEDBACK.md`. The headlines:

1. **`gemini` is a setup preset, not a runtime provider kind.** A
   docs-shaped hand-written config fails bootstrap with "Unknown provider
   'gemini'"; the canonical shape (kind `openai` + Gemini `base_url` +
   `provider_identity`) is only discoverable by running `setup` and
   reading the file it generates.
2. **Default `schema_exposure: "stub_first"` breaks the quickstart flow.**
   Small SDK apps — and the repo's own `tool_agent.py` example — end in a
   disallowed-tool loop error delivered as turn text. Setting
   `schema_exposure: "full"` fixes both.
3. **User tool names can be shadowed by built-in tool aliases.** A tool
   named `web_search` normalizes to the built-in `web.search` ID and is
   unreachable; project-prefixing (`brief_search`) fixes it. A
   registration-time collision warning would save every new user this
   debugging cycle.
4. **Typed output is unreliable after a long tool trajectory.** Splitting
   research (tools, free text) from synthesis (no tools, typed output) is
   the reliable pattern — worth stating in the docs.
5. **Typed-output validation is all-or-nothing on field types.** One
   field's type drift (`limitations` as a string) discarded five correct,
   well-cited findings; a `mode="before"` validator is the app-side fix.
6. **Bracketed IPv6 entries in `no_proxy` crash provider checks** with an
   `InvalidURL` error that never mentions `no_proxy`.
7. **Minimal configs need channel fields the docs never mention**
   (`default_channel: "console"`, `enabled_channels: ["console"]`), or
   `doctor`'s turn smoke fails.

What worked well: once configured, the full loop is solid — forced first
tool call, multi-fetch research, session/run IDs on the result object, and
clean two-stage composition using nothing but the public facade.
`AgentOutputValidationError.raw_text` preserving the raw model output made
Findings 4–5 diagnosable at all.

## License

Project code: MIT (see `LICENSE`). OpenMinion itself is Apache-2.0.
