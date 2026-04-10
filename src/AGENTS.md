# AGENTS.md

## 빠른 명령
- 웹 앱 실행: `uvicorn apps.api_web.app:app --reload`
- 기존 호환 실행: `python web.py`
- CLI watcher 실행: `python main.py --symbol 005930 --market krx`

## 이 디렉터리의 역할
- 실제 웹 대시보드 구현은 `web_app.py`에 있다.
- KIS REST/websocket 연동 핵심은 `kis_websocket.py`에 있다.
- `config.py`는 `packages.shared.config`를 재-export 하는 얇은 호환 레이어다.

## 수정 원칙
- `apps/api_web` 엔트리와 `web.py` 호환 경로를 깨지 않도록 변경한다.
- 웹 UI는 단일 파일 구조가 크더라도, 지금은 기존 구현을 존중하며 국소 수정 위주로 다룬다.
- websocket schema/컬럼 매핑 수정 시 시장별 TR ID와 rename map의 연쇄 영향을 같이 본다.

## Boundaries
### Always
- 자격 증명 요구는 런타임 기준으로 유지하고 import 시점 강제 검증을 되살리지 않는다.
- KIS 시장별 매핑(`krx`, `nxt`, `total`)을 변경하면 관련 상수 전부를 함께 점검한다.

### Ask First
- `src/web_app.py` 대형 분해 리팩터링
- websocket 이벤트 schema, 필드명, 표시용 rename map의 파괴적 변경
- `main.py`/`web.py` 호환 동작을 깨는 엔트리 변경

### Never
- UI 변경 때문에 `apps/api_web/app.py`에 실제 구현을 복제하지 않는다.
- `.env` 실값을 코드 예시나 AGENTS에 옮기지 않는다.
- KIS 연동이 없는 상태에서도 실제 시장 데이터가 들어오는 것처럼 문서화하지 않는다.
