"""Run every visit debrief eval case through the real feature, score it, and write a report.

Usage:
    uv run python -m evals.run_visit_debrief --label baseline
    uv run python -m evals.run_visit_debrief --label haiku --model claude-haiku-5-5
    uv run python -m evals.run_visit_debrief --label medium --effort medium
    uv run python -m evals.run_visit_debrief --label dates --cases after_the_15th back_later

This calls the real Claude API (roughly 1-2 cents per case on Sonnet 5.5, a
fraction of that on Haiku 5.5): ask the owner first. Each case is scored field
by field against its expected answer (outcome, provider, come-back date and
time, materials, the people, whether it asks, words the summary must and
mustn't use). Reports go to evals/visit_debrief/results/<label>.md, with the
summaries to read side by side.
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path

from app.core.claude import ClaudeError
from app.core.config import get_settings
from app.features.visit_debrief.schemas import VisitDebriefRequest, VisitDebriefResponse
from app.features.visit_debrief.service import EFFORT, debrief_visit

EVAL_DIR = Path(__file__).parent / "visit_debrief"

# $ per million tokens (input, output), for the cost line in the report
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


class ClaudeLogCollector(logging.Handler):
    """Keeps the most recent claude_call log line so we can report its tokens."""

    def __init__(self):
        super().__init__()
        self.last_message = ""

    def emit(self, record):
        self.last_message = record.getMessage()

    def usage(self) -> tuple[str, int, int]:
        found = dict(re.findall(r"(\w+)=(\S+)", self.last_message))
        return (
            found.get("model", "?"),
            int(found.get("input_tokens", 0)),
            int(found.get("output_tokens", 0)),
        )


def score(
    expected: dict, proposal: VisitDebriefResponse
) -> list[tuple[str, bool, str]]:
    """Each check as (what, passed, detail). An expected value of None isn't checked."""
    checks = []

    def check(what: str, passed: bool, detail: str = ""):
        checks.append((what, passed, detail))

    if expected.get("outcome") is not None:
        check(
            "outcome",
            proposal.outcome in expected["outcome"],
            f"got {proposal.outcome}, want {expected['outcome']}",
        )
    if expected.get("provider_type") is not None:
        check(
            "provider",
            proposal.provider_type in expected["provider_type"],
            f"got {proposal.provider_type}, want {expected['provider_type']}",
        )
    got_date = proposal.come_back_date.isoformat() if proposal.come_back_date else None
    check(
        "come-back date",
        got_date == expected["come_back_date"],
        f"got {got_date}, want {expected['come_back_date']}",
    )
    check(
        "come-back time",
        proposal.come_back_time == expected["come_back_time"],
        f"got {proposal.come_back_time}, want {expected['come_back_time']}",
    )
    if expected.get("estimated") is not None:
        check(
            "marked as an estimate"
            if expected["estimated"]
            else "not marked as an estimate",
            bool(proposal.come_back_estimate) == expected["estimated"],
            f"estimate: {proposal.come_back_estimate}",
        )
    check(
        "left materials",
        proposal.left_materials == expected["left_materials"],
        f"got {proposal.left_materials}, want {expected['left_materials']}",
    )

    remaining = list(proposal.people)
    for want in expected["people"]:
        found = find_person(want, remaining)
        label = (
            want.get("contact_id")
            or want.get("first_name")
            or want.get("last_name")
            or want.get("title")
            or f"one of {want.get('candidates')}"
        )
        if not found:
            check(f"person {label}", False, "not in the proposal")
            continue
        remaining.remove(found)
        problems = []
        if "candidates" in want and sorted(found.candidate_contact_ids) != sorted(
            want["candidates"]
        ):
            problems.append(f"candidates {found.candidate_contact_ids}")
        if "spoke_with" in want and found.spoke_with != want["spoke_with"]:
            problems.append(f"spoke_with {found.spoke_with}")
        if (
            "is_decision_maker" in want
            and found.is_decision_maker != want["is_decision_maker"]
        ):
            problems.append(f"is_decision_maker {found.is_decision_maker}")
        check(f"person {label}", not problems, ", ".join(problems))
    if remaining:
        # Not a failure (e.g. the front desk person with no name), but worth reading
        extra = ", ".join(describe(p) for p in remaining)
        check("no extra people", True, f"also listed: {extra}")

    if expected.get("asks") is not None:
        check(
            "asks",
            bool(proposal.questions) == expected["asks"],
            f"questions: {proposal.questions}",
        )

    summary = proposal.summary.lower()
    for words in expected["summary_must_mention"]:
        options = words.lower().split("|")
        check(f"summary mentions {words}", any(o in summary for o in options))
    for words in expected["summary_must_not_mention"]:
        check(f"summary leaves out {words.strip()}", words.lower() not in summary)
    return checks


