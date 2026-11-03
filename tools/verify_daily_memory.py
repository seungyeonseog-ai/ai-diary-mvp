"""검증 DB의 합성 요약만 별도 Chroma 컬렉션/FTS에 저장·조회. 유료 API 없음."""
import argparse,json,os
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch


def verify(database):
    path=Path(database).resolve(strict=True)
    if not path.parent.name.startswith('daily-ai-'):
        raise ValueError('합성 daily-ai 검증 DB만 허용')
    os.environ['DATABASE_URL']='sqlite:///'+path.as_posix()
    from sqlalchemy.orm import Session
    from app.core.connection import engine
    from app.models.db.user_model import User
    from app.models.db.daily_model import DailyJob
    from app.models.db.session_log import SessionLog
    from app.models.db.session_summary import GPTSessionSummary
    from app.services.vector_db_service import VectorDBService
    from app.services.sparse_service import SparseIndexService
    from app.services.hybrid_memory_service import HybridMemoryService
    from app.services import daily_ai
    collection='daily_verify_'+uuid4().hex
    dense=VectorDBService(collection_name=collection)
    sparse=SparseIndexService(str(path.parent/'memory_fts.db'))
    with Session(engine) as db:jobs=db.query(DailyJob).filter(DailyJob.summary_result.isnot(None)).all()
    try:
        for job in jobs:
            for _ in range(2):
                # 각 호출마다 별도 연결. 기본 인덱스/기존 컬렉션에는 쓰지 않는다.
                with patch('app.services.vector_db_service.VectorDBService',return_value=dense),patch(
                    'app.services.sparse_service.SparseIndexService',side_effect=lambda:SparseIndexService(str(path.parent/'memory_fts.db'))):
                    daily_ai.index_summary(job.user_id,'day_'+job.source_date.replace('-','')+'_'+job.phase,job.source_date,job.summary_result)
        total=sparse.conn.execute('SELECT count(*) FROM docs_fts').fetchone()[0]
        unique=sparse.conn.execute('SELECT count(DISTINCT doc_id) FROM docs_fts').fetchone()[0]
        count=dense.vectorstore._collection.count()
        hybrid=HybridMemoryService(sparse=sparse,dense=dense)
        with patch('app.services.hybrid_memory_service.HybridMemoryService',return_value=hybrid):
            found=daily_ai.search(engine,1,jobs[0].summary_result['summary'],'2026-11-04')
            today=daily_ai.search(engine,1,jobs[0].summary_result['summary'],'2026-11-03')
            other=daily_ai.search(engine,2,jobs[0].summary_result['summary'],'2026-11-04')
        assert total==unique==count and found and not today and not other
        result={'collection':collection,'sparse_count':total,'dense_count':count,'no_duplicate_ids':total==unique,
                'past_found':len(found),'today_excluded':not today,'other_account_empty':not other,'external_ai_calls':0}
        (path.parent/'memory-report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:sparse.conn.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);verify(p.parse_args().database)
