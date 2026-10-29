from openai import OpenAI, AsyncOpenAI
from fastapi.responses import StreamingResponse
from app.config.settings import settings

# API 키 검증 및 디버깅

if not settings.openai_api_key:
    print("⚠️ 경고: OpenAI API 키가 설정되지 않았습니다. .env 파일에 OPENAI_API_KEY를 추가하세요.")
else:
    print("✅ OpenAI API 키 설정됨")

# settings에서 API 키 가져오기
client = OpenAI(api_key=settings.openai_api_key)

# 응답오는 방식 한번에 완성된 문장 보낼수 있는 api
def call_gpt(prompt: list) -> str:
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=prompt
        )
        return response.choices[0].message.content
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg:
            print("❌ OpenAI API 키 인증 실패. .env 파일에 올바른 OPENAI_API_KEY를 설정하세요.")
        elif "429" in error_msg:
            print("❌ OpenAI API 요청 한도 초과. 잠시 후 다시 시도하세요.")
        else:
            print("❌ GPT 호출 실패:", error_msg)
        raise

# 스트리밍 방식으로 gpt 의 api 호출
async def stream_gpt_response(messages: list):
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            stream=True
        )
        for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta.content:
                yield choice.delta.content
            if choice.finish_reason and choice.finish_reason != "stop":
                raise RuntimeError("AI chat response incomplete")
    except Exception:
        # 오류 문구를 정상 답변 청크로 전달하면 DB에 저장될 수 있다.
        raise RuntimeError("AI chat streaming failed") from None


# 클래스 버전 (일기 생성용)
class GPTClient:
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.async_client = AsyncOpenAI(api_key=settings.openai_api_key)

    # 응답오는 방식 한번에 완성된 문장 보낼수 있는 api
    async def call_gpt(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                print("❌ OpenAI API 키 인증 실패. .env 파일에 올바른 OPENAI_API_KEY를 설정하세요.")
            elif "429" in error_msg:
                print("❌ OpenAI API 요청 한도 초과. 잠시 후 다시 시도하세요.")
            else:
                print("❌ GPT 호출 실패:", error_msg)
            raise

    # 스트리밍 방식으로 gpt 의 api 호출
    async def stream_gpt_response(self, prompt: str):
        try:
            response = await self.async_client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                stream=True
            )
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception:
            # 오류 문장을 정상 일기로 저장하지 않도록 서비스에 실패를 전달한다.
            raise RuntimeError("AI diary streaming failed") from None
