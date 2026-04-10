# AGENTS.md

## 빠른 명령
- 로컬 실행: `python -m apps.collector.service`
- Compose 실행: `docker compose up collector --build`

## 현재 역할
- 아직 실데이터 수집기가 아니라 heartbeat 이벤트를 주기적으로 출력하는 플레이스홀더 서비스다.
- 설정은 `packages.shared.config.load_service_settings("collector")`를 사용한다.
- 이벤트 헬퍼와 토픽 상수는 `packages.shared.events`를 사용한다.

## 수정 원칙
- 실수집 로직을 넣더라도 지금은 플레이스홀더 상태라는 사실을 문서/코드에서 숨기지 않는다.
- 공용 env 키나 이벤트 shape가 필요하면 먼저 `packages/shared`에 반영할지 본다.
- stdout heartbeat 패턴은 최소 기동 검증 수단이므로 이유 없이 제거하지 않는다.

## Boundaries
### Always
- `source="apps.collector.service"` 같은 식별자는 추적 가능하게 유지한다.
- 토픽명은 하드코딩 추가보다 `packages.shared.events` 재사용을 우선한다.

### Ask First
- 실제 Kafka producer, DB write, 외부 API polling 도입
- heartbeat 외에 새로운 이벤트 계약 추가

### Never
- collector 전용 설정을 `packages/shared/config.py` 밖에서 제각각 파싱하지 않는다.
- 아직 없는 처리 보장/저장 semantics를 문서에 사실처럼 적지 않는다.
