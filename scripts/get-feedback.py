#!/usr/bin/env python3
"""Get feedback on BlueClaw specs from multiple LLMs via OpenRouter."""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    print("Error: Set OPENROUTER_API_KEY environment variable")
    sys.exit(1)
API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "google/gemini-3-pro-preview",
    "x-ai/grok-4.1-fast",
    "openai/gpt-5.2",
]

SPEC_DIR = Path(__file__).parent.parent / "spec"
OUTPUT_DIR = Path(__file__).parent.parent / "feedback"

# Key specs to review (skip why.md — it's motivational, not technical)
SPECS_TO_REVIEW = [
    "architecture.md",
    "lexicons.md",
    "bridge-a2a-atproto.md",
    "reputation.md",
    "pds-implementation.md",
    "interop.md",
    "reference-implementation.md",
]

PROMPT = """You are reviewing the technical specifications for BlueClaw — an open social protocol for AI agents built on AT Protocol (Bluesky) and Google's A2A Protocol.

Your job is to provide critical, constructive feedback. Be specific. Don't be nice for the sake of being nice.

Focus on:
1. **Technical feasibility** — Are there parts that won't work as described? Missing details?
2. **Architecture gaps** — What's missing? What hasn't been thought through?
3. **AT Protocol accuracy** — Does this correctly understand and use AT Protocol concepts?
4. **A2A Protocol accuracy** — Does this correctly understand and use A2A concepts?
5. **Security concerns** — Any attack vectors not addressed?
6. **Practical concerns** — What would make this hard to actually build/adopt?
7. **Strongest aspects** — What's genuinely good about this design?

Here are the specifications:

---

{specs}

---

Provide your review in this format:

## Overall Assessment
(2-3 sentences)

## Critical Issues (things that need to change)
(numbered list)

## Gaps & Missing Pieces
(numbered list)

## Security Concerns
(numbered list)

## Strongest Aspects
(numbered list)

## Suggestions
(numbered list)

## Feasibility Rating
(1-10, where 10 = immediately buildable as-is, 1 = fundamental redesign needed)
"""


def load_specs():
    """Load all spec files into a single string."""
    parts = []
    for name in SPECS_TO_REVIEW:
        path = SPEC_DIR / name
        if path.exists():
            content = path.read_text()
            parts.append(f"# FILE: spec/{name}\n\n{content}")
    return "\n\n---\n\n".join(parts)


def query_model(model: str, prompt: str) -> str:
    """Query a model via OpenRouter."""
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/clawd-conroy/blueclaw",
            "X-Title": "BlueClaw Spec Review",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return f"ERROR ({e.code}): {body}"
    except Exception as e:
        return f"ERROR: {e}"


def main():
    specs = load_specs()
    total_chars = len(specs)
    print(f"Loaded {len(SPECS_TO_REVIEW)} specs ({total_chars:,} chars)")
    
    prompt = PROMPT.format(specs=specs)
    print(f"Prompt size: {len(prompt):,} chars\n")

    OUTPUT_DIR.mkdir(exist_ok=True)

    for model in MODELS:
        short_name = model.split("/")[-1]
        print(f"🔄 Querying {model}...")
        
        response = query_model(model, prompt)
        
        outfile = OUTPUT_DIR / f"review-{short_name}.md"
        outfile.write_text(f"# BlueClaw Spec Review — {model}\n\n{response}\n")
        
        print(f"✅ {model} → {outfile} ({len(response):,} chars)")
        print()

    print("Done! Reviews saved to feedback/")


if __name__ == "__main__":
    main()
