"""이미 지난 정각 예약을 검증할 합성 계정 원본 시각만 조정한다. 시스템 시계 변경 없음."""
import os
import sys
from datetime import timedelta
from sqlalchemy.orm import Session
if os.environ.get('ENVIRONMENT')!='validation' or os.environ.get('DATABASE_URL')!='sqlite:////data/app.db':
    raise RuntimeError('Only isolated validation data may be adjusted')
from app.core.connection import engine
from app.models.db.user_model import User
from app.models.db.chat_message_model import ChatMessage
from app.models.db.daily_model import DailyJob
from app.services.daily_service import update_settings
from app.utils.time_utils import get_kst_now

name=sys.argv[1]
if not name.startswith('real-'):raise ValueError('Only the named synthetic real API account is permitted')
now=get_kst_now()
cutoff=now.replace(minute=0,second=0,microsecond=0)
with Session(engine) as db:
    user=db.query(User).filter_by(username=name).one()
    if user.nickname!='실제연결검증' or user.email!=name+'@example.org':raise ValueError('Synthetic fixture identity mismatch')
    uid=user.id
    job=db.get(DailyJob,f'{uid}:{now.date().isoformat()}:encouragement')
    if job and job.state!='skipped':raise ValueError('Only a skipped reservation may be prepared')
    rows=db.query(ChatMessage).filter_by(user_id=uid).order_by(ChatMessage.id).all()
    if len(rows)>100:raise ValueError('Unexpected fixture size')
    for i,row in enumerate(rows):row.timestamp=cutoff-timedelta(minutes=2)+timedelta(seconds=i)
    db.commit()
update_settings(engine,uid,now.hour)
print('PASS: only synthetic account message timestamps prepared before reservation; waiting for real Beat')
