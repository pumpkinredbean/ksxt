import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';

// ─── Types ────────────────────────────────────────────────────────────────────

type MarketScope = 'krx' | 'nxt' | 'total';
type TopView = 'targets' | 'runtime' | 'events';

interface InstrumentRef {
  symbol: string;
  instrument_id?: string | null;
}

interface EventCatalogEntry {
  event_type: string;
  topic_name: string;
  description: string;
}

interface InstrumentSearchResult {
  instrument: InstrumentRef;
  display_name: string;
  market_scope: MarketScope;
  is_active?: boolean;
}

interface CollectionTarget {
  target_id: string;
  instrument: InstrumentRef;
  market_scope: MarketScope;
  event_types: string[];
  enabled: boolean;
}

interface CollectionTargetStatus {
  target_id: string;
  state: string;
  observed_at: string;
  last_event_at?: string | null;
  last_error?: string | null;
}

interface RuntimeStatus {
  component: string;
  state: string;
  observed_at: string;
  active_collection_target_ids: string[];
  last_error?: string | null;
}

interface Snapshot {
  captured_at: string;
  source_service: string;
  event_type_catalog: EventCatalogEntry[];
  collection_targets: CollectionTarget[];
  runtime_status: RuntimeStatus[];
  collection_target_status: CollectionTargetStatus[];
}

interface TargetMutationResponse {
  target?: CollectionTarget;
  applied?: boolean;
  warning?: string | null;
}

interface RecentRuntimeEvent {
  event_id: string;
  event_name: string;
  symbol: string;
  market_scope: string;
  topic_name: string;
  published_at: string;
  matched_target_ids: string[];
  payload?: Record<string, unknown>;
}

interface RecentEventsResponse {
  captured_at: string;
  filters: Record<string, unknown>;
  available_event_names: string[];
  recent_events: RecentRuntimeEvent[];
  buffer_size: number;
}

// ─── Utils ────────────────────────────────────────────────────────────────────

const MARKET_SCOPES: MarketScope[] = ['krx', 'nxt', 'total'];

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({ error: 'Invalid JSON response' }));
  if (!response.ok) {
    const msg =
      (payload as { error?: string; detail?: string }).error ??
      (payload as { detail?: string }).detail ??
      `Request failed: ${response.status}`;
    throw new Error(msg);
  }
  return payload as T;
}

function fmt(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return d.toLocaleString('ko-KR', { hour12: false });
}

function stateTone(value?: string | null): string {
  const v = String(value ?? '').toLowerCase();
  if (['running', 'ready', 'ok', 'active', 'bound', 'enabled'].includes(v)) return 'good';
  if (['error', 'failed', 'degraded'].includes(v)) return 'danger';
  if (['stopped', 'disabled', 'inactive', 'stopping'].includes(v)) return 'muted';
  return 'default';
}

// ─── Shared Components ────────────────────────────────────────────────────────

function Badge({ label, tone }: { label: string; tone?: string }) {
  return <span className={`badge ${tone ?? stateTone(label)}`}>{label}</span>;
}

function Empty({ msg }: { msg: string }) {
  return <div className="empty-row">{msg}</div>;
}

function Banner({ msg, error }: { msg: string; error?: boolean }) {
  return <div className={error ? 'banner error' : 'banner'}>{msg}</div>;
}

// ─── Inline Confirm Button ────────────────────────────────────────────────────
// Replaces window.confirm: first click arms, second click fires.

