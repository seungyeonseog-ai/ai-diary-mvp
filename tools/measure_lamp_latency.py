"""승인된 합성 입력 2회만 비교. 원문·키·응답 본문은 출력/기록하지 않는다."""
import argparse
import json
from pathlib import Path
from time import perf_counter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--approved-two', action='store_true')
    args = parser.parse_args()
    if not args.approved_two:
        parser.error('외부 AI 2회 비교 호출 승인이 필요합니다.')
    from openai import OpenAI
    from app.config.settings import settings
    from app.services.writing_stream import completed_bubbles
    if settings.openai_model != 'gpt-5.6-luna':
        raise RuntimeError('Approved model changed')
    messages = [{'role':'user','content':
        '아래 합성 대화를 읽고 짧게 공감하세요. 질문으로 끝내지 마세요. '
        '대략 2~3개 말풍선, 각각 1~2문장. JSON 객체 '
        '{"bubbles":["첫 말풍선","둘째 말풍선"]}만 반환하세요.\n'
        + json.dumps({'today_user_bubbles':'오늘 합성 프로젝트의 문서 한 페이지를 마쳤어. 조금 지쳤지만 뿌듯해.',
                      'earlier_current_writing':[], 'past_references':[]},ensure_ascii=False)}]
    # 최악의 UTF-8 바이트 수를 입력 토큰 상한으로 잡아도 합계 $0.02 미만.
    byte_bound = len(json.dumps(messages,ensure_ascii=False).encode('utf-8')) + 200
    budget_bound = 2*(byte_bound*0.20 + 1800*1.20)/1_000_000
    if budget_bound >= .02:
        raise RuntimeError('Approved cost cap exceeded')
    report={'model':settings.openai_model,'synthetic':True,'attempt_limit':2,
            'usd_upper_bound':budget_bound,'samples':[]}
    with OpenAI(api_key=settings.openai_api_key,max_retries=0,timeout=60) as client:
        for mode in ('default','none'):
            row={'reasoning':mode}; start=perf_counter();raw='';usage=None
            try:
                options={} if mode=='default' else {'reasoning_effort':'none'}
                with client.chat.completions.create(model=settings.openai_model,messages=messages,
                        stream=True,stream_options={'include_usage':True},max_completion_tokens=1800,**options) as chunks:
                    for chunk in chunks:
                        if chunk.usage:usage=chunk.usage
                        if not chunk.choices:continue
                        content=chunk.choices[0].delta.content
                        if content:
                            row.setdefault('first_content_seconds',round(perf_counter()-start,3));raw+=content
                            if completed_bubbles(raw):row.setdefault('first_bubble_seconds',round(perf_counter()-start,3))
                result=json.loads(raw)
                row['valid_bubbles']=len(result['bubbles']) if result.get('bubbles')==completed_bubbles(raw) else 0
                row['ok']=bool(row['valid_bubbles'])
            except Exception as exc:
                row.update(ok=False,error_type=type(exc).__name__)
            row['total_seconds']=round(perf_counter()-start,3)
            if usage:
                row['input_tokens']=usage.prompt_tokens;row['output_tokens']=usage.completion_tokens
                details=getattr(usage,'completion_tokens_details',None)
                row['reasoning_tokens']=getattr(details,'reasoning_tokens',None)
                row['estimated_usd']=(usage.prompt_tokens*.20+usage.completion_tokens*1.20)/1_000_000
            report['samples'].append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    output=Path('.local-check/lamp-latency-2026-11-04.json')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved aggregate report: '+str(output))


if __name__=='__main__':main()
