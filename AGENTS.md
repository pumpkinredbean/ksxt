# AGENTS.md

## 빠른 명령
- 가상환경/의존성: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- 대시보드 실행: `python web.py`
- API 엔트리 직접 실행: `uvicorn apps.api_web.app:app --reload`
- CLI watcher 실행: `python main.py --symbol 005930 --market krx`
- Compose 스택 실행: `docker compose up --build`
- 플레이스홀더 서비스 확인: `python -m apps.collector.service` / `python -m apps.processor.service`

## 현재 저장소 현실
- 모노레포 진입점은 `apps/`, `packages/`, `src/`, `compose.yaml` 기준으로 본다.
- 대시보드 엔트리는 `apps/api_web/app.py`지만 실제 FastAPI 앱 구현은 `src/web_app.py`를 재사용한다.
- `collector`, `processor`는 아직 실서비스가 아니라 heartbeat 이벤트를 출력하는 플레이스홀더다.
- 공용 설정/이벤트 계약은 `packages/shared/config.py`, `packages/shared/events.py`에 있다.
- Docker Compose 기준 핵심 스택은 `redpanda`, `clickhouse`, `collector`, `processor`, `api-web`이다.

## 디렉터리 감각
- `apps/api_web`: 배포/실행용 웹 엔트리
- `apps/collector`: 수집 서비스 자리
- `apps/processor`: 처리 서비스 자리
- `packages/shared`: 서비스 간 공유 설정/이벤트 헬퍼
- `src`: 기존 구현 재사용 레이어. 웹 UI와 KIS websocket 로직의 실제 본체가 있다.

## 작업 원칙
- 먼저 실행 명령과 엔트리포인트를 확인하고, 그 다음에 코드를 바꾼다.
- 웹 동작 변경이 필요하면 `apps/api_web`보다 `src/web_app.py` 영향 범위를 우선 확인한다.
- 서비스 간 공통 env 키, 토픽명, 이벤트 shape 변경은 `packages/shared` 기준으로 한 번에 맞춘다.
- 공개 저장소 기준 문구를 유지하고, 로컬 시크릿이나 운영값을 문서에 복원하지 않는다.

## Boundaries
### Always
- `README.md`, `compose.yaml`, 실제 엔트리 파일을 함께 보고 현재 구조를 확인한다.
- 새 서비스 계약을 만들면 `packages/shared`에 둘 수 있는지 먼저 판단한다.
- env 관련 설명은 `.env.example` 또는 코드상 기본값 기준으로만 작성한다.

### Ask First
- 새 앱/패키지 추가, 서비스 이름 변경, 토픽명 변경
- Compose 서비스 포트/의존관계 변경
- `src`의 기존 호환 경로(`web.py`, `main.py`, `src/*`)를 깨는 리팩터링

### Never
- `.env` 실값을 읽어서 문서에 쓰거나 노출하지 않는다.
- `apps/api_web/app.py`를 독자 구현처럼 다뤄서 `src.web_app` 재사용 구조를 무시하지 않는다.
- `collector`/`processor`를 이미 완성된 파이프라인처럼 가정해 과장된 문서를 쓰지 않는다.

## 자주 헷갈리는 점
- `apps/api_web/app.py`는 사실상 thin entrypoint다.
- `src/config.py`는 독자 설정 파일이 아니라 `packages.shared.config` re-export 레이어다.
- 현재 저장소에서 "실시간 파이프라인"은 구조와 연결을 먼저 마련한 상태이지, 수집/처리 로직 완성 상태가 아니다.

## 검증 힌트
- 웹 변경: `uvicorn apps.api_web.app:app --reload`
- 공유 설정 변경: `python -m apps.collector.service`와 `python -m apps.processor.service`가 최소 기동되는지 확인
- Compose 관련 변경: `docker compose config`
