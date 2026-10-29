from __future__ import annotations
from app.config.settings import settings
import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from app.core.connection import get_db
from app.models.db.study_model import WeeklyAnalysisReport
from app.models.db.session_summary import GPTSessionSummary
from app.services.vector_db_service import VectorDBService
import json


logger = logging.getLogger(__name__)


class SimilarPatternService:
    """
    주간 리포트의 used_dates를 기반으로, 동일 일자(yymmdd)의 세션을 제외하고
    Dense 검색 후보를 구성하는 서비스.

    - where: user_id만 사용 (메타 yymmdd는 임베딩 시각이므로 제외 기준에 부적합)
    - 제외: session_id에서 yymmdd 추출하여 used_dates 변환셋과 매칭 시 제거
    """

    def __init__(self, vdb: Optional[VectorDBService] = None):
        self.vdb = vdb

    # ---------------------- Public API ----------------------
    def find_similar_excluding_used_dates(
        self,
        *,
        user_id: int,
        analysis_id: int,
        query: str,
        top_k: int = 150,
        min_similarity: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        - WeeklyAnalysisReport.used_dates(YYYY-MM-DD 리스트)를 yymmdd로 변환하여 제외셋 구성
        - Dense 검색(where={"user_id": user_id}) 수행
        - 결과에서 session_id의 yymmdd가 제외셋에 포함된 항목 제거
        - 필요 시 min_similarity 임계값 적용
        반환: [{ text, metadata, distance, similarity? }, ...]
        """
        if not settings.upper_reports_enabled:
            return []
        self.vdb = self.vdb or VectorDBService()
        db = next(get_db())
        try:
            report = (
                db.query(WeeklyAnalysisReport)
                .filter(WeeklyAnalysisReport.analysis_id == analysis_id, WeeklyAnalysisReport.user_id == user_id)
                .first()
            )
            if not report:
                logger.warning("similar_find: weekly report not found user_id=%s analysis_id=%s", user_id, analysis_id)
                return []

            used_dates: List[str] = report.used_dates or []


            # JSON 문자열인 경우 파싱
            if isinstance(used_dates, str):
                try:
                    used_dates = json.loads(used_dates)
                except Exception as e:
                    used_dates = []

            exclude_yymmdd: Set[str] = self._dates_to_yymmdd_set(used_dates)


            raw = self.vdb.search_similar(
                query,
                top_k=top_k,
                where={"user_id": user_id},
                return_similarity=True,
            )

            # 임계값 필터
            if min_similarity is not None:
                raw = [x for x in raw if (x.get("similarity") is not None and x["similarity"] >= float(min_similarity))]

            # used_dates(yymmdd) 제외: session_id에서 yymmdd 추출 기준
            out: List[Dict[str, Any]] = []
            excluded_count = 0
            for item in raw:
                meta = item.get("metadata") or {}
                sid = str(meta.get("session_id") or "")
                sid_yymmdd = self._session_id_to_yymmdd(sid)


                if sid_yymmdd and sid_yymmdd in exclude_yymmdd:
                    excluded_count += 1
                    continue
                out.append(item)


            return out
        finally:
            db.close()

    # ---------------------- Helpers ----------------------
    def _dates_to_yymmdd_set(self, dates: List[str]) -> Set[str]:
        """"YYYY-MM-DD" 문자열 리스트 → {"yymmdd", ...} 집합"""
        res: Set[str] = set()

        if not dates:
            return res

        for i, d in enumerate(dates):
            try:
                dt = datetime.strptime(str(d), "%Y-%m-%d")
                yymmdd = dt.strftime("%y%m%d")
                res.add(yymmdd)
            except Exception:
                pass
        return res

    def _session_id_to_yymmdd(self, session_id: str) -> Optional[str]:
        """
        session_id 포맷 가정: yymmdd_00n → 앞부분 yymmdd만 추출
        잘못된 포맷이면 None
        """
        if not session_id:
            return None
        try:
            y = session_id.split("_")[0]
            if len(y) == 6 and y.isdigit():
                return y
        except Exception:
            pass
        return None


    # ---------------------- Preview Utilities ----------------------
    def preview_similar_summaries(
        self,
        *,
        user_id: int,
        analysis_id: int,
        query: str,
        top_k: int = 50,
        min_similarity: Optional[float] = None,
    ) -> List[Dict[str, str]]:
        """
        유사 검색 결과에서 session_id를 뽑고, 해당 세션의 요약(summary)만 출력 및 반환.
        반환 형식: [{"session_id": "yymmdd_00n", "summary": "..."}, ...]
        """
        hits = self.find_similar_excluding_used_dates(
            user_id=user_id,
            analysis_id=analysis_id,
            query=query,
            top_k=top_k,
            min_similarity=min_similarity,
        )

        # session_id 추출(입력 순서 유지, 중복 제거)
        seen: Set[str] = set()
        session_ids: List[str] = []
        for h in hits:
            meta = h.get("metadata") or {}
            sid = str(meta.get("session_id") or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            session_ids.append(sid)

        if not session_ids:
            return []

        db = next(get_db())
        try:
            rows = (
                db.query(GPTSessionSummary)
                .filter(
                    GPTSessionSummary.user_id == user_id,
                    GPTSessionSummary.session_id.in_(session_ids),
                )
                .all()
            )

            # session_id → summary 매핑
            sid_to_summary: Dict[str, str] = {r.session_id: (r.summary or "") for r in rows}

            out: List[Dict[str, str]] = []
            for sid in session_ids:
                summary = sid_to_summary.get(sid, "")
                out.append({"session_id": sid, "summary": summary})
                # 콘솔 보기 용도
                try:
                    pass  # 개인 콘텐츠를 로그에 출력하지 않는다.
                except Exception:
                    pass
            return out
        finally:
            db.close()

    # ---------------------- SessionId Utilities ----------------------
    def _extract_session_ids(self, hits: List[Dict[str, Any]]) -> List[str]:
        """유사 검색 결과 리스트에서 session_id만 순서 유지+중복 제거하여 추출"""
        seen: Set[str] = set()
        session_ids: List[str] = []
        for h in hits or []:
            meta = h.get("metadata") or {}
            sid = str(meta.get("session_id") or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            session_ids.append(sid)
        return session_ids

    def get_similar_session_ids(
        self,
        *,
        user_id: int,
        analysis_id: int,
        query: str,
        top_k: int = 150,
        min_similarity: Optional[float] = None,
    ) -> List[str]:
        """
        used_dates(yymmdd) 제외 및 임계값(min_similarity) 적용된 Dense 유사 결과에서
        session_id만 추출해 반환.
        """
        hits = self.find_similar_excluding_used_dates(
            user_id=user_id,
            analysis_id=analysis_id,
            query=query,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        return self._extract_session_ids(hits)
