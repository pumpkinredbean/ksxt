# AGENTS.md

## 빠른 명령
- 설정 경로 확인: `python -c "from packages.shared.config import load_service_settings; print(load_service_settings('collector'))"`
- 이벤트 shape 확인: `python -c "from packages.shared.events import build_service_event; print(build_service_event(event_type='x', source='y', payload={}))"`

## 이 디렉터리의 역할
- 서비스 공통 설정 로딩과 env 기본값은 `config.py`가 담당한다.
- 서비스 간 이벤트 토픽명과 최소 이벤트 shape는 `events.py`가 담당한다.
- 루트 `.env` 로딩과 proxy bypass 기본 처리도 여기 기준이다.

## 수정 원칙
- 서비스 둘 이상이 쓰는 값만 이곳에 둔다.
- 기본값을 바꾸면 README/Compose와 모순 없는지 같이 확인한다.
- 공개 저장소 특성상 설명은 env 키 이름과 기본값까지만 쓴다.

## Boundaries
### Always
- 새 공용 설정은 dataclass/loader 흐름에 맞춰 추가한다.
- 토픽 상수와 이벤트 생성 헬퍼는 import 재사용이 쉬운 단순 API로 유지한다.

### Ask First
- env 키 이름 변경, 기본 포트 변경, 토픽명 변경
- `.env` 로딩 위치나 정책 변경

### Never
- 특정 앱 전용 임시 설정을 공유 모듈에 무분별하게 넣지 않는다.
- 시크릿 기본값이나 실운영 자격 증명을 코드/문서에 넣지 않는다.