function ConfirmButton({
  label,
  confirmLabel = '확인 클릭',
  onConfirm,
  disabled,
  className = 'danger-button',
}: {
  label: string;
  confirmLabel?: string;
  onConfirm: () => void;
  disabled?: boolean;
  className?: string;
}) {
  const [armed, setArmed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function arm() {
    setArmed(true);
    timer.current = setTimeout(() => setArmed(false), 3500);
  }

  function fire() {
    if (timer.current) clearTimeout(timer.current);
    setArmed(false);
    onConfirm();
  }

  return armed ? (
    <button type="button" className="danger-button armed" onClick={fire} disabled={disabled}>
      {confirmLabel}
    </button>
  ) : (
    <button type="button" className={className} onClick={arm} disabled={disabled}>
      {label}
    </button>
  );
}

// ─── Targets View ─────────────────────────────────────────────────────────────

interface TargetDraft {
  targetId: string;
  symbol: string;
  scope: MarketScope;
  eventTypes: string[];
  enabled: boolean;
  displayName: string;
}

function emptyDraft(catalog: EventCatalogEntry[]): TargetDraft {
  return {
    targetId: '',
    symbol: '',
    scope: 'total',
    eventTypes: catalog.map((e) => e.event_type),
    enabled: true,
    displayName: '',
  };
}

function TargetsView({
  snapshot,
  snapshotBusy,
  onRefresh,
}: {
  snapshot: Snapshot | null;
  snapshotBusy: boolean;
  onRefresh: () => Promise<void>;
}) {
  const catalog = snapshot?.event_type_catalog ?? [];
  const targets = snapshot?.collection_targets ?? [];
  const statusMap = Object.fromEntries(
    (snapshot?.collection_target_status ?? []).map((s) => [s.target_id, s]),
  );

  const [draft, setDraft] = useState<TargetDraft>(() => emptyDraft(catalog));
  const [searchQuery, setSearchQuery] = useState('');
  const [searchScope, setSearchScope] = useState<MarketScope>('total');
  const [searchResults, setSearchResults] = useState<InstrumentSearchResult[]>([]);
  const [searchMsg, setSearchMsg] = useState('');
  const [searchBusy, setSearchBusy] = useState(false);
  const [formBusy, setFormBusy] = useState(false);
  const [formMsg, setFormMsg] = useState('');
  const [formError, setFormError] = useState(false);

  // Keep event types current when catalog loads
  useEffect(() => {
    if (catalog.length > 0 && draft.eventTypes.length === 0 && !draft.symbol) {
      setDraft((d) => ({ ...d, eventTypes: catalog.map((e) => e.event_type) }));
    }
  }, [catalog.length]); // eslint-disable-line react-hooks/exhaustive-deps

  function pickTarget(t: CollectionTarget, name = '') {
    setDraft({
      targetId: t.target_id,
      symbol: t.instrument.symbol,
      scope: t.market_scope,
      eventTypes: t.event_types.length ? t.event_types : catalog.map((e) => e.event_type),
      enabled: t.enabled,
      displayName: name || t.instrument.instrument_id || '',
    });
    setFormMsg('');
    setFormError(false);
  }

  function pickSearchResult(r: InstrumentSearchResult) {
    const existing = targets.find(
      (t) => t.instrument.symbol === r.instrument.symbol && t.market_scope === r.market_scope,
    );
    if (existing) {
      pickTarget(existing, r.display_name);
    } else {
      setDraft({
        targetId: '',
        symbol: r.instrument.symbol,
        scope: r.market_scope,
        eventTypes: catalog.map((e) => e.event_type),
        enabled: true,
        displayName: r.display_name,
      });
    }
    setFormMsg('');
    setFormError(false);
  }

  function resetDraft() {
    setDraft(emptyDraft(catalog));
    setFormMsg('');
    setFormError(false);
  }

  async function doSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearchBusy(true);
    setSearchMsg('');
    try {
      const r = await requestJson<{ instrument_results: InstrumentSearchResult[] }>(
        `/api/admin/instruments?query=${encodeURIComponent(searchQuery.trim())}&scope=${searchScope}`,
      );
      setSearchResults(r.instrument_results ?? []);
      setSearchMsg(`${r.instrument_results?.length ?? 0}건`);
    } catch (err) {
      setSearchResults([]);
      setSearchMsg(err instanceof Error ? err.message : '검색 실패');
    } finally {
      setSearchBusy(false);
    }
  }

  async function doSave(e: FormEvent) {
    e.preventDefault();
    if (!draft.symbol.trim()) {
      setFormMsg('종목코드를 입력하세요.');
      setFormError(true);
      return;
    }
    if (draft.eventTypes.length === 0) {
      setFormMsg('이벤트를 최소 1개 선택하세요.');
      setFormError(true);
      return;
    }
    setFormBusy(true);
    setFormMsg('');
    setFormError(false);
    try {
      const r = await requestJson<TargetMutationResponse>('/api/admin/targets', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_id: draft.targetId || undefined,
          symbol: draft.symbol.trim(),
          market_scope: draft.scope,
          event_types: draft.eventTypes,
          enabled: draft.enabled,
        }),
      });
      setFormMsg(r.warning ? `저장됨 (경고: ${r.warning})` : '저장되었습니다.');
      await onRefresh();
      if (r.target) {
        pickTarget(r.target, draft.displayName);
      }
    } catch (err) {
      setFormMsg(err instanceof Error ? err.message : '저장 실패');
      setFormError(true);
    } finally {
      setFormBusy(false);
    }
  }

  async function doDelete(targetId: string) {
    setFormBusy(true);
    try {
      await requestJson(`/api/admin/targets/${encodeURIComponent(targetId)}`, {
        method: 'DELETE',
      });
      if (draft.targetId === targetId) resetDraft();
      setFormMsg('삭제되었습니다.');
      setFormError(false);
      await onRefresh();
    } catch (err) {
      setFormMsg(err instanceof Error ? err.message : '삭제 실패');
      setFormError(true);
    } finally {
      setFormBusy(false);
    }
  }

  const isUpdate = !!draft.targetId || targets.some(
    (t) => t.instrument.symbol === draft.symbol.trim() && t.market_scope === draft.scope,
  );

  return (
    <div className="view-grid targets-grid">
      {/* Left column: search + target list */}
      <div className="col-stack">
        {/* Search panel */}
        <section className="panel">
          <div className="panel-head">
            <span className="eyebrow">Instrument Search</span>
          </div>
          <form className="search-bar" onSubmit={doSearch}>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="005930 · 삼성전자"
            />
            <select value={searchScope} onChange={(e) => setSearchScope(e.target.value as MarketScope)}>
              {MARKET_SCOPES.map((s) => (
                <option key={s} value={s}>
                  {s.toUpperCase()}
                </option>
              ))}
            </select>
            <button type="submit" disabled={searchBusy}>
              {searchBusy ? '…' : '검색'}
            </button>
          </form>
          {searchMsg && <div className="hint">{searchMsg}</div>}
          {searchResults.length > 0 && (
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>종목</th>
                    <th>시장</th>
                    <th>등록</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {searchResults.map((r) => {
                    const registered = targets.some(
                      (t) => t.instrument.symbol === r.instrument.symbol && t.market_scope === r.market_scope,
                    );
                    return (
                      <tr key={`${r.instrument.symbol}-${r.market_scope}`}>
                        <td>
                          <strong>{r.instrument.symbol}</strong>
                          <div className="sub">{r.display_name}</div>
                        </td>
                        <td>
                          <Badge label={r.market_scope.toUpperCase()} tone="default" />
                        </td>
                        <td>
                          {registered ? (
                            <Badge label="등록됨" tone="good" />
                          ) : (
                            <Badge label="신규" tone="muted" />
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="sm-btn"
                            onClick={() => pickSearchResult(r)}
                          >
                            선택
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Target list */}
        <section className="panel">
          <div className="panel-head">
            <span className="eyebrow">Registered Targets</span>
            <span className="count-pill">{targets.length}</span>
          </div>
          {targets.length === 0 ? (
            <Empty msg="등록된 수집 대상 없음" />
          ) : (
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>종목</th>
                    <th>이벤트</th>
                    <th>상태</th>
                    <th>마지막 이벤트</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {targets.map((t) => {
                    const st = statusMap[t.target_id];
                    return (
                      <tr key={t.target_id} className={draft.targetId === t.target_id ? 'row-selected' : ''}>
                        <td>
                          <strong>{t.instrument.symbol}</strong>
                          <div className="sub">
                            <Badge label={t.market_scope.toUpperCase()} tone="default" />
                            {' '}
                            {t.enabled ? (
                              <Badge label="활성" tone="good" />
                            ) : (
                              <Badge label="비활성" tone="muted" />
                            )}
                          </div>
                        </td>
                        <td className="event-pills">
                          {t.event_types.map((ev) => (
                            <Badge key={ev} label={ev} tone="default" />
                          ))}
                        </td>
                        <td>
                          <Badge label={st?.state ?? 'unknown'} tone={stateTone(st?.state)} />
                        </td>
                        <td className="mono">{fmt(st?.last_event_at)}</td>
                        <td>
                          <div className="row-actions">
                            <button
                              type="button"
                              className="sm-btn"
                              onClick={() => pickTarget(t)}
                            >
                              편집
                            </button>
                            <ConfirmButton
                              label="삭제"
                              confirmLabel="삭제 확인"
                              onConfirm={() => void doDelete(t.target_id)}
                              disabled={formBusy || snapshotBusy}
                              className="sm-btn danger-sm"
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {/* Right column: edit form */}
      <section className="panel form-panel">
        <div className="panel-head">
          <span className="eyebrow">{isUpdate ? 'Update Target' : 'New Target'}</span>
          {draft.symbol && (
            <span className="identity-label">
              {draft.symbol} · {draft.scope.toUpperCase()}
            </span>
          )}
        </div>

        <form className="col-stack" onSubmit={doSave}>
          <div className="field-row">
            <label className="field">
              <span>종목코드</span>
              <input
                value={draft.symbol}
                onChange={(e) => setDraft((d) => ({ ...d, symbol: e.target.value }))}
                placeholder="005930"
              />
            </label>
            <label className="field">
              <span>시장 범위</span>
              <select
                value={draft.scope}
                onChange={(e) => setDraft((d) => ({ ...d, scope: e.target.value as MarketScope }))}
              >
                {MARKET_SCOPES.map((s) => (
                  <option key={s} value={s}>
                    {s.toUpperCase()}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="field-block">
            <div className="field-block-head">
              <span>수집 이벤트</span>
              <div className="inline-actions">
                <button
                  type="button"
                  className="sm-btn"
                  onClick={() => setDraft((d) => ({ ...d, eventTypes: catalog.map((e) => e.event_type) }))}
                >
                  전체
                </button>
                <button
                  type="button"
                  className="sm-btn"
                  onClick={() => setDraft((d) => ({ ...d, eventTypes: [] }))}
                >
                  해제
                </button>
              </div>
            </div>
            <div className="check-grid">
              {catalog.map((entry) => {
                const checked = draft.eventTypes.includes(entry.event_type);
                return (
                  <label key={entry.event_type} className="check-card">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        setDraft((d) => ({
                          ...d,
                          eventTypes: checked
                            ? d.eventTypes.filter((v) => v !== entry.event_type)
                            : [...d.eventTypes, entry.event_type],
                        }))
                      }
                    />
                    <span>
                      <strong>{entry.event_type}</strong>
                      <small>{entry.description}</small>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.checked }))}
            />
            <span>저장 후 즉시 수집 활성화</span>
          </label>

          <div className="form-actions">
            <button type="submit" disabled={formBusy || snapshotBusy}>
              {formBusy ? '처리 중…' : isUpdate ? '업데이트 저장' : '새 대상 저장'}
            </button>
            <button type="button" className="secondary-button" onClick={resetDraft}>
              초기화
            </button>
          </div>

          {formMsg && <Banner msg={formMsg} error={formError} />}
        </form>
      </section>
    </div>
  );
}

// ─── Runtime View ─────────────────────────────────────────────────────────────

function RuntimeView({ snapshot }: { snapshot: Snapshot | null }) {
  const runtime = snapshot?.runtime_status ?? [];
  const targetStatuses = snapshot?.collection_target_status ?? [];
  const targets = snapshot?.collection_targets ?? [];

  // Build symbol+scope label from targets for better UX
  const labelByTargetId = Object.fromEntries(
    targets.map((t) => [t.target_id, `${t.instrument.symbol} · ${t.market_scope.toUpperCase()}`]),
  );

  return (
    <div className="col-stack">
      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">Service Health</span>
        </div>
        {runtime.length === 0 ? (
          <Empty msg="서비스 상태 없음" />
        ) : (
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>컴포넌트</th>
                  <th>상태</th>
                  <th>활성 타깃 수</th>
                  <th>마지막 오류</th>
                  <th>관측 시각</th>
                </tr>
              </thead>
              <tbody>
                {runtime.map((r) => (
                  <tr key={r.component}>
                    <td>
                      <strong>{r.component}</strong>
                    </td>
                    <td>
                      <Badge label={r.state} tone={stateTone(r.state)} />
                    </td>
                    <td>{r.active_collection_target_ids.length}</td>
                    <td className="error-cell">{r.last_error ?? '—'}</td>
                    <td className="mono">{fmt(r.observed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">Per-Target Status</span>
          <span className="count-pill">{targetStatuses.length}</span>
        </div>
        {targetStatuses.length === 0 ? (
          <Empty msg="대상별 상태 없음" />
        ) : (
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>종목 · 시장</th>
                  <th>상태</th>
                  <th>마지막 이벤트</th>
                  <th>마지막 오류</th>
                  <th>관측 시각</th>
                </tr>
              </thead>
              <tbody>
                {targetStatuses.map((s) => (
                  <tr key={s.target_id}>
                    <td>
                      <strong>{labelByTargetId[s.target_id] ?? s.target_id}</strong>
                    </td>
                    <td>
                      <Badge label={s.state} tone={stateTone(s.state)} />
                    </td>
                    <td className="mono">{fmt(s.last_event_at)}</td>
                    <td className="error-cell">{s.last_error ?? '—'}</td>
                    <td className="mono">{fmt(s.observed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// ─── Events View ──────────────────────────────────────────────────────────────

function EventsView({ snapshot }: { snapshot: Snapshot | null }) {
  const targets = snapshot?.collection_targets ?? [];

  const [events, setEvents] = useState<RecentRuntimeEvent[]>([]);
  const [bufferSize, setBufferSize] = useState<number>(0);
  const [capturedAt, setCapturedAt] = useState<string>('');
  const [availableNames, setAvailableNames] = useState<string[]>([]);
  const [filterSymbol, setFilterSymbol] = useState('');
  const [filterScope, setFilterScope] = useState('');
  const [filterName, setFilterName] = useState('');
  const [limit, setLimit] = useState(50);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const buildUrl = useCallback(() => {
    const params = new URLSearchParams();
    if (filterSymbol.trim()) params.set('symbol', filterSymbol.trim());
    if (filterScope) params.set('scope', filterScope);
    if (filterName) params.set('event_name', filterName);
    params.set('limit', String(limit));
    return `/api/admin/events?${params.toString()}`;
  }, [filterSymbol, filterScope, filterName, limit]);

  async function fetchEvents() {
    setBusy(true);
    setMsg('');
    setError(false);
    try {
      const r = await requestJson<RecentEventsResponse>(buildUrl());
      setEvents(r.recent_events ?? []);
      setBufferSize(r.buffer_size ?? 0);
      setCapturedAt(r.captured_at ?? '');
      setAvailableNames(r.available_event_names ?? []);
      setMsg(`${r.recent_events?.length ?? 0}건 · 버퍼 ${r.buffer_size ?? 0}개`);
    } catch (err) {
      setEvents([]);
      setMsg(err instanceof Error ? err.message : '이벤트 조회 실패');
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void fetchEvents();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Build symbol options from known targets
  const symbolOptions = [...new Set(targets.map((t) => t.instrument.symbol))];

  return (
    <div className="col-stack">
      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">Recent Runtime Events</span>
          {capturedAt && <span className="hint-inline">캡처: {fmt(capturedAt)}</span>}
        </div>

        {/* Filters */}
        <div className="filter-bar">
          <select value={filterSymbol} onChange={(e) => setFilterSymbol(e.target.value)}>
            <option value="">모든 종목</option>
            {symbolOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select value={filterScope} onChange={(e) => setFilterScope(e.target.value)}>
            <option value="">모든 시장</option>
            {MARKET_SCOPES.map((s) => (
              <option key={s} value={s}>
                {s.toUpperCase()}
              </option>
            ))}
          </select>
          <select value={filterName} onChange={(e) => setFilterName(e.target.value)}>
            <option value="">모든 이벤트</option>
            {availableNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="narrow-select"
          >
            {[25, 50, 100, 200].map((n) => (
              <option key={n} value={n}>
                {n}건
              </option>
            ))}
          </select>
          <button type="button" onClick={() => void fetchEvents()} disabled={busy}>
            {busy ? '조회 중…' : '조회'}
          </button>
        </div>

        {msg && <div className={error ? 'hint error-hint' : 'hint'}>{msg}</div>}

        {events.length === 0 ? (
          <Empty msg="최근 이벤트 없음 — 수집 대상을 활성화하면 이벤트가 쌓입니다." />
        ) : (
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>시각</th>
                  <th>이벤트</th>
                  <th>종목 · 시장</th>
                  <th>토픽</th>
                  <th>매칭 타깃</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <>
                    <tr
                      key={ev.event_id}
                      className={expandedId === ev.event_id ? 'row-expanded' : ''}
                    >
                      <td className="mono">{fmt(ev.published_at)}</td>
                      <td>
                        <Badge label={ev.event_name} tone="default" />
                      </td>
                      <td>
                        <strong>{ev.symbol}</strong>
                        <span className="sub"> · {ev.market_scope.toUpperCase()}</span>
                      </td>
                      <td className="mono small">{ev.topic_name}</td>
                      <td>{ev.matched_target_ids.length > 0 ? ev.matched_target_ids.length : '—'}</td>
                      <td>
                        {ev.payload && Object.keys(ev.payload).length > 0 && (
                          <button
                            type="button"
                            className="sm-btn"
                            onClick={() =>
                              setExpandedId(expandedId === ev.event_id ? null : ev.event_id)
                            }
                          >
                            {expandedId === ev.event_id ? '닫기' : '페이로드'}
                          </button>
                        )}
                      </td>
                    </tr>
                    {expandedId === ev.event_id && ev.payload && (
                      <tr key={`${ev.event_id}-payload`} className="payload-row">
                        <td colSpan={6}>
                          <pre className="payload-pre">{JSON.stringify(ev.payload, null, 2)}</pre>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="hint">
          버퍼 크기: {bufferSize} · 최대 표시 {limit}건
        </div>
      </section>
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView] = useState<TopView>('targets');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [snapshotError, setSnapshotError] = useState('');
  const [snapshotBusy, setSnapshotBusy] = useState(true);

  const refreshSnapshot = useCallback(async () => {
    setSnapshotBusy(true);
    setSnapshotError('');
    try {
      const next = await requestJson<Snapshot>('/api/admin/snapshot');
      setSnapshot(next);
    } catch (err) {
      setSnapshotError(err instanceof Error ? err.message : '스냅샷 로드 실패');
    } finally {
      setSnapshotBusy(false);
    }
  }, []);

  useEffect(() => {
    void refreshSnapshot();
  }, [refreshSnapshot]);

  const targets = snapshot?.collection_targets ?? [];
  const runtime = snapshot?.runtime_status ?? [];
  const anyError = runtime.some((r) => stateTone(r.state) === 'danger');

  return (
    <div className="shell">
      {/* Top bar */}
      <header className="topbar">
        <div className="topbar-brand">
          <span className="brand-label">KIS Admin</span>
          <span className="brand-sub">Collector Control Plane</span>
        </div>
        <nav className="topbar-nav">
          {(['targets', 'runtime', 'events'] as TopView[]).map((v) => (
            <button
              key={v}
              type="button"
              className={`nav-btn${view === v ? ' active' : ''}`}
              onClick={() => setView(v)}
            >
              {v === 'targets' && 'Targets'}
              {v === 'runtime' && 'Runtime'}
              {v === 'events' && 'Events'}
            </button>
          ))}
        </nav>
        <div className="topbar-meta">
          <span className="meta-stat">
            <span className="meta-key">Targets</span>
            <strong>{targets.length}</strong>
          </span>
          <span className="meta-stat">
            <span className="meta-key">Health</span>
            <Badge
              label={anyError ? 'degraded' : runtime.length > 0 ? 'ok' : 'no data'}
              tone={anyError ? 'danger' : runtime.length > 0 ? 'good' : 'muted'}
            />
          </span>
          {snapshot && (
            <span className="meta-stat">
              <span className="meta-key">Snapshot</span>
              <span className="mono small">{fmt(snapshot.captured_at)}</span>
            </span>
          )}
          <button
            type="button"
            className="secondary-button sm-topbar-btn"
            onClick={() => void refreshSnapshot()}
            disabled={snapshotBusy}
          >
            {snapshotBusy ? '…' : '새로고침'}
          </button>
        </div>
      </header>

      {snapshotError && (
        <div className="global-banner error">{snapshotError}</div>
      )}

      {/* Main content */}
      <main className="main">
        {view === 'targets' && (
          <TargetsView
            snapshot={snapshot}
            snapshotBusy={snapshotBusy}
            onRefresh={refreshSnapshot}
          />
        )}
        {view === 'runtime' && <RuntimeView snapshot={snapshot} />}
        {view === 'events' && <EventsView snapshot={snapshot} />}
      </main>
    </div>
  );
}
