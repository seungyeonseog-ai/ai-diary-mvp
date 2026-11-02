"""서재 읽기 모델. 저장된 본인 일기만, 실제 KST 날짜로 제공한다."""
from datetime import datetime,timedelta
from sqlalchemy import func
from app.models.db.study_model import DiaryReport
from app.models.db.writing_model import DiaryPhoto
from app.utils.time_utils import get_kst_now,KST


def month_range(value):
    try:
        start=datetime.strptime(value,'%Y-%m')
        end=start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1)
        return start,end
    except ValueError:
        raise ValueError('올바른 연월을 선택해 주세요.') from None


def saved_query(db,user_id,now):
    tomorrow=datetime.combine(now.date()+timedelta(days=1),datetime.min.time())
    return db.query(DiaryReport).filter(DiaryReport.user_id==user_id,DiaryReport.state=='saved',
                                        DiaryReport.timestamp.isnot(None),DiaryReport.timestamp<tomorrow)


def item(row,photo=None):
    day=row.timestamp.date()
    return {'id':row.diary_id,'date':day.isoformat(),
            'title':row.title.strip() if row.title and row.title.strip() else f'{day.month}월 {day.day}일의 기록',
            'excerpt':(row.content or '').replace('\r','').replace('\n',' ')[:120],
            'photo_url':f'/writing/diaries/{row.diary_id}/photos/{photo.id}' if photo else None}


def items(db,user_id,rows):
    ids=[row.diary_id for row in rows]
    first={}
    if ids:
        for photo in db.query(DiaryPhoto).filter(DiaryPhoto.user_id==user_id,DiaryPhoto.diary_id.in_(ids)).order_by(DiaryPhoto.created_at,DiaryPhoto.id):
            first.setdefault(photo.diary_id,photo)
    return [item(row,first.get(row.diary_id)) for row in rows]


def page_rows(query,page):
    total=query.count();pages=max(1,(total+4)//5);page=min(page,pages)
    rows=query.order_by(DiaryReport.timestamp.desc(),DiaryReport.diary_id.desc()).offset((page-1)*5).limit(5).all()
    return rows,{'total':total,'page':page,'pages':pages,'has_older':page<pages,'has_newer':page>1}


def shelf(db,user_id,page):
    now=get_kst_now();query=saved_query(db,user_id,now)
    rows,paging=page_rows(query,page)
    books=[{'state':'saved',**entry} for entry in items(db,user_id,rows)]
    while len(books)<5:
        if paging['page']==1:
            # 최신 진열에만 미래 자리. 과거 페이지에는 가짜 미래 날짜를 넣지 않는다.
            missing=len(books)-len(rows)+1
            books.append({'state':'future','date':(now.date()+timedelta(days=missing)).isoformat()})
        else:books.append({'state':'empty'})
    earliest=query.with_entities(func.min(DiaryReport.timestamp)).scalar()
    return {**paging,'server_date':now.date().isoformat(),'server_now':now.replace(tzinfo=KST).isoformat(),
            'first_month':earliest.strftime('%Y-%m') if earliest else now.strftime('%Y-%m'),'books':books}


def month_data(db,user_id,month,page):
    now=get_kst_now();month=month or now.strftime('%Y-%m')
    start,end=month_range(month)
    if start.date()>now.date():raise ValueError('아직 오지 않은 달은 선택할 수 없어요.')
    query=saved_query(db,user_id,now).filter(DiaryReport.timestamp>=start,DiaryReport.timestamp<end)
    rows,paging=page_rows(query,page)
    # 달력은 해당 월 전체의 ID/제목만 읽으며 목록 페이지 제한에 영향을 받지 않는다.
    markers=query.with_entities(DiaryReport.diary_id,DiaryReport.timestamp,DiaryReport.title).order_by(DiaryReport.timestamp,DiaryReport.diary_id).all()
    days={}
    for diary_id,when,title in markers:
        days.setdefault(when.date().isoformat(),[]).append({'id':diary_id,'title':title.strip() if title and title.strip() else f'{when.month}월 {when.day}일의 기록'})
    return {**paging,'month':month,'server_date':now.date().isoformat(),'days':days,'items':items(db,user_id,rows)}
