# AGENTS.md

## 빠른 명령
- 로컬 실행: `uvicorn apps.api_web.app:app --reload`
- Compose 실행: `docker compose up api-web --build`

## 이 디렉터리의 역할
- `apps/api_web/app.py`는 배포/실행용 FastAPI 엔트리다.
- 실제 앱 객체는 `src.web_app`에서 import 한다.
- 여기서는 부트스트랩 경로를 얇게 유지하는 것이 우선이다.

## 수정 원칙
- 웹 UI/엔드포인트 동작 변경은 보통 여기 말고 `src/web_app.py`에서 처리한다.
- 여기서는 import 경로, 엔트리 노출, 런 커맨드 호환성만 건드리는 편이 맞다.

## Boundaries
### Always
- 변경 전 `src/web_app.py`가 실제 구현 본체인지 다시 확인한다.
- `app` export 이름은 유지한다.

### Ask First
- `apps.api_web.app:app` 경로를 바꾸는 변경
- 별도 FastAPI app factory 또는 추가 엔트리 구조 도입

### Never
- 이 파일에 대형 비즈니스 로직이나 HTML/JS UI를 복붙하지 않는다.
- `src.web_app` 재사용 구조를 우회하는 임시 분기 코드를 넣지 않는다.
