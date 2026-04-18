# Decisions Log

Append-only log of explicit hub decisions.  Each entry uses the H-series
(Hub decision) identifier and captures question, decision, rationale, and
impact so later sessions can branch with full context.

---

## H23 — multiprovider 구현 1차(step 1) 결과

- **질문**: multiprovider 구현 1차(step 1) 결과는 어디까지 완료되었는가?
- **결정**: **PARTIAL** — domain/contracts 확장과 provider adapter 경계
  skeleton, control-plane wiring까지는 완료되었으나 CCXT/CCXT Pro의 live
  adapter 구현과 admin UI의 provider/instrument_type 노출은 의도적으로
  이번 세션에서 수행하지 않았다.
- **근거**:
  - `packages/domain/enums.py`: `Provider` StrEnum(KXT/CCXT/CCXT_PRO/OTHER)
    신규 추가. `InstrumentType`에 `SPOT`, `PERPETUAL` 추가 (FUTURE/OPTION
    기존 유지)로 crypto spot + USDT perpetual 구조 준비 완료.
  - `packages/domain/models.py`: `InstrumentRef`, `CollectionTarget`,
    `InstrumentSearchResult`에 `provider`, `canonical_symbol` 추가.
    `build_canonical_symbol()` helper 도입 — 형식 `<provider>:<venue>:<instrument_type>:<symbol>`.
  - `packages/contracts/events.py`, `packages/contracts/admin.py`:
    `DashboardEventEnvelope`, `DashboardControlEnvelope`,
    `RecentRuntimeEvent`에 provider/canonical_symbol 필드를 additive
    optional로 추가하여 기존 KXT 응답 shape를 깨지 않음.
  - `packages/adapters/`: `registry.py`, `kxt.py`, `ccxt.py` 신규.
    `ProviderRegistry` + `build_default_registry()`가 KXT/CCXT/CCXT_PRO 3개
    provider를 등록. CCXT/CCXT_PRO는 `implemented=False` skeleton.
  - `src/collector_control_plane.py`: `upsert_target`, `search_instruments`,
    `record_runtime_event`가 provider/instrument_type를 수용. KXT 기본값
    유지, 비-KXT provider는 market_scope="" 허용 (not-applicable 의미).
  - `apps/collector/runtime.py`: `register_target`이 provider를 수용하고
    provider != KXT일 때 `NotImplementedError`로 실패 loud — silent
    degradation 방지.
  - `apps/collector/service.py`: `start_dashboard_publication`이
    provider/instrument_type/canonical_symbol kwargs를 수용하며
    `build_default_registry()`를 서비스 생성 시 호출.
- **영향**:
  - 다음 세션은 **CCXT/CCXT Pro live adapter 구현** 또는 **admin UI의
    provider/instrument_type 노출 통합** 중 하나로 진행 가능. blocker
    해소 세션은 필요 없음 — 기존 KXT/KRX runtime은 그대로 동작.
  - admin UI에서 provider 필드를 입력·표시하도록 확장하려면 이번
    세션의 additive 필드를 소비하는 frontend 작업이 남아 있음.
  - 운영상 추가 DB 스키마 변경이 필요한 시점은 crypto provider의
    subscription persistence가 붙을 때로 지연됨.
