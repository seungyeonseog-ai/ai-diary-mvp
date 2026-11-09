"""Run an isolated A/B check of writing memory selection from fixed hits."""
import argparse
from collections import Counter
from datetime import datetime
from functools import partial
import json
import os
from unittest.mock import patch

from tests.memory_eval_cases import DATE, PROFILES, candidates, cases, session_id, summaries


def check(engine, case, prompt, hybrid, stream):
    rows = candidates(case)
    selector = partial(prompt._select_sessions_by_bucket, unique_sessions=False)
    expected = {session_id(day) for day in case.required}
    own = {session_id(day): text for day, text in summaries(PROFILES[case.user]).items()}
    report = {"id": case.key, "group": case.group, "input": case.source,
              "expected_sessions": sorted(expected), "rubric": {
                  "2": case.full, "1": case.partial, "0": case.forbidden},
              "fixed_candidates": rows, "conditions": {}}
    for label, select in (
        ("current", selector),
        ("unique", prompt._select_sessions_by_bucket),
    ):
        with (patch.object(hybrid, "HybridMemoryService") as search,
              patch.object(prompt, "_select_sessions_by_bucket", wraps=select) as pick):
            search.return_value.hybrid_retrieve.return_value = rows
            context = stream.memory_context(engine, case.user, case.source, DATE)
            search.return_value.hybrid_retrieve.assert_called_once_with(
                user_query=prompt._preprocess_query(case.source),
                user_id=case.user, yymmdd="261107", top_k=12)
            pick.assert_called_once_with(rows, need=4)
            chosen = [row["session_id"] for row in select(rows, need=4)["picked"]]
        delivered = list(dict.fromkeys(chosen))
        if context != [own[sid] for sid in delivered]:
            raise AssertionError(f"{case.key} {label} wrong account, order or content")
        if "은하열쇠" in " ".join(context):
            raise AssertionError(f"{case.key} {label} unexpected future marker in fixed-hit experiment")
        report["conditions"][label] = {
            "selected": chosen, "delivered": delivered, "past_references": context,
            "duplicate_slots": len(chosen) - len(delivered),
            "all_required_delivered": expected.issubset(delivered) if expected else None,
        }
    return report


def run():
    # Set throwaway app configuration before importing anything that reads settings.
    os.environ.update(DATABASE_URL="sqlite:///:memory:", SECRET_KEY="memory-eval-only",
                      OPENAI_API_KEY="memory-eval-no-network", PYTHONIOENCODING="utf-8")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.connection import Base
    from app.models.db import session_log, user_model  # register foreign key targets
    from app.models.db.session_summary import GPTSessionSummary
    from app.prompt import chat_prompt
    from app.services import hybrid_memory_service, writing_stream

    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine, tables=[GPTSessionSummary.__table__])
        with Session(engine) as db:
            for user, profile in PROFILES.items():
                for day, summary in summaries(profile).items():
                    db.add(GPTSessionSummary(user_id=user, session_id=session_id(day), summary=summary,
                                             key_sentence=summary.split(".")[0], keywords=[profile[0]],
                                             created_at=datetime(2026, 11, day)))
            db.commit()
        results = [check(engine, case, chat_prompt, hybrid_memory_service, writing_stream)
                   for case in cases()]
    finally:
        engine.dispose()
    totals = {}
    for group in ("development", "holdout"):
        subset = [row for row in results if row["group"] == group]
        counts = Counter()
        for row in subset:
            current, unique = (row["conditions"][name] for name in ("current", "unique"))
            counts["answerable"] += bool(row["expected_sessions"])
            for label, result in (("current", current), ("unique", unique)):
                counts[f"{label}_duplicate_slots"] += result["duplicate_slots"]
                counts[f"{label}_all_evidence"] += result["all_required_delivered"] is True
            counts["recovered"] += current["all_required_delivered"] is False and unique["all_required_delivered"] is True
            counts["lost"] += current["all_required_delivered"] is True and unique["all_required_delivered"] is False
        if len(subset) != 20 or counts["answerable"] != 15:
            raise AssertionError(f"{group} invalid split")
        if counts["unique_duplicate_slots"] or counts["lost"] or not counts["recovered"]:
            raise AssertionError(f"{group} unexpected fixed-hit regression: {counts}")
        totals[group] = {"questions": len(subset), **counts}
    return {"experiment": "fixed synthetic Top12", "answer_scores": None,
            "totals": totals, "cases": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=argparse.FileType("w", encoding="utf-8"))
    args = parser.parse_args()
    report = run()
    if args.report:
        with args.report as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(report["totals"], indent=2))
