"""실제 네트워크 없이 검증 API 예산 상한과 재시작 보존 검사."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.deployment import budget_proxy as proxy


class BudgetTests(unittest.TestCase):
    def test_rejected_payloads_do_not_consume_budget(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(proxy,'DB',Path(temp)/'calls.db'):
            good={'model':proxy.MODEL,'max_completion_tokens':1800}
            for data, size in [({**good,'model':'unapproved'},100),
                               ({**good,'max_completion_tokens':1801},100),
                               ({**good,'n':2},100), (good,60001)]:
                with self.assertRaises(ValueError): proxy.reserve(data,size)
            self.assertFalse(proxy.DB.exists())
            self.assertEqual(proxy.reserve(good,100),1)

    def test_persistent_limit_includes_failed_and_unfinished_calls(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(proxy,'DB',Path(temp)/'calls.db'):
            for index in range(proxy.MAX_CALLS):
                self.assertEqual(proxy.reserve({'model':proxy.MODEL,'max_completion_tokens':1800},100),index+1)
            with self.assertRaises(ValueError):
                proxy.reserve({'model':proxy.MODEL,'max_completion_tokens':1800},100)
            # 같은 DB를 다시 열어도 카운터를 초기화하지 않는다.
            with self.assertRaises(ValueError):
                proxy.reserve({'model':proxy.MODEL,'max_completion_tokens':1800},100)


if __name__=='__main__': unittest.main()
