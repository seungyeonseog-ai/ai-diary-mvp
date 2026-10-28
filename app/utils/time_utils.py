from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

def get_kst_now():
    """기존 SQLite 기록 형식과 호환되는 timezone-naive KST를 반환한다."""
    return datetime.now(KST).replace(tzinfo=None)

def get_kst_date_str():
    """한국 시간 기준 날짜 문자열 반환 (YYYY-MM-DD) - 더 이상 사용하지 않음"""
    return get_kst_now().strftime("%Y-%m-%d")

def get_kst_datetime_str():
    """한국 시간 기준 날짜시간 문자열 반환 (YYYY-MM-DD HH:MM:SS) - 더 이상 사용하지 않음"""
    return get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
