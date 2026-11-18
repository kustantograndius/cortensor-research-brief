"""Research Brief Agent — an OpenMinion 0.1 Python SDK agent.

Input:  one research question.
Output: a structured brief (summary, findings with citations, limitations)
        plus a verification section that is computed locally in this file —
        not by the model — by checking every cited source against the pages
        the tools actually fetched during the run.

Two model-backed stages, both through the OpenMinion SDK:
  1. Research  — an Agent with decorated tools (brief_search, brief_fetch)
                 gathers sources and drafts an answer.
  2. Synthesis — a second Agent with typed output (Pydantic) restructures
                 the gathered source texts into the brief schema. (A single
                 typed run after a long tool trajectory proved unreliable —
                 see FEEDBACK.md, 2026-11-17.)

Then deterministic local code verifies every citation against the run's
source registry before anything is printed.

Provider credentials are read from the environment variable named in
.openminion/agents.json (GEMINI_API_KEY). No secret is stored in this repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html import unescape

from pydantic import BaseModel, field_validator

from openminion import (
    Agent,
    AgentOutputValidationError,
    ProviderError,
    TurnTimeoutError,
    tool,
)

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, ".openminion", "agents.json")
OUTPUT_DIR = os.path.join(HERE, "output")

# --------------------------------------------------------------------------
# Run-scoped source registry. The tools below record what they actually did;
# the local verifier at the end of the run reads this registry. This is what
# makes the verification section evidence-based instead of model-asserted.
# --------------------------------------------------------------------------
SEARCHES: list[dict] = []
FETCHED: dict[str, str] = {}  # url -> extracted page text


def _opener() -> urllib.request.OpenerDirector:
    proxy = urllib.request.ProxyHandler(
        {
            "http": os.environ.get("http_proxy", ""),
            "https": os.environ.get("https_proxy", ""),
        }
    )
    return urllib.request.build_opener(proxy)


def _get(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "research-brief-agent/0.1 (OpenMinion hackathon entry)"
            )
        },
    )
    with _opener().open(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def _clean_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


@tool(min_scope="READ_ONLY", idempotent=True)
def brief_search(query: str) -> str:
    """Search the web for sources about a query.

    Returns up to 6 results as title + URL lines. Backends: DuckDuckGo Lite,
    with a Bing HTML fallback if the first returns nothing parseable.
    (Tool names are project-prefixed on purpose: generic names such as
    "web_search" collide with the runtime's built-in tool aliases —
    see FEEDBACK.md, 2026-11-17.)
    """
    results: list[dict] = []
    backend = "duckduckgo-lite"
    try:
        html = _get(
            "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote_plus(query)
        )
        for match in re.finditer(
            r"<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", html, re.S
        ):
            href = unescape(match.group(1))
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            if "uddg" in params:  # DuckDuckGo redirect wrapper
                href = params["uddg"][0]
            if not href.startswith("http"):
                continue
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if title:
                results.append({"title": title, "url": href})
            if len(results) >= 6:
                break
    except Exception:
        results = []
    if not results:
        backend = "bing-html"
        try:
            html = _get(
                "https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
            )
            for match in re.finditer(
                r"<h2><a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", html, re.S
            ):
                href = unescape(match.group(1))
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                if href.startswith("http") and title:
                    results.append({"title": title, "url": href})
                if len(results) >= 6:
                    break
        except Exception:
            results = []
    SEARCHES.append({"query": query, "backend": backend, "results": results})
    if not results:
        return (
            "search returned no parseable results from either backend; "
            "say so in the brief's limitations instead of guessing sources"
        )
    return "\n".join(f"- {r['title']}\n  {r['url']}" for r in results)


@tool(min_scope="READ_ONLY", idempotent=True)
def brief_fetch(url: str) -> str:
    """Fetch one web page and return its readable text (truncated).

    Only URLs returned by brief_search or given by the user should be
    fetched. The fetched text is registered locally so citations can be
    verified after the run.
    """
    try:
        html = _get(url)
    except Exception as exc:  # network, TLS, HTTP errors all surface honestly
        return f"fetch failed for {url}: {exc}"
    text = _clean_html(html)[:6000]
    FETCHED[url] = text
    return f"URL: {url}\n---\n{text}"


# --------------------------------------------------------------------------
# Typed output (stage 2)
# --------------------------------------------------------------------------
class Finding(BaseModel):
    claim: str
    source_url: str


class ResearchBrief(BaseModel):
    question: str
    summary: str
    findings: list[Finding]
    limitations: list[str]

    @field_validator("limitations", mode="before")
    @classmethod
    def _coerce_limitations(cls, value: object) -> object:
        # Models often return limitations as one sentence instead of a list;
        # typed-output validation is all-or-nothing, so coerce instead of
        # discarding an otherwise valid brief (see FEEDBACK.md, 2026-11-17).
        if isinstance(value, str):
            return [value]
        return value


# --------------------------------------------------------------------------
# Local verification — deterministic, model-independent.
# A finding is SUPPORTED when its cited URL was actually fetched during this
# run and the claim's content words overlap the fetched text enough. Anything
# else is flagged, never silently trusted.
# --------------------------------------------------------------------------
_STOPWORDS = set(
    "the a an and or of to in is are was were for on with as by at from that "
    "this it its be has have had not but can could should would may might".split()
)


def _tokens(text: str) -> set[str]:
    return {
        tok
        for tok in re.findall(r"[a-z0-9]+", text.lower())
        if len(tok) > 2 and tok not in _STOPWORDS
    }


def verify_findings(findings: list[Finding]) -> list[dict]:
    rows = []
    for finding in findings:
        source_text = FETCHED.get(finding.source_url)
        if source_text is None:
            rows.append(
                {
                    "claim": finding.claim,
                    "source_url": finding.source_url,
                    "status": "SOURCE_NOT_FETCHED",
                    "overlap": None,
                    "note": "cited URL was not fetched by brief_fetch in this run",
                }
            )
            continue
        claim_tokens = _tokens(finding.claim)
        overlap = (
            len(claim_tokens & _tokens(source_text)) / max(1, len(claim_tokens))
        )
        if overlap >= 0.35:
            status = "SUPPORTED"
        elif overlap >= 0.15:
            status = "PARTIAL"
        else:
            status = "WEAK_OVERLAP"
        rows.append(
            {
                "claim": finding.claim,
                "source_url": finding.source_url,
                "status": status,
                "overlap": round(overlap, 2),
                "note": "token overlap between claim and fetched page text",
            }
        )
    return rows


RESEARCH_INSTRUCTIONS = """You are the research stage of a research-brief agent. For the user's question:
1. Call brief_search at least once to find relevant sources.
2. Call brief_fetch on at least two of the most relevant result URLs and read
   the returned text carefully.
