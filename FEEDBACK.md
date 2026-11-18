# Building Blocks Tested / What We Learned

Feedback log for our Cortensor Hackathon #5 entry (Research Brief Agent,
OpenMinion Python SDK 0.1.22). Written honestly, as we go — this file is part
of the submission. Newest entries at the bottom of each day.

**Environment:** Linux VM (no GPU), Python 3.12.3, `openminion==0.1.22`
installed from PyPI into a fresh venv. Provider: Gemini via OpenMinion's
`gemini` preset (OpenAI-compatible endpoint), model `gemini-3.5-flash-lite`.

---

## 2026-11-17 — Phase 1: install, docs, configuration

### Building blocks tested today
- [x] SDK installation from PyPI (`openminion==0.1.22`)
- [x] CLI surface (`openminion version`, `setup --list-providers`, `--help`)
- [x] Provider configuration model (`.openminion/agents.json`)
- [x] Decorated tools, sessions, typed output, first model-backed run
      (see "first runs" section below — it took four attempts, each failure
      taught us something real about the SDK)

### What worked
- **Install was clean.** `pip install "openminion==0.1.22"` on Python 3.12
  resolved ~40 packages (pydantic 2.14, httpx, SQLAlchemy, typer, rich, plus
  the SophiaGraph/GraphFakos family) with no conflicts, and the documented
  import check (`from openminion import Agent, ProviderError,
  TurnTimeoutError, tool`) passed exactly as the quickstart promises.
- **`openminion setup --list-providers` is genuinely useful** — one screen
  gives every preset's API format, credential env var, endpoint, and
  recommended models, including the two `custom-*-compatible` escape hatches.
  It answered questions the docs site made us click around for.
- **The quickstart's capability map is excellent.** The table mapping needs
  to public API (`forced_tools`, `output_type`, `approval_callback`,
  `cancel_event`, …) is the single most productive page we read; we designed
  the whole entry from it plus `examples/sdk/` in the repo.

### Friction, gaps, and surprises
1. **Hackathon submission-repo URL is still a placeholder.** The DoraHacks
   page for Hackathon #5 (kickoff was 16 Oct 2026) still says the dedicated
   submission repository URL "will be added before kickoff" and, under
   Timeline, that it "will be announced before kickoff". A month into the
   build period there is still no URL on the page, so participants cannot
   tell where the required PR should go. (Organizer-side issue, but it is
   the first thing a builder looks for.)
2. **"Recommended model" for the Gemini preset is not account-safe.** Setup
   recommends `gemini-3.6-flash`; Google gates model availability per
   account for new users (on our account the verified-working model is
   `gemini-3.5-flash-lite`; some listed models return 404). The providers
   doc does warn that recommended models "are setup defaults, not
   guarantees", but a first-time builder hits this as a runtime 404, not as
   a setup-time hint. A `doctor` probe that verifies the *configured* model
   answers (not just that a key exists) would close this gap — maybe
   `--check-turn` already does this; we will report what we find.
3. **Docs links on the DoraHacks page are unlabelled.** The detail page's
   "Detail Docs & Reference" section names a GitBook and a "V2
   documentation" without visible URLs in the page text; we found the SDK
   docs via openminion.com instead. Minor, but it cost time.
4. **Two version lines to keep straight.** TestPyPI shows a separate
   `openminion` 0.1.20 build; the real install path is PyPI proper. The
   quickstart pinning `==0.1.22` in `requirements.txt` prevented any
   ambiguity — good pattern, worth keeping.

---

## 2026-11-17 — Phase 1 (continued): configuration shape and first runs

### Building blocks tested in this section
- [x] `openminion setup --no-chat --provider gemini --model … --check-provider`
- [x] `openminion doctor --check-turn` (full pass: 24 OK / 3 warn / 0 fail,
      including a real turn smoke test — this *does* verify the configured
      model answers, which answers our question in item 2 above, positively)
- [x] Decorated tools with `forced_tools`, explicit sessions (one per stage)
- [x] Typed output (`output_type` + Pydantic), `AgentOutputValidationError`
- [x] Error surfaces: `ProviderError` paths exercised via misconfiguration

### Finding 1 — `gemini` is a setup preset, not a runtime provider kind
- **Steps:** write `.openminion/agents.json` exactly in the shape the
  Providers docs show (`agents.<id>.provider: "gemini"`,
  `providers.gemini: {model, api_key_env}`), then run
  `openminion doctor --check-turn`.
- **Expected:** bootstrap succeeds, as the docs present `gemini` alongside
  `openai`/`anthropic` as a selectable provider.
- **Actual:** `[FAIL] provider.supported: Configured provider 'gemini' is
  not supported … one of: anthropic, cerebras, claude, cortensor, echo,
  groq, ollama, openai, openrouter` and `runtime.bootstrap` fails with
  `Unknown provider 'gemini'`.
- **What setup actually writes:** running `openminion setup --provider
  gemini` reveals the canonical representation — the agent's provider kind
  is `"openai"`, and Gemini lives in `base_url`
  (`https://generativelanguage.googleapis.com/v1beta/openai/`) plus a
  `provider_identity` block (`service_vendor: gemini`,
  `transport_adapter: openai_chat`). The preset→kind mapping is nowhere in
  the docs' config examples; it is only discoverable by running setup and
  reading the generated file (368 lines for one provider).
- **Suggestion:** document the preset→kind mapping in the Providers page, or
  make the error message say "use provider kind 'openai' with the Gemini
  base_url" instead of only listing kinds.
- **Side observation:** `setup` rewrote our whole `agents.json`, created a
  new default agent (`openminion`), and left our existing `researcher`
  profile pointing at the invalid `gemini` kind without flagging it.

