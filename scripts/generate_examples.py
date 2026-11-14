"""Generate REAL example JSON via the running backend (never fabricates data)."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx


EXAMPLES = {
    "time_trend": {
        "query": "How many trials for Niemann-Pick disease type C started each year since 2018?",
        "condition": "Niemann-Pick disease type C", "start_year": 2018,
    },
    "phase_distribution": {
        "query": "How are Fabry disease clinical trials distributed across phases?",
        "condition": "Fabry disease",
    },
    "geography": {
        "query": "Which countries have the most recruiting trials for Wilson disease?",
        "condition": "Wilson disease", "recruiting_only": True,
    },
    "network": {
        "query": "Show the sponsor to drug network for Fabry disease trials",
        "condition": "Fabry disease",
    },
    "comparison": {
        "query": "Compare trial phases for ivacaftor versus lumacaftor",
        "drugs": ["ivacaftor", "lumacaftor"],
    },
}


async def generate(url: str, max_studies: int) -> None:
    out = Path("examples")
    out.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=180.0) as client:
        for name, payload in EXAMPLES.items():
            response = await client.post(
                f"{url.rstrip('/')}/api/v1/analyze",
                json={**payload, "max_studies": max_studies},
            )
            response.raise_for_status()
            result = response.json()
            path = out / f"{name}.json"
            path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            meta = result["meta"]
            status = "REGISTRY COMPLETE" if meta["complete"] else "REGISTRY PARTIAL"
            if meta.get("visualization_truncated", False):
                status += " / CHART TRUNCATED"
            print(f"{path}: {status}, used={meta['records_used']}")
    print("Inspect both registry completeness and visualization truncation before submitting.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--max-studies", type=int, default=1500)
    options = parser.parse_args()
    asyncio.run(generate(options.url, options.max_studies))