3. Base your draft ONLY on text you actually fetched. Never invent facts,
   dates, or numbers.
4. Finish with a plain-language draft answer that names the source URL
   behind each fact, and note anything you could not verify."""

SYNTHESIS_INSTRUCTIONS = """You convert gathered research into a structured brief.
Return ONLY JSON matching the requested schema: question, summary, findings
(each with claim and source_url), limitations.
Rules: use ONLY the source texts provided in the prompt; every finding's
source_url must be copied exactly from the provided source list;
"limitations" must be a JSON array of strings (never a single string);
if the sources are thin, say so in limitations. No markdown, no extra text."""


def _sources_digest(max_sources: int = 4, per_source_chars: int = 4000) -> str:
    parts = []
    for url, text in list(FETCHED.items())[:max_sources]:
        parts.append(f"SOURCE {url}\n{text[:per_source_chars]}")
    return "\n\n".join(parts)


def render_markdown(
    brief: ResearchBrief, verification: list[dict], meta: dict
) -> str:
    lines = [
        f"# Research Brief: {brief.question}",
        "",
        f"_Session: {meta.get('session_id')} · Research run: "
        f"{meta.get('research_run_id')} · Synthesis run: "
        f"{meta.get('synthesis_run_id')} · Model-backed runs via OpenMinion "
        f"0.1 SDK_",
        "",
        "## Summary",
        "",
        brief.summary,
        "",
        "## Findings",
        "",
    ]
    for finding in brief.findings:
        lines.append(f"- {finding.claim}")
        lines.append(f"  Source: {finding.source_url}")
    lines += [
        "",
        "## Verification (computed locally, not by the model)",
        "",
        "Each finding was checked against the pages brief_fetch actually "
        "retrieved during this run.",
        "",
    ]
    for row in verification:
        lines.append(
            f"- **{row['status']}** (overlap: {row['overlap']}) — {row['claim']}"
        )
        lines.append(f"  Source: {row['source_url']}")
    lines += ["", "## Limitations", ""]
    for limitation in brief.limitations:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question",
        nargs="?",
        default="What is OpenMinion and what does it provide to agent builders?",
    )
    parser.add_argument("--session", default="research-brief-demo")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    # ---- Stage 1: research with tools ------------------------------------
    try:
        with Agent(
            config_path=CONFIG_PATH,
            agent_id="researcher",
            instructions=RESEARCH_INSTRUCTIONS,
            tools=[brief_search, brief_fetch],
            forced_tools=["brief_search"],
            session_id=args.session,
        ) as agent:
            research = agent.run(args.question, timeout_seconds=args.timeout)
    except ProviderError as exc:
        print(f"provider failed (research stage): {exc.code}: {exc.message}")
        return 1
    except TurnTimeoutError as exc:
        print(f"turn timed out (research stage): {exc}")
        return 1

    if not FETCHED:
        print("research stage fetched no sources; cannot build a brief")
        print(f"draft was: {research.text}")
        return 3

    # ---- Stage 2: typed synthesis from the gathered sources --------------
    synthesis_prompt = (
        f"Research question: {args.question}\n\n"
        f"Draft from the research stage:\n{research.text}\n\n"
        f"Source texts gathered this run:\n{_sources_digest()}"
    )
    try:
        with Agent(
            config_path=CONFIG_PATH,
            agent_id="researcher",
            instructions=SYNTHESIS_INSTRUCTIONS,
            session_id=f"{args.session}-synthesis",
            output_type=ResearchBrief,
        ) as agent:
            synthesis = agent.run(synthesis_prompt, timeout_seconds=180)
    except ProviderError as exc:
        print(f"provider failed (synthesis stage): {exc.code}: {exc.message}")
        return 1
    except TurnTimeoutError as exc:
        print(f"turn timed out (synthesis stage): {exc}")
        return 1
    except AgentOutputValidationError as exc:
        print("synthesis output failed schema validation; raw text follows:")
        print(exc.raw_text)
        return 2

    brief: ResearchBrief = synthesis.output
    verification = verify_findings(brief.findings)
    meta = {
        "session_id": args.session,
        "research_run_id": getattr(research, "run_id", None),
        "synthesis_run_id": getattr(synthesis, "run_id", None),
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    payload = {
        "brief": brief.model_dump(),
        "verification_local": verification,
        "research_draft": research.text,
        "sources_searched": SEARCHES,
        "sources_fetched": sorted(FETCHED.keys()),
        "run": meta,
    }
    with open(os.path.join(OUTPUT_DIR, "brief.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    markdown = render_markdown(brief, verification, meta)
    with open(os.path.join(OUTPUT_DIR, "brief.md"), "w", encoding="utf-8") as fh:
        fh.write(markdown)

    print(markdown)
    print(f"[meta] session={meta['session_id']} "
          f"research_run={meta['research_run_id']} "
          f"synthesis_run={meta['synthesis_run_id']}")
    print(
        f"[meta] searches={len(SEARCHES)} fetched={len(FETCHED)} "
        f"findings={len(brief.findings)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