### Finding 2 — default `schema_exposure: "stub_first"` breaks the quickstart flow
- **Steps:** with a valid provider config, run the repo's own
  `examples/sdk/tool_agent.py` (decorated `lookup_order`, `forced_tools`)
  against a tool-capable model.
- **Expected:** the example prints `order A-104: ready`.
- **Actual (before fix):** the run ends with an unrelated model reply
  ("I could not safely update the task conditions…"); in our app the same
  root cause surfaced verbatim as the turn result:
  `act_loop_adaptive does not expose tool 'web.search' in the current loop.
  Activate it before use.` — an internal loop error string delivered as the
  agent's answer text, which then (in our case) failed output validation.
- **Root cause:** `runtime.tool_selection.schema_exposure` defaults to
  `stub_first` (see `base/config/tool_selection/models.py`), a mode designed
  for the full 164-tool runtime. In a small SDK app the model sees stubs,
  picks a tool that is not active in the loop, and the loop terminates with
  `ADAPTIVE_TERM_DISALLOWED_TOOL` instead of recovering.
- **Fix that worked:** `"runtime": {"tool_selection": {"schema_exposure":
  "full", "tool_prompt_token_budget": 2000}}` in `agents.json`. After this
  single change, `tool_agent.py` passes verbatim and our agent's tools are
  called correctly.
- **Suggestion:** for the Python SDK facade (few run-scoped tools), default
  to — or at least document — `schema_exposure: "full"`. The quickstart
  never mentions this knob; every new SDK user with a custom config will
  hit this.

### Finding 3 — user tool names can be shadowed by built-in tool aliases
- **Steps:** name a decorated tool `web_search` (a natural name), force it
  via `forced_tools=["web_search"]`, instruct the model to call it.
- **Expected:** the model calls the run-scoped `web_search`.
- **Actual:** the model emits a call to `web.search` — the runtime's
  built-in search tool ID — and the loop rejects it as not exposed
  (Finding 2's error). The brain's name normalization
  (`normalize_tool_name_for_brain` → binding-manager alias resolution)
  maps the natural spelling onto the built-in's canonical ID, so the user
  tool is effectively unreachable under that name.
- **Fix that worked:** project-prefixing the tools (`brief_search`,
  `brief_fetch`) made runs succeed immediately.
- **Suggestion:** warn at registration time when a decorated tool's name
  normalizes to an existing built-in tool ID; that collision is silent and
  cost us two debugging cycles.

### Finding 4 — typed output is unreliable after a long tool trajectory
- **Steps:** one `Agent` with tools *and* `output_type=ResearchBrief`;
  research question requiring 1 search + 2 fetches (~4 minutes of turns).
- **Actual:** research succeeded (the draft even quoted the fetched pages
  accurately), but the final message was polished Markdown prose, not JSON,
  so the run ended in `AgentOutputValidationError` with the whole result
  discarded.
- **What worked:** splitting the workflow into two SDK runs — research
  (tools, free text) → synthesis (no tools, `output_type`, sources in the
  prompt). The synthesis run returned schema-valid JSON on the next attempt.
  This also matches the quickstart's own structured-output example, which
  is a one-shot prompt; the docs could say explicitly that typed output is
  best applied to bounded, tool-free turns.

### Finding 5 — typed-output validation is all-or-nothing on field types
- **Actual:** a synthesis result that was valid JSON with correct findings
  was rejected wholesale because `limitations` came back as a single string
  instead of `list[str]`. One field's type drift discarded five correct,
  well-cited findings.
- **App-side workaround:** a Pydantic `field_validator(mode="before")`
  coercing `str → [str]`. Workable, but every SDK user writing list fields
  will rediscover this; a docs note (or an opt-in lenient decode) would
  help.

### Finding 6 — proxy `no_proxy` with bracketed IPv6 crashes provider checks
- **Environment:** standard VM egress proxy in env vars; `no_proxy` contains
  bracketed IPv6 literals (e.g. `[::1]`, `[fd8b:…::1]`).
- **Actual:** `setup --check-provider`'s connection smoke fails with
  `InvalidURL: Invalid port: ':1]'` — the parser chokes on the bracketed
  IPv6 entry. Sanitizing `no_proxy` to `localhost,127.0.0.1,::1` for the
  child process makes the same check pass. The error message gives no hint
  that `no_proxy` is the culprit.
- **Suggestion:** tolerate bracketed IPv6 entries in `no_proxy` parsing, and
  include the offending value in the error.

### Finding 7 — minimal configs need channel fields the docs never mention
- **Actual:** with provider/bootstrap fixed, `doctor` still failed
  `agent.turn_smoke` with `Unknown channel ''. Available channels: console`
  until the agent profile gained `"default_channel": "console"` and the
  config gained `"enabled_channels": ["console"]`. Neither field appears in
  the Providers docs' example configs.

### What worked well in the runs
- Once configured, the full loop is solid: forced first tool call, multi-
  fetch research, session/run IDs on the result object, and a clean
  two-stage composition using nothing but the public facade
  (`Agent`, `tool`, exceptions) — no deep imports needed.
- `AgentOutputValidationError.raw_text` preserving the model's raw output
  is exactly right for debugging; Findings 4–5 were diagnosable *because*
  the raw text was available.
- End-to-end result (17 Nov): brief on "What is OpenMinion…?" — 1 search
  (6 results), 2 pages fetched, 5 findings, **5/5 locally verified
  SUPPORTED** (token overlap 0.73–0.80). Evidence:
  `evidence/first-run-2026-11-17.txt`, `output/brief.json`.
- Latency note for demo planning: one full brief takes ~3–4 minutes on
  `gemini-3.5-flash-lite` (research stage dominates). A 1–5 minute demo
  video will need a trimmed question or pre-warmed session.
