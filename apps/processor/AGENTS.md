# AGENTS.md

## 빠른 명령
- 로컬 실행: `python -m apps.processor.service`
- Compose 실행: `docker compose up processor --build`

## 현재 역할
- 아직 스트리밍 처리기가 아니라 heartbeat 이벤트를 출력하는 플레이스홀더 서비스다.
- 설정은 `packages.shared.config.load_service_settings("processor")`를 사용한다.
- 처리 결과 토픽 상수는 `packages.shared.events.PROCESSED_EVENTS_TOPIC`를 사용한다.

## 수정 원칙
- 현재는 구조/연결성 확인이 목적이므로, 작은 검증 가능한 단계로만 확장한다.
- collector와 processor가 공통으로 쓰는 계약은 `packages/shared`로 끌어올린다.
- clickhouse/redpanda 연결을 추가하더라도 Compose 기본값과 맞춰야 한다.

## Boundaries
### Always
- 서비스 이름, source, 토픽명이 서로 일관되는지 확인한다.
- placeholder 단계 표현을 유지한다.

### Ask First
- 실시간 변환 파이프라인, 적재 로직, consumer group 도입
- 메시지 schema 변경

### Never
- processor 내부에 collector 설정/계약을 중복 정의하지 않는다.
- 아직 존재하지 않는 영속화/정합성 보장을 README나 AGENTS에 단정적으로 쓰지 않는다.
