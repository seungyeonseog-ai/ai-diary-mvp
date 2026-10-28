"""외부 AI/Redis 및 실제 사용자 DB 없이 생성·저장 실패를 검증한다."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'unit-test-only-secret-key-not-for-deployment'
os.environ['OPENAI_API_KEY'] = 'test-only-no-network'

import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.services.diary_service import DiaryService
from app.clients.gpt_api import GPTClient
from app.core.operation_lock import diary_generation_lock


@asynccontextmanager
async def fake_lock(_):
    renewal = asyncio.get_running_loop().create_future()
    try:
        yield renewal
    finally:
        renewal.cancel()


class DiaryStreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = DiaryService.__new__(DiaryService)
        self.service.chat_repository = Mock()
        self.service.chat_repository.check_today_diary_by_source.return_value = None
        self.service.chat_repository.diary_get_today_user_chat_and_tokens.return_value = (['private chat'], 60)
        self.service.prompt_service = Mock()
        self.service.gpt_client = Mock()
        self.service.redis_client = Mock()
        self.db = Mock()
        self.saved = []
        self.db.add.side_effect = self.saved.append
        def commit():
            self.saved[-1].diary_id = 42
        self.db.commit.side_effect = commit

    async def collect(self, chunks=('오늘 ', '기분이 좋았다.'), fail=False):
        async def stream(_):
            for chunk in chunks:
                yield chunk
            if fail:
                raise RuntimeError('private upstream details')
        self.service.gpt_client.stream_gpt_response = stream
        with patch('app.services.diary_service.diary_generation_lock', fake_lock), patch('app.services.diary_service.get_db', return_value=iter([self.db])):
            result = []
            async for frame in self.service.generate_diary_stream(1):
                event, data, _ = frame.split('\n', 2)
                if event == 'event: saved':
                    self.db.commit.assert_called_once()
                result.append((event[7:], json.loads(data[6:])))
            return result

    async def test_success_requires_commit_before_saved_event(self):
        result = await self.collect()
        self.assertEqual([event for event, _ in result], ['chunk', 'chunk', 'saved'])
        self.assertEqual(self.saved[0].content, '오늘 기분이 좋았다.')
        self.assertEqual(result[-1][1]['diary_id'], 42)
        self.db.close.assert_called_once()

    async def test_upstream_failure_never_saves_partial_diary(self):
        result = await self.collect(fail=True)
        self.assertEqual(result[-1][0], 'error')
        self.db.commit.assert_not_called()
        self.assertNotIn('private upstream details', str(result))

    async def test_commit_failure_never_reports_success(self):
        self.db.commit.side_effect = RuntimeError('private SQL content')
        result = await self.collect()
        self.assertEqual(result[-1][0], 'error')
        self.assertNotIn('saved', [event for event, _ in result])
        self.db.rollback.assert_called_once()
        self.db.close.assert_called_once()

    async def test_notification_failure_keeps_saved_result(self):
        self.service.redis_client.publish.side_effect = RuntimeError('Redis offline')
        result = await self.collect()
        self.assertEqual(result[-1][0], 'saved')
        self.db.rollback.assert_not_called()

    async def test_existing_diary_rejected_without_ai_call(self):
        self.service.chat_repository.check_today_diary_by_source.return_value = object()
        result = await self.collect()
        self.assertEqual([event for event, _ in result], ['error'])
        self.db.commit.assert_not_called()

    async def test_empty_ai_output_rejected(self):
        result = await self.collect(chunks=(' ',))
        self.assertEqual(result[-1][0], 'error')
        self.db.commit.assert_not_called()

    async def test_actual_ai_client_propagates_failure(self):
        client = GPTClient.__new__(GPTClient)
        client.async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError('private')))))
        with self.assertRaisesRegex(RuntimeError, '^AI diary streaming failed$'):
            async for _ in client.stream_gpt_response('private diary prompt'):
                self.fail('AI failure must not become a diary chunk')


class DiaryLockTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, acquired=True):
        lock = Mock(acquire=AsyncMock(return_value=acquired), release=AsyncMock(), extend=AsyncMock())
        client = Mock(aclose=AsyncMock())
        client.lock.return_value = lock
        return client, lock

    async def test_lock_releases_on_generation_failure(self):
        client, lock = self.make_client()
        with patch('app.core.operation_lock.redis.Redis', return_value=client):
            with self.assertRaises(ValueError):
                async with diary_generation_lock(7):
                    raise ValueError('generation failed')
        lock.release.assert_awaited_once()
        client.aclose.assert_awaited_once()

    async def test_busy_lock_rejects_duplicate_and_closes_client(self):
        client, lock = self.make_client(False)
        with patch('app.core.operation_lock.redis.Redis', return_value=client):
            with self.assertRaises(RuntimeError):
                async with diary_generation_lock(7):
                    self.fail('duplicate generation entered lock')
        lock.release.assert_not_awaited()
        client.aclose.assert_awaited_once()

    async def test_cleanup_failure_does_not_reverse_success(self):
        client, lock = self.make_client()
        client.aclose.side_effect = RuntimeError('connection closed')
        with patch('app.core.operation_lock.redis.Redis', return_value=client):
            async with diary_generation_lock(7):
                pass
        lock.release.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
