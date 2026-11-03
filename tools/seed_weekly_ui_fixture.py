"""승인된 gptgpt 주간 UI 검증 자료만 추가. 외부 AI/작업 등록/기존 행 수정 없음."""
import argparse,hashlib,json,sqlite3
from datetime import datetime,timedelta,timezone
from pathlib import Path
from app.services.weekly_cycle_ai import validate_daily,validate_weekly

ROOT=Path(__file__).resolve().parents[1]
TABLES=('users','chat_messages','diary_reports','diary_analysis_reports','weekly_analysis_reports','result_notices','analysis_jobs','weekly_clocks','daily_settings')
def encoded(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def digest(db,table,maximum):
    return hashlib.sha256(encoded(db.execute(f'SELECT * FROM {table} WHERE rowid<=? ORDER BY rowid',(maximum,)).fetchall()).encode()).hexdigest()
def seed(account,apply=False):
    if account!='gptgpt':raise ValueError('승인된 gptgpt 계정만 허용')
    path=(ROOT/'.local-check/test.db').resolve(strict=True)
    now=datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    end=datetime(2026,11,2);start=end-timedelta(days=6)
    if end.date()>=now.date():raise ValueError('완료된 과거기간만 허용')
    daily=[
      {'emotions':['피곤함','걱정','기대'],'scores':[-.5,-.2,.1],'keywords':['일정 정리','남은 업무','잠깐의 휴식'],'keyword_descriptions':['화면 검증용 합성 자료: 해야 할 일을 정리했어요.','화면 검증용 합성 자료: 일이 남아 걱정되는 마음을 살펴봤어요.','화면 검증용 합성 자료: 잠시 쉬어갈 시간을 생각했어요.'],'summary':'[화면 검증용 합성 자료] 해야 할 일이 겹쳐 피곤하고 걱정됐어요. 일정을 정리하며 잠깐 쉬어갈 여유를 찾고 싶었던 하루예요.'},
      {'emotions':['차분함','만족감','피로'],'scores':[.3,.2,-.1],'keywords':['산책','따뜻한 차','작은 마무리'],'keyword_descriptions':['화면 검증용 합성 자료: 짧은 산책으로 마음을 가라앉혔어요.','화면 검증용 합성 자료: 따뜻한 차를 마시며 쉬었어요.','화면 검증용 합성 자료: 작은 일을 마친 만족감을 느꼈어요.'],'summary':'[화면 검증용 합성 자료] 짧은 산책과 따뜻한 차로 마음이 차분해졌어요. 피로는 조금 남았지만 작은 일을 마친 만족감이 있었어요.'},
      {'emotions':['기쁨','안도감','기대'],'scores':[.5,.3,.1],'keywords':['친구와 대화','고민 나누기','다음 주 계획'],'keyword_descriptions':['화면 검증용 합성 자료: 친구와 편안히 이야기를 나눴어요.','화면 검증용 합성 자료: 고민을 나누며 마음의 부담이 줄었어요.','화면 검증용 합성 자료: 다음 주에 해볼 작은 일을 정했어요.'],'summary':'[화면 검증용 합성 자료] 친구와 고민을 나누며 안도감과 기쁨을 느꼈어요. 다음 주에 해볼 작은 일을 정하며 기대하는 마음으로 하루를 마무리했어요.'}
    ]
    dates=[(start+timedelta(days=i)).date().isoformat() for i in (0,3,6)]
    emotion={'trend':'[화면 검증용 합성 자료] 피곤함과 걱정이 있던 날에서 작은 휴식과 마무리를 거쳐, 대화 속 기쁨과 안도감으로 흐름이 바뀌었어요. 기록이 없는 날짜의 감정은 추정하지 않았어요.','dominant_emotion':'[합성] 안도감과 차분함','recommendation':'[화면 검증용 합성 자료] 일이 겹칠 때는 작은 단위로 나누고, 짧은 산책이나 믿을 수 있는 사람과의 대화로 쉬어가 보세요.'}
    keyword={'main_themes':['일정과 마무리','산책과 휴식','친구와의 대화'],'trending_keywords':['정리','휴식','관계'],'recurring_patterns':['[합성] 해야 할 일을 정리하며 부담을 줄이려 했어요.','[합성] 짧은 휴식과 대화가 마음을 가볍게 했어요.'],'insights':'[화면 검증용 합성 자료] 일정 정리, 산책, 친구와의 대화처럼 작은 행동들이 마음을 돌보는 계기가 되었어요. 세 날짜의 자료만으로 한 주 전체를 단정하지 않았어요.'}
    overall={'overall_assessment':'[화면 검증용 합성 자료] 부담이 있었던 시작과 달리, 작은 일을 마무리하고 충분히 쉬며 사람과 연결되는 경험이 도움이 된 기간이에요. 서로 다른 세 날짜의 기록을 토대로 돌아본 예시입니다.'}
    for data in daily:validate_daily(data)
    for kind,data in [('emotion',emotion),('keyword',keyword),('comprehensive',overall)]:validate_weekly(kind,data)
    with sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=30) as db:
        db.execute('PRAGMA foreign_keys=ON')
        row=db.execute('SELECT id FROM users WHERE username=?',(account,)).fetchone()
        if row is None:raise ValueError('계정 없음')
        uid=row[0]
        for table in ('chat_messages','diary_reports','diary_analysis_reports','weekly_analysis_reports','analysis_jobs','weekly_clocks'):
            if db.execute(f'SELECT count(*) FROM {table} WHERE user_id=?',(uid,)).fetchone()[0]:raise ValueError('대상 계정에 자료가 있어 추가하지 않음: '+table)
        if not apply:
            print(encoded({'mode':'dry-run','account':account,'period':[start.date().isoformat(),end.date().isoformat()],'dates':dates,'daily':3,'weekly':1,'notices':1,'external_ai':0}));return
        stamp=now.strftime('%Y%m%d-%H%M%S-%f');backup=ROOT/'.local-check'/('gptgpt-weekly-before-'+stamp+'.db')
        with sqlite3.connect(backup) as target:db.backup(target)
        db.execute('BEGIN IMMEDIATE')
        try:
            # 잠금 획득 후 계정과 원래 행 보존을 다시 확인한다.
            for table in ('chat_messages','diary_reports','diary_analysis_reports','weekly_analysis_reports','analysis_jobs','weekly_clocks'):
                if db.execute(f'SELECT count(*) FROM {table} WHERE user_id=?',(uid,)).fetchone()[0]:raise ValueError('대상 상태 변경됨: '+table)
            baseline={t:db.execute(f'SELECT coalesce(max(rowid),0) FROM {t}').fetchone()[0] for t in TABLES}
            hashes={t:digest(db,t,m) for t,m in baseline.items()}
            ids=[]
            for day,data in zip(dates,daily):
                cursor=db.execute('INSERT INTO diary_analysis_reports(user_id,emotions,scores,keywords,keyword_descriptions,summary,timestamp,date_str,is_used_in_weekly) VALUES(?,?,?,?,?,?,?,?,1)',(uid,encoded(data['emotions']),encoded(data['scores']),encoded(data['keywords']),encoded(data['keyword_descriptions']),data['summary'],day+' 00:00:00.000000',day))
                ids.append(cursor.lastrowid)
            overall.update({'_source_report_ids':ids,'_schema_version':2,'_test_fixture':'gptgpt-weekly-ui-20261103'})
            cursor=db.execute('INSERT INTO weekly_analysis_reports(user_id,week_start_date,week_end_date,used_dates,emotion_trend_result,keyword_pattern_result,comprehensive_pattern_result,timestamp) VALUES(?,?,?,?,?,?,?,?)',(uid,start.isoformat(' '),end.isoformat(' '),encoded(dates),encoded(emotion),encoded(keyword),encoded(overall),now.isoformat(' ')))
            weekly=cursor.lastrowid
            notice=db.execute('INSERT INTO result_notices(user_id,kind,result_id,created_at) VALUES(?,?,?,?)',(uid,'weekly',weekly,now.isoformat(' '))).lastrowid
            assert all(digest(db,t,m)==hashes[t] for t,m in baseline.items()),'기존 행 보존 실패'
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            db.commit()
        except BaseException:db.rollback();raise
        manifest={'account':account,'period':[dates[0],dates[-1]],'daily_ids':ids,'weekly_id':weekly,'notice_id':notice,'backup':str(backup),'original_rows_unchanged':True,'external_ai':0,'created_at_kst':now.isoformat()}
        out=ROOT/'.local-check'/('gptgpt-weekly-fixture-'+stamp+'.json');out.write_text(encoded(manifest),encoding='utf-8')
        print(encoded({**manifest,'manifest':str(out)}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--account',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args();seed(args.account,args.apply)