def find_person(want: dict, people: list):
    for person in people:
        if "contact_id" in want and person.contact_id == want["contact_id"]:
            return person
        if "candidates" in want and set(person.candidate_contact_ids) & set(
            want["candidates"]
        ):
            return person
        # A name can land in either field ("Dr. Patel" read as a first name)
        names = {(person.first_name or "").lower(), (person.last_name or "").lower()}
        if "first_name" in want and want["first_name"].lower() in names:
            return person
        if "last_name" in want and want["last_name"].lower() in names:
            return person
        if (
            "title" in want
            and want["title"].lower() in (person.title or "").lower()
            and not person.first_name
        ):
            return person
    return None


def describe(person) -> str:
    name = (
        " ".join(p for p in (person.first_name, person.last_name) if p) or "(no name)"
    )
    return f"{name} ({person.title or 'no title'}, contact {person.contact_id or '-'}, spoke {person.spoke_with})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--model", help="Defaults to VISIT_DEBRIEF_MODEL or CLAUDE_MODEL"
    )
    parser.add_argument("--effort", default=EFFORT)
    parser.add_argument(
        "--cases", nargs="*", help="Only cases whose file name contains one of these"
    )
    args = parser.parse_args()

    collector = ClaudeLogCollector()
    logging.getLogger("pitchr_ai.claude").addHandler(collector)
    logging.getLogger("pitchr_ai.claude").setLevel(logging.INFO)
    model = (
        args.model or get_settings().visit_debrief_model or get_settings().claude_model
    )

    paths = sorted((EVAL_DIR / "cases").glob("*.json"))
    if args.cases:
        paths = [p for p in paths if any(c in p.name for c in args.cases)]

    report = [
        f"# Visit debrief eval: {args.label}",
        "",
        f"Model `{model}`, effort `{args.effort}`.",
        "",
    ]
    passed_total = checks_total = 0
    tokens_in = tokens_out = 0
    seconds = 0.0
    rows = []
    failed: list[str] = []
    for path in paths:
        case = json.loads(path.read_text())
        request = VisitDebriefRequest(**case["request"])
        start = time.perf_counter()
        try:
            proposal = debrief_visit(request, model=model, effort=args.effort)
        except ClaudeError as error:
            # One failed call (e.g. an API timeout) shouldn't end the run
            failed.append(path.stem)
            rows.append(f"| {path.stem} | failed: {error} | |")
            report += [
                f"## {case['name']} ({path.stem})",
                "",
                f"**Failed:** {error}",
                "",
            ]
            print(f"{path.stem}: failed ({error})")
            continue
        elapsed = time.perf_counter() - start
        _, case_in, case_out = collector.usage()
        tokens_in += case_in
        tokens_out += case_out
        seconds += elapsed

        checks = score(case["expected"], proposal)
        passed = sum(1 for _, ok, _ in checks if ok)
        passed_total += passed
        checks_total += len(checks)
        rows.append(f"| {path.stem} | {passed}/{len(checks)} | {elapsed:.1f}s |")

        report += [
            f"## {case['name']} ({path.stem})",
            "",
            f"**Note:** {case['request']['note']}",
            "",
        ]
        report += [
            (
                f"- Outcome: {proposal.outcome} · provider: {proposal.provider_type} · come back: "
                f"{proposal.come_back_date} {proposal.come_back_time or ''}"
                f"{f' (estimated from: {proposal.come_back_estimate})' if proposal.come_back_estimate else ''}"
                f" · left materials: {proposal.left_materials}"
            ),
            f"- People: {'; '.join(describe(p) for p in proposal.people) or '(none)'}",
            f"- Questions: {proposal.questions or '(none)'}",
            "",
            f"**Summary:** {proposal.summary}",
            "",
        ]
        report += [
            f"- {'✅' if ok else '❌'} {what}"
            + (
                f": {detail}"
                if detail and (not ok or what == "no extra people")
                else ""
            )
            for what, ok, detail in checks
        ]
        report.append("")
        print(f"{path.stem}: {passed}/{len(checks)} ({elapsed:.1f}s)")

    price_in, price_out = PRICES.get(model, (0, 0))
    cost = tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
    totals = [
        "## Totals",
        "",
        f"**{passed_total}/{checks_total} checks passed** over {len(paths) - len(failed)} cases"
        + (f" ({len(failed)} failed to run: {', '.join(failed)})." if failed else "."),
        f"Tokens: {tokens_in} in, {tokens_out} out · about ${cost:.2f} · {seconds:.0f}s in all.",
        "",
        "| Case | Checks | Time |",
        "| --- | --- | --- |",
        *rows,
        "",
    ]
    report[4:4] = totals
    results = EVAL_DIR / "results"
    results.mkdir(exist_ok=True)
    out = results / f"{args.label}.md"
    out.write_text("\n".join(report))
    print(f"\n{passed_total}/{checks_total} checks · about ${cost:.2f} · report: {out}")


if __name__ == "__main__":
    main()
