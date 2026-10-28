# MVP baseline — 2026-10-28

This snapshot preserves the current implementation before the next deployment-readiness review. It is not a claim that deployment, analytics integration, or beta validation is complete.

## Agreed product scope

- MVP: the agreed features in Space, Chat, and Library.
- Garden, personality report, and other unfinished features are planned to show “Coming soon”; that UI change is not part of this baseline.
- Security findings affecting any route remain in scope, including account isolation, WebSocket authentication, and credential exposure.
- Repeated retrieval of the same session and query-sensitive sparse recall are recorded improvement candidates. Session deduplication is not implemented in this snapshot.

## Current verification

- Python regression tests: 27 passed.
- Authentication frontend scenarios: 5 passed.
- Diary streaming frontend scenarios: 3 passed.
- Chroma's existing index was readable after using a relative data path on Windows. Retrieval included the stored cat memory. Multiple documents from one session can still produce repeated prompt summaries.
- These are development checks, not evidence of completed real-user beta testing.

## Services required locally

Run commands from the project directory with the existing virtual environment and explicitly configured database/connection settings:

1. Redis-compatible service, currently on `localhost:6379`.
2. Chroma on `127.0.0.1:8001`. In this Windows environment, use a relative data path:

   ```powershell
   .\.venv-local\Scripts\chroma.exe run --path .local-check\chroma_db --host 127.0.0.1 --port 8001
   ```

3. FastAPI on `127.0.0.1:8000`.
4. Celery worker using the same database, Redis broker, Chroma host, and Chroma port.
5. One Celery Beat scheduler using that same environment.

Web and worker currently share the local SQLite database under `.local-check/test.db`. Setting a different database URL can make an otherwise running service appear to lose accounts/history. Do not recreate or copy private data merely to start this code snapshot.

The virtual environment, model cache, SQLite databases, Chroma indexes, service logs, credentials, and Beat state are deliberately excluded from Git. A source snapshot is not a backup of user data. Data backup/restore and repeatable environment setup remain deployment work.

## Known remaining work

- Confirm the detailed provided/coming-soon feature list.
- Select a hosting/storage architecture before assuming local shared SQLite/FTS files can be shared across hosted services.
- Complete the core journey, account isolation, failure, restart, and persistence review; explain findings before further app changes.
- Review the Dockerfile and health checks separately when choosing the deployment method. Their presence does not establish a working container build.
- Define PostHog events with product questions and privacy boundaries, then implement and validate collection.
- Conduct a limited beta and an evidence-based improvement/retest.
