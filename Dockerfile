# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 matabus && useradd --uid 10001 --gid 10001 --no-create-home matabus
COPY requirements.txt ./
# 기존 Windows 가상환경은 유지하고 이미지에는 CPU wheel을 설치한다.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch==2.7.1+cpu torchvision==0.22.1+cpu torchaudio==2.7.1+cpu \
      --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt && pip check
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 static ./static
COPY --chown=10001:10001 templates ./templates
COPY --chown=10001:10001 deploy ./deploy
RUN mkdir -p /data /models /state /chroma-data \
    && chown -R 10001:10001 /data /models /state /chroma-data
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "deploy.launch", "web"]

# 합성 AI는 별도 검증 target에만 포함한다.
FROM runtime AS validation
COPY --chown=10001:10001 tests/deployment ./validation
