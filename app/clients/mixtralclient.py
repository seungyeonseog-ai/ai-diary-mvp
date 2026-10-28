import os
import requests
import json
from dotenv import load_dotenv
from app.config.settings import settings
load_dotenv()



class MixtralClient:
    """
    [인프라/외부서비스 연동]
    - MIXTRAL_ENDPOINT, MIXTRAL_TOKEN 환경변수를 읽어옵니다.
    - generate_summary()로 HTTP POST 요청만 처리.
    """

    def __init__(self, endpoint: str = None, token: str = None):
        self.endpoint = endpoint or settings.mixtral_endpoint
        self.token    = token    or settings.mixtral_token  # mixtral_api_key -> mixtral_token

        if self.endpoint is None or self.token is None:
            raise ValueError("❌ MIXTRAL_ENDPOINT 또는 MIXTRAL_TOKEN이 설정되지 않았습니다.")

    def generate_summary(self, conversation_text: str) -> str:
        print(f"[MixtralClient] ▶ generate_summary 시작: messages={len(conversation_text)}", flush=True)

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json"
        }
        payload = {
            "inputs":     conversation_text,
            "parameters": {
                "temperature": 0.2, 
                "max_new_tokens": 512,
                "do_sample": True,
                "top_p": 0.9,
                "repetition_penalty": 1.1,
                "stop": ["</s>", "[INST]", "[/INST]"]
            }
        }

        # DEBUG
        print("🧪 DEBUG | type(conversation_text):", type(conversation_text), flush=True)
        if isinstance(conversation_text, list):
            print("🧪 WARNING | conversation_text가 여전히 list입니다! join 처리가 안 됐습니다!", flush=True)
            for i, msg in enumerate(conversation_text[:3]):
                print(f"  - [{i}] role={msg.get('role')} | content={msg.get('content')}", flush=True)
        else:
            print("🧪 DEBUG | 첫 300자 내용:", conversation_text[:300], flush=True)

        try:
            print("🧪 DEBUG | payload 확인:", json.dumps(payload, indent=2, ensure_ascii=False), flush=True)
        except Exception as e:
            print("🧪 DEBUG | payload JSON 변환 실패:", str(e), flush=True)

        try:
            print(f"[MixtralClient] → POST {self.endpoint} payload keys={list(payload.keys())}", flush=True)
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=60)
            print(f"[MixtralClient] ← 상태 코드: {resp.status_code}", flush=True)
            resp.raise_for_status()

            data = resp.json()
            # ✅ 여기에 전체 응답 확인 코드 삽입

            # 응답 구조 확인
            if isinstance(data, list):
                if len(data) > 0 and 'generated_text' in data[0]:
                    summary = data[0]['generated_text'].strip()
                    return summary
                else:
                    raise KeyError("리스트 내부에 'generated_text' 키가 없습니다.")
            else:
                raise TypeError(f"예상치 못한 응답 타입입니다: {type(data)}")

        except requests.exceptions.HTTPError as http_err:
            print(f"[MixtralClient] ❌ HTTPError: {http_err} / response body: {resp.text}", flush=True)
            raise
        except requests.exceptions.RequestException as req_err:
            print(f"[MixtralClient] ❌ RequestException: {req_err}", flush=True)
            raise
        except KeyError as key_err:
            print(f"[MixtralClient] ❌ KeyError: 응답 형식이 예상과 다릅니다 -> {key_err}", flush=True)
            raise
        except Exception as err:
            print(f"[MixtralClient] ❌ 알 수 없는 오류: {err}", flush=True)
            raise 