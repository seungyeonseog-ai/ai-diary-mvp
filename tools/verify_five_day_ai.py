"""승인된 합성 3일 자료로 주간 AI 3회만 확인. 원본 DB 접근 없음."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--approved-three-calls', action='store_true')
    args = parser.parse_args()
    if not args.approved_three_calls:
        parser.error('실제 AI 3회 승인 필요')
    from app.config.settings import settings
    from app.services import weekly_cycle_ai as ai
    if settings.openai_model != 'gpt-5.6-luna':
        raise RuntimeError('승인 모델과 다름')
    days = [{'date': f'2026-11-0{day}', 'emotions': ['기쁨', '피곤'], 'scores': [.6, -.2],
             'keywords': ['정리'], 'keyword_descriptions': ['작은 일을 마쳤어요.'],
             'summary': '합성 검증: 서류를 정리하고 짧게 산책하며 하루를 돌아봤어요.'}
            for day in (3, 4, 5)]
    result, calls = {}, []
    output = Path('.local-check/five-day-ai-result.json')
    if output.exists():
        raise RuntimeError('기존 실행 결과 있음: 승인 호출 중복 방지')
    for kind in ('emotion', 'keyword', 'comprehensive'):
        payload = {'days': days, 'period_start': '2026-11-03', 'period_end': '2026-11-07',
                   'period_days': 5, 'previous': result}
        if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 12000:
            raise RuntimeError('합성 입력 상한 초과')
        calls.append({'kind': kind, 'started': True})
        output.write_text(json.dumps({'calls': calls}), encoding='utf-8')
        result[kind] = ai.generate(kind, payload)
        calls[-1]['usage'] = ai.last_usage
        output.write_text(json.dumps({'days': days, 'result': result, 'calls': calls}, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'model': settings.openai_model, 'calls': calls, 'validated': True}))


if __name__ == '__main__': main()
