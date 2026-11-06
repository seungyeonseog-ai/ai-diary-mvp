"""주간용 AI 경계. 내부 자동 재시도 없이 논리 작업별 복구한다."""
import json,math
from app.prompt.diary_analysis_report_prompt import diary_analysis_prompt

last_usage=None


def validate_daily(result):
    if not isinstance(result,dict):raise ValueError('Invalid daily analysis')
    for key in ('emotions','keywords','keyword_descriptions'):
        if not isinstance(result.get(key),list) or not result[key] or any(not isinstance(x,str) or not x.strip() for x in result[key]):raise ValueError('Invalid daily text arrays')
    scores=result.get('scores')
    if not isinstance(scores,list) or len(scores)!=len(result['emotions']) or any(type(x) not in (int,float) or not math.isfinite(x) or not -1<=x<=1 for x in scores):raise ValueError('Invalid daily scores')
    if len(result['keywords'])!=len(result['keyword_descriptions']) or not isinstance(result.get('summary'),str) or not result['summary'].strip():raise ValueError('Invalid daily description')
    return result


def validate_weekly(kind,result):
    if not isinstance(result,dict):raise ValueError('Invalid weekly object')
    keys={'emotion':['trend','dominant_emotion','recommendation'],'keyword':['insights'],'comprehensive':['overall_assessment']}[kind]
    if any(not isinstance(result.get(key),str) or not result[key].strip() for key in keys):raise ValueError('Invalid weekly text')
    if kind=='keyword':
        for key in ('main_themes','recurring_patterns'):
            if not isinstance(result.get(key),list) or any(not isinstance(x,str) for x in result[key]):raise ValueError('Invalid weekly keywords')
    # 레이더 전용 점수를 신규 결과에 저장하지 않는다.
    return {key:value for key,value in result.items() if key not in ('life_satisfaction','stress_level','social_activity','emotion_stability')}


def generate(kind,data):
    global last_usage
    from openai import OpenAI
    from app.config.settings import settings
    if kind=='daily':
        system='대상 날짜의 사용자 대화를 감정적으로 분석하세요. 자료에 없는 사건을 만들지 말고 JSON만 반환하세요.'
        user=diary_analysis_prompt.format(content=data)
    else:
        shapes={'emotion':{'trend':'감정 흐름','dominant_emotion':'눈에 띈 감정','key_changes':['변화'],'recommendation':'따뜻한 제안'},
                'keyword':{'main_themes':['주요 주제'],'trending_keywords':['키워드'],'recurring_patterns':['반복된 이야기'],'insights':'인사이트'},
                'comprehensive':{'overall_mood':'전체 분위기','key_achievements':['성취'],'challenges':['어려움'],'growth_areas':['성장'],'weekly_theme':'주제','next_week_focus':'다음 제안','overall_assessment':'한 주를 돌아보는 설명'}}
        system='입력에 명시된 기간 중 실제 대화 분석이 있는 날짜만 근거로 따뜻하게 돌아보세요. 빈 날짜를 추측하거나 심리 진단하지 마세요. 레이더 점수는 생성하지 마세요. JSON만 반환하세요.'
        user=json.dumps({'input':data,'response_shape':shapes[kind]},ensure_ascii=False)
    with OpenAI(api_key=settings.openai_api_key,max_retries=0,timeout=60) as client:
        response=client.chat.completions.create(model=settings.openai_model,messages=[{'role':'system','content':system},{'role':'user','content':user}],max_completion_tokens=1200)
    last_usage={'input':response.usage.prompt_tokens,'output':response.usage.completion_tokens}
    if response.choices[0].finish_reason!='stop':raise ValueError('Incomplete weekly AI result')
    result=json.loads(response.choices[0].message.content)
    return validate_daily(result) if kind=='daily' else validate_weekly(kind,result)
