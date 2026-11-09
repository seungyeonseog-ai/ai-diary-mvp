"""Measure current FTS and local vector retrieval before either selector."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests.memory_eval_cases import DATE, PROFILES, cases, session_id, summaries


def load_documents(sparse, dense):
    texts, metadata = [], []
    for user, profile in PROFILES.items():
        place, alias, item, decoy, person, _, old, new = profile
        keywords = {
            1: [place, item, person],
            2: [place, "약속", old],
            3: [place, "일정 변경", new],
            4: ["집", decoy, "도서관 약속"],
            5: [place, alias, "놓고 온 물건"],
        }
        for day, words in keywords.items():
            summary = summaries(profile)[day]
            entries = [("summary", summary), ("key_sentence", summary.split(". ")[-1]),
                       ("keywords_all", ", ".join(words))]
            entries.extend(("keyword", word) for word in words)
            sid = session_id(day)
            for kind, content in entries:
                doc_id = dense.build_id(user, sid, kind, content)
                texts.append(content)
                metadata.append({"user_id": user, "session_id": sid, "type": kind,
                                 "doc_id": doc_id, "yymmdd": sid.split("_")[0],
                                 "timestamp": f"2026-11-{day:02d}T00:00:00"})
    sparse.add_documents(texts, metadata)
    dense.add_documents(texts=texts, metadatas=metadata, ids=[row["doc_id"] for row in metadata])
    return len(texts)


def measure(search, case, preprocess, select):
    required = [session_id(day) for day in case.required]
    hits = {}

    def capture(label, original):
        def wrapped(*args, **kwargs):
            hits[label] = original(*args, **kwargs)
            return hits[label]
        return wrapped

    # Capture actual hits as they pass through the unchanged hybrid method.
    with (patch.object(search, "_search_sparse", capture("fts", search._search_sparse)),
          patch.object(search, "_search_dense", capture("dense", search._search_dense))):
        ranked = search.hybrid_retrieve(preprocess(case.source), case.user,
                                        DATE.replace("-", "")[2:],
                                        top_k=search.SPARSE_K + search.DENSE_K, unique_sessions=False)
    if any(row["user_id"] != case.user for source in (*hits.values(), ranked) for row in source):
        raise AssertionError(f"{case.key} cross-account search hit")
    top = ranked[:12]
    a = select(top, need=4, unique_sessions=False)["picked"]
    b = select(top, need=4)["picked"]
    production_top = search.hybrid_retrieve(preprocess(case.source), case.user,
                                            DATE.replace("-", "")[2:], top_k=12)
    production = select(production_top, need=4)["picked"]
    if len(production_top) != len({row["session_id"] for row in production_top}):
        raise AssertionError(f"{case.key} duplicate session in production candidates")
    stages = {label: [row["session_id"] for row in rows] for label, rows in
              (*hits.items(), ("fused", ranked), ("top12", top), ("current", a), ("unique", b),
               ("production_top12", production_top), ("production", production))}
    ranks = {label: {sid: sids.index(sid) + 1 if sid in sids else None for sid in required}
             for label, sids in stages.items()}
    for label in ("current", "unique"):
        stages[f"{label}_delivered"] = list(dict.fromkeys(stages[label]))
    return {"case": case.key, "group": case.group, "query": case.source, "required": required,
            "first_ranks": ranks, "stages": stages, "top12_documents": top}


def summarize(rows):
    totals = Counter()
    for row in rows:
        stages = row["stages"]
        totals["questions"] += 1
        for label in ("current", "unique"):
            totals[f"{label}_duplicate_slots"] += len(stages[label]) - len(set(stages[label]))
        required = set(row["required"])
        if not required:
            continue
        totals["answerable"] += 1
        for label in ("fts", "dense", "fused", "top12", "current", "unique",
                      "production_top12", "production"):
            totals[f"all_evidence_{label}"] += required.issubset(stages[label])
        a, b = (required.issubset(stages[label]) for label in ("current", "unique"))
        if not required.issubset(stages["fused"]):
            totals["missing_from_search"] += 1
        elif not required.issubset(stages["top12"]):
            totals["below_top12"] += 1
        elif not a:
            totals["missed_by_current_selection"] += 1
        totals["recovered"] += not a and b
        totals["lost"] += a and not b
        production = required.issubset(stages["production"])
        totals["production_recovered"] += not a and production
        totals["production_lost"] += a and not production
    return dict(totals)


def run():
    os.environ.update(DATABASE_URL="sqlite:///:memory:", SECRET_KEY="memory-eval-only",
                      OPENAI_API_KEY="memory-eval-no-network", HF_HUB_OFFLINE="1",
                      TRANSFORMERS_OFFLINE="1", ANONYMIZED_TELEMETRY="False",
                      OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    from app.config.settings import settings
    settings.chroma_host = None  # Never connect to the product collection.
    from app.prompt.chat_prompt import _preprocess_query, _select_sessions_by_bucket
    from app.services import hybrid_memory_service as hybrid
    from app.services.sparse_service import SparseIndexService
    from app.services.vector_db_service import VectorDBService

    with TemporaryDirectory(prefix="memory-search-eval-") as temp:
        sparse = SparseIndexService(str(Path(temp) / "sparse.db"))
        try:
            dense = VectorDBService(persist_directory=None, collection_name="internal_memory_search_eval")
            count = load_documents(sparse, dense)
            if dense.vectorstore._collection.count() != count:
                raise AssertionError("Synthetic vector index count mismatch")
            search = hybrid.HybridMemoryService(sparse=sparse, dense=dense, strict_errors=True)
            # The isolated index contains only completed synthetic sessions.
            with patch.object(hybrid.redis_client, "smembers", return_value=set()):
                rows = [measure(search, case, _preprocess_query, _select_sessions_by_bucket)
                        for case in cases()]
        finally:
            sparse.conn.close()
    return {"indexed_documents": count, "gpt_calls": 0,
            "totals": {group: summarize(row for row in rows if row["group"] == group)
                       for group in ("development", "holdout")},
            "cases": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["totals"], indent=2))
