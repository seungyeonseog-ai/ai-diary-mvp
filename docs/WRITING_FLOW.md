# 작성·초안 기반 — 3번 구현

2026-11-02. 새 제품 화면은 4번에서 연결한다. 기존 `/chat`, `/study` 응답 계약은 유지하며 `/writing` API를 추가한다.

## 데이터와 원본 범위

- `diary_reports`: 기존 ID/content/source_type/timestamp 보존. `title`, `state=draft/saved/discarded`, `version`, `updated_at` 추가. 기존 일기는 saved, 제목은 빈 문자열로 보존하며 AI로 제목을 소급 생성하지 않는다.
- `writings`: 사용자·원본 KST 날짜·작성 ID·폐기 시각·일기 ID. 기술 세션과 다르다. 같은 날짜에 진행 중인 작성은 재사용하고 폐기 후 새 작성 ID를 만든다.
- `writing_messages`: 작성 ID와 `chat_messages.id` 연결. 클라이언트 입력 ID로 중복 저장 방지. 원본 사용자/AI 대화는 기존 채팅 테이블에 보존한다.
- `writing_operations`: 사용자별 요청 ID·종류(lamp/diary)·고정된 사용자 원본 ID·사용량·상태·생성 결과·5분 lease. API/AI 작업 중에는 DB 쓰기 잠금을 잡지 않는다. timeout은 240초다. 같은 ID 재시도는 차감/원본을 재사용한다. 다른 탭의 동시 요청은 409.
- `summary_ranges`: 날짜·응원전/자정·성공 원본 ID와 요약. 내부 함수로 성공한 범위를 영속 관리하며, 실제 스케줄러/검색/임베딩 교체는 6번이다.
- `diary_photos`: 소유자·일기 연결·요청 ID·형식·해시·원본 bytes. 본문과 같은 SQLite DB에 저장한다. 조회 시 bytes는 지연 로딩한다. 베타 규모에 맞춘 구현이며 데이터가 커지면 비공개 파일 저장소 전환을 별도 검토한다.
- 사용자 `registered_at`: 신규 가입 때 KST 기록. 신규 체험은 이 시각부터 정확히 7일. 가입 시각 없는 기존 계정은 합의대로 이행 시 `trial_started_at`부터 7일. 재이행으로 시작일을 바꾸지 않는다.

일기는 현재 작성의 USER1/USER2 원문만 사용한다. AI 답변·요약·검색 기억은 넣지 않는다. A 폐기 후 B 작성이면 새 일기는 B만 사용한다. 원본 A는 지우지 않으므로 일기 폐기와 무관하게 응원/하루 요약/장기 기억/대화 기반 분석에 남는다. 폐기를 전역 제외 조건으로 사용하지 않는다. 이미 생성한 응원은 이 API가 수정/삭제하지 않는다.

현재 새 `/writing`으로 입력한 대화만 작성에 연결한다. 과거 채팅을 현재 작성으로 임의 편입하거나 기존 일기와 대화의 관계를 추측해 연결하지 않는다. 기존 일기 9건은 저장 일기 조회/수정/폐기 API에서 그대로 관리한다. 구형 UI는 단계적으로 대체할 대상이며 새 작성 복원/초안 조작은 새 API를 사용한다.

## API 계약

모두 기존 Bearer 인증 사용. 사용자 ID/원본 ID/작성일은 서버에서 결정한다. 요청 본문의 여분 필드는 거부한다.

| 경로 | 용도 |
|---|---|
| POST `/writing` | 오늘 작성 생성 또는 현재 작성 복원 |
| GET `/writing/{id}` | 해당 작성의 화면용 말풍선·초안·사용량 조회. 폐기는 말풍선/일기를 숨김 |
| POST `/writing/{id}/messages` | `{request_id,message}`로 사용자 말풍선 원본 저장 |
| POST `/writing/{id}/generate/lamp` | `{request_id}`로 아직 제출하지 않은 묶음의 짧은 AI 답 생성·저장 |
| POST `/writing/{id}/generate/diary` | `{request_id}`로 현재 작성 사용자 원문 전체의 제목/본문 초안 생성 |
| DELETE `/writing/{id}` | 작성 폐기·진행 요청 무효화·연결 일기 폐기. 원본 채팅 보존 |
| GET `/writing/diaries` | saved만 조회. month=YYYY-MM, offset/limit 지원 |
| GET `/writing/diaries/{id}` | 소유자의 초안/저장 일기 상세·사진 URL |
| PATCH `/writing/diaries/{id}` | `{version,title,body}`. 같은 행 수정, 오래된 버전은 409 |
| POST `/writing/diaries/{id}/save` | `{version}`. 같은 행 saved 전환, 응답 유실 재시도 중복 저장 없음 |
| DELETE `/writing/diaries/{id}` | 과거 포함 폐기. 오늘만 새 작성 가능 |
| POST `/writing/diaries/{id}/photos` | raw 사진 bytes, query version/request_id. 최대 3장·장당 20MiB(화면 문구 20MB), JPG/PNG/WebP 실형식 확인 |
| GET `/writing/diaries/{id}/photos/{photo_id}` | 인증·소유권·일기 연결 확인, private/no-store |
| DELETE `/writing/diaries/{id}/photos/{photo_id}` | JSON version으로 사진 삭제·일기 버전 증가 |

