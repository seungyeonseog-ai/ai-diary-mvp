import unittest
from unittest.mock import Mock, patch

from app.prompt.chat_prompt import _select_sessions_by_bucket
from app.services import hybrid_memory_service as memory


class MemoryDedupTests(unittest.TestCase):
    def test_session_at_document_rank_13_survives_candidate_cutoff(self):
        search = memory.HybridMemoryService(sparse=Mock(), dense=Mock(), strict_errors=True)
        hits = [
            {"doc_id": f"doc-{rank}", "session_id": session, "user_id": 1,
             "index": "sparse", "rank": rank, "type": "summary"}
            for rank, session in enumerate(["A"] * 4 + ["B"] * 4 + ["C"] * 4 + ["D"], 1)
        ]
        with (patch.object(memory.redis_client, "smembers", return_value=set()),
              patch.object(search, "_search_sparse", return_value=hits),
              patch.object(search, "_search_dense", return_value=[])):
            before = search.hybrid_retrieve("우산", 1, "261109", unique_sessions=False)
            after = search.hybrid_retrieve("우산", 1, "261109")
        self.assertNotIn("D", [row["session_id"] for row in before])
        self.assertEqual([row["session_id"] for row in after], ["A", "B", "C", "D"])
        picked = _select_sessions_by_bucket(after)["picked"]
        self.assertIn("D", [row["session_id"] for row in picked])
