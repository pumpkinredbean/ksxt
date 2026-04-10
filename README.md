# KIS Program Trade Realtime

실시간 KIS 프로그램 트레이딩 스택을 위한 모노레포입니다.

## 구조

```text
apps/
  api_web/      FastAPI 대시보드 진입점
  collector/    플레이스홀더 수집 서비스
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

- `python web.py`로 여전히 대시보드를 실행할 수 있습니다.
- `python main.py --symbol 005930 --market krx`로 여전히 CLI watcher를 실행할 수 있습니다.
- 대시보드 진입 경로는 이제 `apps/api_web/app.py`이지만, 내부적으로는 기존 `src/web_app.py` 구현을 계속 재사용합니다.

## 로컬 Python 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python web.py
```

실행 후 `http://127.0.0.1:8000`에 접속하세요.

## Docker Compose

```bash
docker compose up --build
```

현재 Docker Compose에는 다음 서비스가 포함되어 있습니다.

- `redpanda`
- `clickhouse`
- `collector`
- `processor`
- `api-web`

현재 `collector`와 `processor`는 의도적으로 최소 기능만 갖춘 플레이스홀더입니다. 두 서비스는 Docker 내부에서 기동되고, 모노레포의 공용 설정을 읽으며, 공유 이벤트 헬퍼를 사용해 heartbeat 형태의 이벤트를 발행합니다. 현재 저장소 구조와 서비스 간 연결 방식을 맞춰 두기 위한 구성입니다.

## 환경 변수

시크릿은 커밋하지 않는 로컬 `.env` 파일에 보관하세요. 현재 KIS 연동에서 일반적으로 사용하는 키는 다음과 같습니다.

- `KIS_APP_KEY`
- `KIS_APP_SECRET`
- `KIS_HTS_ID`
- `KIS_REST_URL`
- `KIS_WS_URL`

공용 서비스 기본값으로는 아래 변수들도 인식합니다.

- `BOOTSTRAP_SERVERS`
- `CLICKHOUSE_URL`
- `KIS_SYMBOL`
- `KIS_MARKET`
- `POLL_INTERVAL_SECONDS`

대시보드 모듈은 이제 import 시점에 즉시 자격 증명을 검증하지 않지만, 실시간 KIS 호출을 수행하려면 런타임에 유효한 KIS 자격 증명이 여전히 필요합니다.

오픈소스 사용 시 참고: 필요하면 `.env.example`을 복사해 로컬 설정의 출발점으로 사용하고, 실제 `.env`는 반드시 로컬에만 보관하세요. 자격 증명이 포함된 env 파일은 절대 커밋하면 안 됩니다.

## 참고 사항

- 오픈소스 저장소 위생을 위해 `.env`와 Docker 관련 잡음 파일은 무시됩니다.
- `infra/`는 이후 IaC/매니페스트 용도로 남겨둔 디렉터리입니다.

## 로드맵 / TODO

- [x] 모노레포 구조 정리
- [x] 기존 `web.py`, `main.py` 실행 경로 호환 유지
- [x] Docker Compose 기반 개발 스택 구성
- [x] 공용 설정 및 이벤트 헬퍼 패키지 정리
- [ ] `collector` 실데이터 수집 로직 확장
- [ ] `processor` 스트리밍 처리 로직 확장
- [ ] 운영 관점의 모니터링/배포 구성 보강
