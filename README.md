# oh-my-krx

국내 주식 시장 데이터를 다루는 실시간 트레이딩/데이터 스택을 위한 모노레포입니다.

현재 저장소의 실구현 어댑터는 KIS 연동이며, 장기적으로는 브로커/데이터 소스를 분리 가능한 구조로 확장하는 방향을 목표로 합니다.

## 구조

```text
apps/
  api_web/      FastAPI 대시보드 진입점
  collector/    KIS live upstream을 소유하는 collector 서비스
  processor/    플레이스홀더 처리 서비스
packages/
  shared/       공용 설정 및 이벤트 헬퍼
docker/
  python-service.Dockerfile
infra/
  README.md
compose.yaml
src/            기존 구현을 호환성 유지용으로 보존
main.py         기존 CLI 진입점
web.py          새 api_web 앱 모듈로 연결하는 호환용 shim
```

## 현재 동작

- `apps/collector/service.py`는 FastAPI collector 서비스이며 기본 포트는 `8001`입니다.
- collector가 KIS live upstream subscription의 유일한 owner이며, 대시보드 이벤트를 Redpanda/Kafka 토픽으로 발행한 뒤 broker-consume 결과를 SSE로 제공합니다.
- 웹 앱(`apps.api_web.app:app`, 내부 구현은 `src/web_app.py`)은 브라우저용 UI와 API를 제공하며, 현재 활성 대시보드 경로에서는 collector HTTP/SSE만 소비합니다 (`/stream`, `/api/price-chart` relay).
- `python main.py --symbol 005930 --market krx` 경로는 기존 CLI watcher 호환용으로 유지됩니다.
- 현재 실데이터 범위는 KRX 중심이며, 이번 루프의 대시보드 broadcast core는 Redpanda/Kafka입니다. ClickHouse/processor 로직은 아직 필수 경로가 아닙니다.

## 로컬 Python 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

collector와 웹 앱을 각각 실행합니다. 로컬 대시보드 실시간 경로에는 broker가 먼저 필요하며, 별도 `BOOTSTRAP_SERVERS`를 주지 않으면 로컬 기본값은 `localhost:19092`입니다.

```bash
docker compose up -d redpanda
python -m apps.collector.service
```

다른 터미널에서:

```bash
uvicorn apps.api_web.app:app --reload
```

브라우저는 `http://127.0.0.1:8000`, collector 상태 확인은 `http://127.0.0.1:8001/health`를 사용하세요.

기존 호환 경로도 유지됩니다.

```bash
python web.py
```

단, 웹 대시보드의 실시간 `/stream`은 broker와 collector가 먼저 떠 있어야 정상 동작합니다.

## Docker Compose

```bash
docker compose up --build
```

Compose project name is explicitly set to `oh-my-krx` in `compose.yaml`, so container/network names no longer inherit an old local folder name.

현재 Docker Compose에는 다음 서비스가 포함되어 있습니다.

- `redpanda` (현재 대시보드 실시간 broadcast core)
- `clickhouse` (현 단계에서는 필수 실시간 경로가 아님)
- `collector`
- `processor`
- `api-web`

Compose 내부 서비스 간 통신은 계속 `BOOTSTRAP_SERVERS=redpanda:9092`를 사용하고, 로컬 Python 실행만 기본적으로 `localhost:19092`를 사용합니다.

현재 `collector`는 Docker 내부에서 기동되는 실데이터 수집 서비스입니다. 이 서비스가 KIS live upstream/runtime의 유일한 owner로서 `market.dashboard-events.v1` 토픽에 이벤트를 발행하고, 같은 토픽을 consumer로 읽어 `/health`, `/stream?symbol=...&market=...`, `/api/price-chart?symbol=...&market=...&interval=...` 엔드포인트를 제공합니다. `api-web`은 같은 이벤트 이름/페이로드 형태를 유지한 채 collector SSE/HTTP만 브라우저로 중계합니다. `processor`는 여전히 최소 기능 플레이스홀더입니다.

## 환경 변수

시크릿은 커밋하지 않는 로컬 `.env` 파일에 보관하세요. 공용 서비스 레이어는 다음과 같은 브로커 중립 설정을 인식합니다.

- `APP_ENV`
- `APP_HOST`
- `APP_PORT`
- `BOOTSTRAP_SERVERS`
- `CLICKHOUSE_URL`
- `SYMBOL` (`KIS_SYMBOL` 호환 fallback 유지)
- `MARKET` (`KIS_MARKET` 호환 fallback 유지)
- `POLL_INTERVAL_SECONDS`
- `COLLECTOR_BASE_URL` (`api-web`가 collector SSE 서비스에 접속할 주소, 기본값 `http://127.0.0.1:8001`)

현재 구현된 KIS 어댑터 전용 키는 다음과 같습니다.

- `KIS_APP_KEY`
- `KIS_APP_SECRET`
- `KIS_HTS_ID`
- `KIS_REST_URL`
- `KIS_WS_URL`
- `KIS_BYPASS_PROXY`

대시보드 모듈은 import 시점에 즉시 자격 증명을 검증하지 않지만, 현재 실시간 경로의 upstream owner는 collector뿐이며 collector 런타임에서 유효한 KIS 자격 증명과 Kafka-compatible broker 접속이 모두 필요합니다.

오픈소스 사용자도 필요하면 `.env.example`을 복사해 로컬 설정의 출발점으로 사용할 수 있습니다. 실제 `.env`는 로컬에만 보관하고, 자격 증명이 포함된 env 파일은 커밋하지 마세요.

## 참고 사항

- `.env`와 Docker 실행 중 생성되는 불필요한 파일은 Git에서 제외됩니다.
- `infra/`는 이후 IaC/매니페스트 용도로 남겨둔 디렉터리입니다.
- 저장소는 특정 브로커 전용 이름보다 확장 가능한 실시간 데이터 스택 구성을 지향하지만, 현재 실제 연동 구현은 KIS 기준입니다.
- 현재 단계의 웹 대시보드는 collector HTTP/SSE 소비 구조를 유지하지만, collector 내부 broadcast core는 Kafka/Redpanda입니다. 웹 앱은 활성 대시보드 경로에서 직접 Kafka 또는 KIS에 연결하지 않습니다.

## 로드맵 / TODO

- [x] 모노레포 구조 정리
- [x] 기존 `web.py`, `main.py` 실행 경로 호환 유지
- [x] Docker Compose 기반 개발 스택 구성
- [x] 공용 설정 및 이벤트 헬퍼 패키지 정리
- [x] `collector` 대시보드 live 스트림 서비스화
- [ ] `processor` 스트리밍 처리 로직 확장
- [ ] 운영 관점의 모니터링/배포 구성 보강