일기 생성 후에는 직접 편집하거나 폐기 후 새로 작성한다. 과거 일기도 편집/사진/폐기 가능하지만 날짜를 지정한 과거 재생성 API는 제공하지 않는다. 23:59:55 입력은 전날 원본, 00:00:05 입력은 새날 원본이다. 날짜 변경 중 완료된 요청은 원래 작성 날짜를 유지한다.

## 한도·실패·프론트 연결

- 전등 제출 작업 기준 기본 1회. 체험 중 추가 2회/KST 날짜. 폐기는 새 작성의 기본 1회를 다시 제공하며 당일 추가 사용량을 복구하지 않는다. 자정에는 날짜별 집계가 분리된다.
- 진행 중 작업도 사용량을 예약한다. 실패 재시도는 같은 request_id를 사용해 추가 차감 없이 재처리한다. 다른 ID로 임의 환급/새 기회를 만들지 않는다. 실패에 대한 별도 환급 상품 정책은 아직 확정하지 않았으며 구현된 예약/같은 ID 재시도와 구분한다.
- 생성된 결과는 작업 기록에 먼저 체크포인트 저장. 뒤의 초안 생성/응답 저장 실패는 체크포인트가 있으면 AI 재호출 없이 저장만 재시도한다. 체크포인트 자체를 DB 장애로 저장하지 못한 경우까지 생성 결과 영속 보존을 보장하지 않는다. 입력 원본은 보존된다.
- 409는 중복 진행·버전 충돌·입력/한도 조건 안내, 503은 입력 보존 후 같은 요청 재시도, 사진 413/415는 크기/형식 안내다. 본문/성공 사진은 그대로 유지한다.
- 새 lamp/diary API는 현재 완성 결과 JSON을 반환한다. 4번에서 완성 말풍선부터 순차 표시할 스트림 계약과 확인 모달·대기·재시도 UI를 연결한다. 현재 endpoint만으로 새 UX 완료로 판정하지 않는다. 기존 텍스트/SSE 채팅은 바꾸지 않는다.
- 새 lamp 프롬프트는 짧은 공감과 질문 마무리 금지를 적용했다. 기억 검색/새 UI와의 최종 연결·출력 품질 평가는 4번 후속 범위다. JSON 파싱/출력 중단/빈 답은 정상 저장하지 않는다.

## 이행·복구

저장소 루트, 기존 `.venv-local`, UTF-8 환경에서 실행한다.

```
python -B -m tools.migrate_writing --database .local-check/test.db
```

도구는 SQLite backup API로 `.local-check/writing-backup-시각.db`를 먼저 생성한다. 기존 컬럼/원문을 삭제하지 않고 필드/테이블만 추가한다. 앱 시작은 이행 누락을 검사하므로 구버전 DB로 조용히 실행하지 않는다. 이행 재실행은 체험 시작/초안 상태를 초기화하지 않는다. 원래 컬럼들의 정렬 해시와 integrity_check로 기존 자료 보존을 검사했다. 기존 고유 제약(user_id,timestamp)은 유지한다.

복구가 필요하면 먼저 FastAPI/Worker/Beat 등 DB 쓰기 프로세스를 정지하고 실제 DB 경로와 백업을 대조한다. 백업을 보존한 채 별도 복구본을 만들고 해당 코드 버전과 함께 검증한다. 실행 중 DB를 덮어쓰거나 과거 백업으로 이후 사용자 기록을 조용히 삭제하지 않는다. 이 도구는 자동 롤백/전체 데이터 삭제 명령을 제공하지 않는다.

## 검증 구분

- `tests/test_writing_flow.py`: 실제 라우터/SQLite, AI 어댑터만 합성 대체. 원본/초안/상태/사용량/동시 요청/사진/계정/날짜·요약 범위/백업 검사.
- `tests/browser/writing_server.py` + `writing.html`: 별도 DB·합성 계정·실제 로그인·브라우저 HTTP. `WRITING_LIVE_AI=approved-two`로 명시한 실행에서만 실제 AI 최대 2회. 이 변수는 테스트 실행 전 별도 사용자 승인을 대신하지 않는다.
- 실제 제품 UI 연결/이미지 배치/완성 말풍선 점진 표시/3분 요약 교체/주간 3탭은 이번 3번 기반 구현과 별도다.
