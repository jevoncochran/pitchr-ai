"""Run every lead snapshot eval case through the real feature and write a report.

Usage:
    uv run python -m evals.run_lead_snapshot --label baseline
    uv run python -m evals.run_lead_snapshot --label low-effort --effort low
    CLAUDE_MODEL=claude-sonnet-5-5 uv run python -m evals.run_lead_snapshot --label sonnet

This calls the real Claude API (about 2 cents per case). Reports are written to
evals/lead_snapshot/results/<label>.md, for reading side by side with the
hand-written reference snapshots.
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path

from app.config import get_settings
from app.prompts.lead_snapshot import format_date
from app.schemas.lead_snapshot import LeadSnapshotRequest, LeadSnapshotResponse
from app.services.lead_snapshot import EFFORT, create_snapshot

EVAL_DIR = Path(__file__).parent / "lead_snapshot"


class ClaudeLogCollector(logging.Handler):
    """Keeps the most recent claude_call log line so we can report its tokens."""

    def __init__(self):
        super().__init__()
        self.last_message = ""

    def emit(self, record):
        self.last_message = record.getMessage()

    def token_counts(self) -> tuple[int, int]:
        found = dict(re.findall(r"(\w+)=(\S+)", self.last_message))
        return int(found.get("input_tokens", 0)), int(found.get("output_tokens", 0))


def render_snapshot(snapshot: LeadSnapshotResponse, today) -> str:
    """The snapshot as it might look on the lead page."""
    lines = []
    if snapshot.last_contact:
        lc = snapshot.last_contact
        lines.append(f"**Last contact:** {format_date(lc.date, today)} · {lc.type}")
    else:
        lines.append("**Last contact:** none")
    if snapshot.last_activity:
        la = snapshot.last_activity
        lines.append(
            f"**Last activity:** {format_date(la.date, today)} · {la.description}"
        )
    else:
        lines.append("**Last activity:** none")
    effort = ", ".join(
        f"{name.replace('_', ' ')} {count}"
        for name, count in snapshot.effort.model_dump().items()
        if count
    )
    lines.append(f"**Effort:** {effort or 'none'}")

    a = snapshot.analysis
    lines += [
        "",
        f"**{a.headline}**",
        "",
        f"**Decision-maker:** {a.decision_maker}",
        "",
        *[f"- {fact}" for fact in a.key_facts],
        "",
        f"**Odds: {a.odds}.** {a.odds_reason}",
        "",
        f"**Goal:** {a.goal}",
        "",
        f"**Approach:** {a.suggested_approach}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="Name for this run's report")
    parser.add_argument("--effort", default=EFFORT, help=f"Default: {EFFORT}")
    args = parser.parse_args()

    collector = ClaudeLogCollector()
    claude_logger = logging.getLogger("pitchr_ai.claude")
    claude_logger.setLevel(logging.INFO)
    claude_logger.addHandler(collector)

    summary_rows = []
    sections = []
    case_files = sorted((EVAL_DIR / "cases").glob("*.json"))

    for number, path in enumerate(case_files, start=1):
        case = json.loads(path.read_text())
        request = LeadSnapshotRequest.model_validate(case["request"])
        print(f"Running {number}/{len(case_files)}: {case['name']}...")

        start = time.perf_counter()
        snapshot = create_snapshot(request, effort=args.effort)
        seconds = time.perf_counter() - start
        tokens_in, tokens_out = collector.token_counts()

        summary_rows.append(
            f"| {number}. {case['name']} | {snapshot.analysis.odds} "
            f"| {seconds:.1f}s | {tokens_in:,} / {tokens_out:,} |"
        )
        checklist = "\n".join(f"- [ ] {item}" for item in case["must_get_right"])
        sections.append(
            f"## {number}. {case['name']}\n\n"
            f"### Must get right\n\n{checklist}\n\n"
            f"### Generated snapshot\n\n{render_snapshot(snapshot, request.today)}\n\n"
            f"### Hand-written reference\n\n> {case['reference_snapshot']}\n"
        )

    report = "\n".join(
        [
            f"# Lead snapshot eval: {args.label}",
            "",
            (
                f"Model: `{get_settings().claude_model}` · Effort: `{args.effort}` "
                f"· {len(case_files)} cases"
            ),
            "",
            "| Case | Odds | Time | Tokens in / out |",
            "| --- | --- | --- | --- |",
            *summary_rows,
            "",
            "---",
            "",
            "\n---\n\n".join(sections),
        ]
    )
    results_dir = EVAL_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    report_path = results_dir / f"{args.label}.md"
    report_path.write_text(report)
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
