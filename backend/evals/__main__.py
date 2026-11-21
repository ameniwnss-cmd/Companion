import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from companion.config import BACKEND_ROOT, LLMProviderName, get_settings
from companion.conversation.personality import Personality
from companion.llm.factory import build_llm
from evals.cases import CASES
from evals.harness import CaseResult, Judge, run_case
from evals.report import render

REPORT = BACKEND_ROOT.parent / "docs" / "evals" / "latest.md"
PAUSE_BETWEEN_CASES_SECONDS = 2.0


async def evaluate(runs: int, category: str | None) -> tuple[list[CaseResult], str] | None:
    settings = get_settings()
    if settings.llm_provider is LLMProviderName.FAKE:
        return None
    cases = [c for c in CASES if category is None or c.category == category]
    results: list[CaseResult] = []
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as http:
        llm = build_llm(settings, http)
        judge = Judge(llm)
        personality = Personality.load(settings.personality_path)
        for case in cases:
            for _ in range(runs):
                result = await run_case(case, llm, personality, judge)
                results.append(result)
                print(f"{'PASS' if result.passed else 'FAIL'}  {case.category:12} {case.name}")
                await asyncio.sleep(PAUSE_BETWEEN_CASES_SECONDS)
    model = settings.groq_model if settings.llm_provider is LLMProviderName.GROQ else "ollama"
    return results, model


def main(runs: int, category: str | None, report: Path) -> int:
    outcome = asyncio.run(evaluate(runs, category))
    if outcome is None:
        print("Evals need a real model. Set LLM_PROVIDER (and its key) in backend/.env.")
        return 2
    results, model = outcome
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render(results, model, runs), encoding="utf-8")
    passed = sum(result.passed for result in results)
    print()
    print(f"{passed}/{len(results)} passed. Report: {report}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grade the companion against the real model.")
    parser.add_argument("--runs", type=int, default=1, help="times to run each case")
    parser.add_argument("--category", help="only run one category")
    parser.add_argument("--report", type=Path, default=REPORT, help="where to write the report")
    args = parser.parse_args()
    sys.exit(main(args.runs, args.category, args.report))
