"""공개 정적 파일만 캐시/압축한다. 인증 API와 SSE에는 적용하지 않는다."""
from starlette.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            # 파일 이름/쿼리 버전을 바꿔 배포한다. 구형 URL도 삭제하지 않는다.
            response.headers['Cache-Control'] = 'public, max-age=86400'
        return response


def public_static(directory='static'):
    return GZipMiddleware(CachedStaticFiles(directory=directory), minimum_size=1000)
