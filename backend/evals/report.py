from collections import defaultdict
from collections.abc import Sequence

from evals.harness import CaseResult


def score_by_category(results: Sequence[CaseResult]) -> dict[str, tuple[int, int]]:
    scores: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for result in results:
        score = scores[result.case.category]
        score[0] += result.passed
        score[1] += 1
    return {category: (passed, total) for category, (passed, total) in scores.items()}


def render(results: Sequence[CaseResult], model: str, runs: int) -> str:
    scores = score_by_category(results)
    passed = sum(score[0] for score in scores.values())
    total = sum(score[1] for score in scores.values())
    lines = [
        "# Evaluation results",
        "",
        f"Model: `{model}`. Each case ran {runs} time(s) against the real model; checks are graded "
        "by code where possible and by a judge prompt only for tone.",
        "",
        "| Category | Passed |",
        "| -------- | ------ |",
        *(f"| {category} | {ok}/{count} |" for category, (ok, count) in scores.items()),
        f"| **Total** | **{passed}/{total}** |",
    ]
    failures = [result for result in results if not result.passed]
    if failures:
        lines += ["", "## Failures"]
    for result in failures:
        lines += ["", f"### {result.case.name} ({result.case.category})", ""]
        lines.append(f"- You: {result.case.turns[-1]}")
        lines.append(f"- Companion: {result.reply or '(no reply)'}")
        if result.error:
            lines.append(f"- Error: {result.error}")
        lines += [
            f"- Failed: {label} ({verdict.detail})"
            for label, verdict in result.verdicts
            if not verdict.passed
        ]
    return "\n".join(lines) + "\n"
