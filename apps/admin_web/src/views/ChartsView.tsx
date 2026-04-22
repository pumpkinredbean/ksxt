import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import GridLayout, { Layout, WidthProvider } from 'react-grid-layout';
import Editor from '@monaco-editor/react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  LineData,
  CandlestickData,
  UTCTimestamp,
} from 'lightweight-charts';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import hubStubSource from '../assets/hub-stub.py?raw';

// ─── API contract types ───────────────────────────────────────────────────

export interface ChartSeriesBinding {
  binding_id: string;
  source_kind: 'raw' | 'builtin' | 'script';
  target_id: string;
  symbol: string;
  provider?: string;
  event_name: string;
  field_name: string;
  output_name: string;
  axis: 'left' | 'right';
  color: string;
  label: string;
  visible: boolean;
}

export interface ChartPanelSpec {
  panel_id: string;
  chart_type: 'line' | 'candle';
  symbol: string;
  source: string;
  series_ref: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title?: string | null;
  notes?: string | null;
  series_bindings: ChartSeriesBinding[];
}

interface IndicatorScriptSpec {
  script_id: string;
  name: string;
  source: string;
  class_name: string;
  builtin: boolean;
  description?: string | null;
}

interface IndicatorInstanceSpec {
  instance_id: string;
  script_id: string;
  symbol: string;
  market_scope: string;
  params: Record<string, unknown>;
  enabled: boolean;
}

interface IndicatorErrorRow {
  instance_id: string;
  script_id: string;
  symbol: string;
  state: string;
  last_error: string | null;
  last_output_at: string | null;
  output_count: number;
}

interface SeriesPoint {
  timestamp: string;
  value: number;
  meta?: Record<string, unknown>;
}

interface IndicatorOutputEnvelope {
  instance_id: string;
  script_id: string;
  name: string;
  symbol: string;
  market_scope: string;
  output_kind: string;
  published_at: string;
  point: SeriesPoint;
}

// ─── LocalStorage keys ───────────────────────────────────────────────────

const LS_PREFIX = 'korea-market-data-hub.admin-charts';
const LS_PREFERRED = `${LS_PREFIX}.preferredLayout.v1`;
const LS_WORKING = `${LS_PREFIX}.workingLayout.v1`;
const LS_SEED_DONE = `${LS_PREFIX}.seed.v2.done`;

const DEFAULT_LAYOUT: Layout[] = [];

const DEFAULT_COLORS = ['#4aa3ff', '#f59e0b', '#22c55e', '#ef4444', '#a855f7', '#14b8a6'];

const ResponsiveGridLayout = WidthProvider(GridLayout);

// ─── Small helpers ────────────────────────────────────────────────────────

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => ({ error: 'invalid json' }));
  if (!response.ok) {
    const msg =
      (body as { error?: string; detail?: string }).error ??
      (body as { detail?: string }).detail ??
      `request failed: ${response.status}`;
    const err = new Error(msg) as Error & { payload?: unknown; status?: number };
    err.payload = body;
    err.status = response.status;
    throw err;
  }
  return body as T;
}

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function loadLayout(key: string): Layout[] | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as Layout[];
  } catch {
    /* ignore */
  }
  return null;
}

function saveLayout(key: string, layout: Layout[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(layout));
  } catch {
    /* ignore */
  }
}

function normalizePanel(raw: any): ChartPanelSpec {
  return {
    panel_id: raw.panel_id,
    chart_type: raw.chart_type,
    symbol: raw.symbol ?? '',
    source: raw.source ?? 'raw_event',
    series_ref: raw.series_ref ?? '',
    x: raw.x ?? 0,
    y: raw.y ?? 0,
    w: raw.w ?? 8,
    h: raw.h ?? 10,
    title: raw.title ?? null,
    notes: raw.notes ?? null,
    series_bindings: Array.isArray(raw.series_bindings)
      ? raw.series_bindings.map((b: any) => ({
          binding_id: b.binding_id ?? uid('bind'),
          source_kind: b.source_kind ?? 'raw',
          target_id: b.target_id ?? '',
          symbol: b.symbol ?? '',
          provider: b.provider ?? '',
          event_name: b.event_name ?? '',
          field_name: b.field_name ?? '',
          output_name: b.output_name ?? '',
          axis: b.axis ?? 'left',
          color: b.color ?? '',
          label: b.label ?? '',
          visible: b.visible !== false,
        }))
      : [],
  };
}

function extractScalar(
  eventName: string,
  payload: Record<string, unknown> | null | undefined,
  fieldName: string,
): number | null {
  if (!payload) return null;
  // For trade/price/mark/funding; fall back to common fields.
  if (fieldName && fieldName in payload) {
    const raw = payload[fieldName];
    const v = Number(raw);
    return Number.isFinite(v) ? v : null;
  }
  // Defaults per event_name.
  if (eventName === 'trade') {
    const v = Number((payload as any).price);
    return Number.isFinite(v) ? v : null;
  }
  if (eventName === 'mark_price' || eventName === 'funding_rate') {
    const v = Number((payload as any).value ?? (payload as any).rate ?? (payload as any).mark_price);
    return Number.isFinite(v) ? v : null;
  }
  if (eventName === 'ohlcv') {
    const v = Number((payload as any).close);
    return Number.isFinite(v) ? v : null;
  }
  return null;
}

// ─── ChartPanel: multi-series candle/line host ───────────────────────────

function ChartPanel({
  spec,
  indicatorOutputs,
  rawEvents,
}: {
  spec: ChartPanelSpec;
  indicatorOutputs: Map<string, SeriesPoint[]>;
  rawEvents: Map<string, Array<Record<string, unknown>>>;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<
    Map<string, { kind: 'line' | 'candle'; api: ISeriesApi<'Line'> | ISeriesApi<'Candlestick'> }>
  >(new Map());

  // Create chart once per mount.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { color: '#1a1a1a' }, textColor: '#d0d0d0' },
      grid: { vertLines: { color: '#262626' }, horzLines: { color: '#262626' } },
      timeScale: { timeVisible: true, secondsVisible: true },
      rightPriceScale: { visible: true },
      leftPriceScale: { visible: true },
      autoSize: true,
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = new Map();
    };
  }, []);

  // Diff series bindings + feed data on every update.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const current = seriesRef.current;
    const bindings = spec.series_bindings ?? [];

    const desiredIds = new Set<string>();
    const firstBindingId = bindings[0]?.binding_id;

    bindings.forEach((binding, idx) => {
      if (!binding.visible) return;
      desiredIds.add(binding.binding_id);
      // Candle panel: first binding is candlestick; rest are overlays.
      const isCandleBase = spec.chart_type === 'candle' && binding.binding_id === firstBindingId;
      const desiredKind: 'line' | 'candle' = isCandleBase ? 'candle' : 'line';
      const existing = current.get(binding.binding_id);
      let entry = existing;
      if (!existing || existing.kind !== desiredKind) {
        if (existing) {
          try {
            chart.removeSeries(existing.api);
          } catch {
            /* ignore */
          }
          current.delete(binding.binding_id);
        }
        const color = binding.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
        if (desiredKind === 'candle') {
          const api = chart.addCandlestickSeries();
          entry = { kind: 'candle', api };
        } else {
          const api = chart.addLineSeries({
            color,
            lineWidth: 2,
            priceScaleId: binding.axis === 'right' ? 'right' : 'left',
          });
          entry = { kind: 'line', api };
        }
        current.set(binding.binding_id, entry);
      } else if (existing.kind === 'line') {
        // Update color/axis if changed.
        const color = binding.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
        try {
          (existing.api as ISeriesApi<'Line'>).applyOptions({
            color,
            priceScaleId: binding.axis === 'right' ? 'right' : 'left',
          });
        } catch {
          /* ignore */
        }
      }

      // Resolve data feed.
      if (!entry) return;
      const symbol = binding.symbol || spec.symbol;

      if (binding.source_kind === 'raw') {
        const rows = rawEvents.get(`${symbol}:${binding.event_name}`) ?? [];
        if (entry.kind === 'candle') {
          const data: CandlestickData[] = rows
            .map((r) => {
              const ts = r.timestamp ?? r.published_at;
              return {
                time: Math.floor(new Date(ts as string).getTime() / 1000) as UTCTimestamp,
                open: Number((r as any).open),
                high: Number((r as any).high),
                low: Number((r as any).low),
                close: Number((r as any).close),
              };
            })
            .filter((d) => Number.isFinite(d.open) && Number.isFinite(d.close))
            .sort((a, b) => (a.time as number) - (b.time as number));
          (entry.api as ISeriesApi<'Candlestick'>).setData(data);
        } else {
          const data: LineData[] = rows
            .map((r) => {
              const ts = r.timestamp ?? r.published_at;
              const payload = (r as any).__payload as Record<string, unknown> | undefined;
              const value = extractScalar(
                binding.event_name,
                payload ?? (r as Record<string, unknown>),
                binding.field_name,
              );
              if (value == null || !ts) return null;
              return {
                time: Math.floor(new Date(ts as string).getTime() / 1000) as UTCTimestamp,
                value,
              } as LineData;
            })
            .filter((d): d is LineData => d != null)
            .sort((a, b) => (a.time as number) - (b.time as number));
          (entry.api as ISeriesApi<'Line'>).setData(data);
        }
      } else {
        // builtin / script → indicatorOutputs keyed by instance_id
        const key = binding.target_id;
        const pts = indicatorOutputs.get(key) ?? [];
        const data: LineData[] = pts
          .map((p) => ({
            time: Math.floor(new Date(p.timestamp).getTime() / 1000) as UTCTimestamp,
            value: p.value,
          }))
          .sort((a, b) => (a.time as number) - (b.time as number));
        if (entry.kind === 'line') {
          (entry.api as ISeriesApi<'Line'>).setData(data);
        }
      }
    });

    // Remove stale series.
    for (const [id, entry] of Array.from(current.entries())) {
      if (!desiredIds.has(id)) {
        try {
          chart.removeSeries(entry.api);
        } catch {
          /* ignore */
        }
        current.delete(id);
      }
    }
  }, [spec.series_bindings, spec.chart_type, spec.symbol, indicatorOutputs, rawEvents]);

  const legend = (spec.series_bindings ?? []).filter((b) => b.visible);

  return (
    <>
      <div className="chart-host" ref={containerRef} />
      {legend.length > 0 && (
        <div className="chart-legend">
          {legend.map((b, idx) => (
            <span key={b.binding_id} className="chart-legend-item">
              <span
                className="chart-legend-dot"
                style={{ background: b.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length] }}
              />
              {b.label ||
                (b.source_kind === 'raw'
                  ? `${b.event_name}${b.field_name ? '.' + b.field_name : ''}`
                  : b.target_id || b.source_kind)}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

// ─── Inspector sub-component ─────────────────────────────────────────────

function PanelInspector({
  panel,
  symbols,
  instances,
  scripts,
  onChange,
  onActivate,
}: {
  panel: ChartPanelSpec;
  symbols: string[];
  instances: IndicatorInstanceSpec[];
  scripts: IndicatorScriptSpec[];
  onChange: (next: ChartPanelSpec) => void;
  onActivate: (scriptId: string, symbol: string) => Promise<string | null>;
}) {
  const [localPanel, setLocalPanel] = useState<ChartPanelSpec>(panel);
  useEffect(() => setLocalPanel(panel), [panel]);

  function commit(next: ChartPanelSpec) {
    setLocalPanel(next);
    onChange(next);
  }

  function updateBinding(idx: number, patch: Partial<ChartSeriesBinding>) {
    const nextBindings = localPanel.series_bindings.map((b, i) =>
      i === idx ? { ...b, ...patch } : b,
    );
    commit({ ...localPanel, series_bindings: nextBindings });
  }

  function removeBinding(idx: number) {
    const nextBindings = localPanel.series_bindings.filter((_, i) => i !== idx);
    commit({ ...localPanel, series_bindings: nextBindings });
  }

  function addBinding() {
    const fresh: ChartSeriesBinding = {
      binding_id: uid('bind'),
      source_kind: 'raw',
      target_id: '',
      symbol: localPanel.symbol,
      event_name: localPanel.chart_type === 'candle' ? 'ohlcv' : 'trade',
      field_name: '',
      output_name: '',
      axis: 'left',
      color: '',
      label: '',
      visible: true,
    };
    commit({ ...localPanel, series_bindings: [...localPanel.series_bindings, fresh] });
  }

  async function handleActivateShortcut(idx: number, scriptId: string) {
    const sym = localPanel.series_bindings[idx]?.symbol || localPanel.symbol;
    if (!sym) return;
    const instanceId = await onActivate(scriptId, sym);
    if (instanceId) {
      updateBinding(idx, { target_id: instanceId });
    }
  }

  return (
    <div className="charts-inspector">
      <div className="inspector-section">
        <span className="eyebrow">Panel</span>
        <label className="field">
          <span>Title</span>
          <input
            value={localPanel.title ?? ''}
            onChange={(e) => commit({ ...localPanel, title: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Chart type</span>
          <select
            value={localPanel.chart_type}
            onChange={(e) =>
              commit({ ...localPanel, chart_type: e.target.value as 'line' | 'candle' })
            }
          >
            <option value="line">line</option>
            <option value="candle">candle</option>
          </select>
        </label>
        <label className="field">
          <span>Symbol</span>
          <select
            value={localPanel.symbol}
            onChange={(e) => commit({ ...localPanel, symbol: e.target.value })}
          >
            <option value="">— symbol —</option>
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="inspector-section">
        <div className="inspector-section-head">
          <span className="eyebrow">Series ({localPanel.series_bindings.length})</span>
          <button type="button" className="sm-btn" onClick={addBinding}>
            + series 추가
          </button>
        </div>
        {localPanel.series_bindings.length === 0 && (
          <div className="empty-row">시리즈가 없습니다. 먼저 추가하세요.</div>
        )}
        {localPanel.series_bindings.map((binding, idx) => {
          const isCandleBase = localPanel.chart_type === 'candle' && idx === 0;
          return (
            <div key={binding.binding_id} className="binding-row">
              <div className="binding-row-head">
                <strong>#{idx + 1}</strong>
                {isCandleBase && <span className="badge good">base</span>}
                <button
                  type="button"
                  className="sm-btn danger-sm"
                  onClick={() => removeBinding(idx)}
                >
                  삭제
                </button>
              </div>
              <label className="field">
                <span>Source</span>
                <select
                  value={binding.source_kind}
                  onChange={(e) =>
                    updateBinding(idx, {
                      source_kind: e.target.value as ChartSeriesBinding['source_kind'],
                      target_id: '',
                      event_name: '',
                      field_name: '',
                      output_name: '',
                    })
                  }
                  disabled={isCandleBase}
                >
                  <option value="raw">raw</option>
                  <option value="builtin">builtin</option>
                  <option value="script">script</option>
                </select>
              </label>

              {binding.source_kind === 'raw' && (
                <>
                  <label className="field">
                    <span>Event</span>
                    <select
                      value={binding.event_name || (isCandleBase ? 'ohlcv' : '')}
                      onChange={(e) => updateBinding(idx, { event_name: e.target.value })}
                      disabled={isCandleBase}
                    >
                      <option value="">—</option>
                      <option value="ohlcv">ohlcv</option>
                      <option value="trade">trade</option>
                      <option value="mark_price">mark_price</option>
                      <option value="funding_rate">funding_rate</option>
                    </select>
                  </label>
                  {!isCandleBase && (
                    <label className="field">
                      <span>Field</span>
                      <select
                        value={binding.field_name}
                        onChange={(e) => updateBinding(idx, { field_name: e.target.value })}
                      >
                        <option value="">(default)</option>
                        {binding.event_name === 'ohlcv' && (
                          <>
                            <option value="close">close</option>
                            <option value="open">open</option>
                            <option value="high">high</option>
                            <option value="low">low</option>
                            <option value="volume">volume</option>
                          </>
                        )}
                        {binding.event_name === 'trade' && <option value="price">price</option>}
                        {(binding.event_name === 'mark_price' ||
                          binding.event_name === 'funding_rate') && (
                          <>
                            <option value="value">value</option>
                            <option value="rate">rate</option>
                          </>
                        )}
                      </select>
                    </label>
                  )}
                </>
              )}

              {binding.source_kind === 'builtin' && (
                <>
                  <label className="field">
                    <span>Builtin</span>
                    <select
                      value={binding.target_id || 'obi'}
                      onChange={(e) => updateBinding(idx, { target_id: e.target.value })}
                    >
                      <option value="obi">obi</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Output</span>
                    <input
                      value={binding.output_name || 'obi'}
                      onChange={(e) => updateBinding(idx, { output_name: e.target.value })}
                    />
                  </label>
                  {!instances.some(
                    (i) => i.script_id === 'builtin.obi' && i.symbol === (binding.symbol || localPanel.symbol),
                  ) && (
                    <button
                      type="button"
                      className="sm-btn"
                      onClick={() => void handleActivateShortcut(idx, 'builtin.obi')}
                    >
                      활성화 (OBI)
                    </button>
                  )}
                </>
              )}

              {binding.source_kind === 'script' && (
                <>
                  <label className="field">
                    <span>Instance</span>
                    <select
                      value={binding.target_id}
                      onChange={(e) => updateBinding(idx, { target_id: e.target.value })}
                    >
                      <option value="">— instance —</option>
                      {instances.map((inst) => {
                        const sc = scripts.find((s) => s.script_id === inst.script_id);
                        return (
                          <option key={inst.instance_id} value={inst.instance_id}>
                            {sc?.name ?? inst.script_id} · {inst.symbol || '*'}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                  <label className="field">
                    <span>Output</span>
                    <input
                      value={binding.output_name}
                      onChange={(e) => updateBinding(idx, { output_name: e.target.value })}
                      placeholder="value"
                    />
                  </label>
                </>
              )}

              <div className="binding-row-grid">
                <label className="field">
                  <span>Axis</span>
                  <select
                    value={binding.axis}
                    onChange={(e) =>
                      updateBinding(idx, { axis: e.target.value as 'left' | 'right' })
                    }
                  >
                    <option value="left">left</option>
                    <option value="right">right</option>
                  </select>
                </label>
                <label className="field">
                  <span>Color</span>
                  <input
                    type="color"
                    value={binding.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length]}
                    onChange={(e) => updateBinding(idx, { color: e.target.value })}
                  />
                </label>
              </div>
              <label className="field">
                <span>Label</span>
                <input
                  value={binding.label}
                  onChange={(e) => updateBinding(idx, { label: e.target.value })}
                />
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={binding.visible}
                  onChange={(e) => updateBinding(idx, { visible: e.target.checked })}
                />
                <span>visible</span>
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main ChartsView ──────────────────────────────────────────────────────

interface ChartsViewProps {
  capabilities: Array<{
    provider: string;
    venue: string;
    instrument_type: string;
    supported_event_types: string[];
    label: string;
  }>;
  targets: Array<{
    target_id: string;
    instrument: { symbol: string; instrument_type?: string | null };
    provider?: string | null;
  }>;
}

export default function ChartsView({ capabilities, targets }: ChartsViewProps) {
  const [panels, setPanels] = useState<ChartPanelSpec[]>([]);
  const [scripts, setScripts] = useState<IndicatorScriptSpec[]>([]);
  const [instances, setInstances] = useState<IndicatorInstanceSpec[]>([]);
  const [errors, setErrors] = useState<IndicatorErrorRow[]>([]);
  const [banner, setBanner] = useState('');
  const [bannerError, setBannerError] = useState(false);
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null);

  const [layout, setLayout] = useState<Layout[]>(
    () => loadLayout(LS_WORKING) ?? loadLayout(LS_PREFERRED) ?? DEFAULT_LAYOUT,
  );

  const [indicatorOutputs, setIndicatorOutputs] = useState<Map<string, SeriesPoint[]>>(new Map());
  const [rawEvents, setRawEvents] = useState<Map<string, Array<Record<string, unknown>>>>(
    () => new Map(),
  );

  const [editingScriptId, setEditingScriptId] = useState<string | null>(null);
  const [editorSource, setEditorSource] = useState<string>(hubStubSource);
  const [editorName, setEditorName] = useState<string>('');
  const [editorClassName, setEditorClassName] = useState<string>('MyOBI');
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const seedAttemptedRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [p, s, i, e] = await Promise.all([
        apiJson<{ panels: any[] }>('/api/admin/charts/panels'),
        apiJson<{ scripts: IndicatorScriptSpec[] }>('/api/admin/charts/scripts'),
        apiJson<{ instances: IndicatorInstanceSpec[] }>('/api/admin/charts/instances'),
        apiJson<{ instances: IndicatorErrorRow[] }>('/api/admin/charts/errors'),
      ]);
      setPanels((p.panels ?? []).map(normalizePanel));
      setScripts(s.scripts ?? []);
      setInstances(i.instances ?? []);
      setErrors(e.instances ?? []);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'charts state load failed');
      setBannerError(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // SSE stream.
  useEffect(() => {
    const es = new EventSource('/api/admin/charts/stream');
    es.addEventListener('indicator_output', (evt: MessageEvent) => {
      try {
        const payload = JSON.parse(evt.data) as IndicatorOutputEnvelope;
        setIndicatorOutputs((prev) => {
          const next = new Map(prev);
          const key = payload.instance_id;
          const cur = next.get(key) ?? [];
          const merged = [...cur, payload.point].slice(-500);
          next.set(key, merged);
          return next;
        });
      } catch {
        /* ignore */
      }
    });
    es.addEventListener('raw_event', (evt: MessageEvent) => {
      try {
        const envelope = JSON.parse(evt.data) as {
          symbol?: string;
          event_name?: string;
          timestamp?: string | number | null;
          published_at?: string | number | null;
          payload?: Record<string, unknown> | null;
        };
        const symbol = envelope.symbol;
        const eventName = envelope.event_name;
        if (!symbol || !eventName) return;
        const key = `${symbol}:${eventName}`;
        const row = {
          ...(envelope.payload ?? {}),
          __payload: envelope.payload ?? {},
          symbol,
          event_name: eventName,
          timestamp: envelope.timestamp,
          published_at: envelope.published_at,
        } as Record<string, unknown>;
        setRawEvents((prev) => {
          const next = new Map(prev);
          const cur = next.get(key) ?? [];
          const merged = [...cur, row].slice(-500);
          next.set(key, merged);
          return next;
        });
      } catch {
        /* ignore */
      }
    });
    return () => es.close();
  }, []);

  const capsBySymbol = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const t of targets) {
      const provider = (t.provider ?? 'kxt').toLowerCase();
      const venue = provider === 'kxt' ? 'krx' : 'binance';
      const itype = (t.instrument.instrument_type ?? 'spot').toLowerCase();
      const cap = capabilities.find(
        (c) => c.provider === provider && c.venue === venue && c.instrument_type === itype,
      );
      if (cap) map.set(t.instrument.symbol, new Set(cap.supported_event_types));
    }
    return map;
  }, [capabilities, targets]);

  function panelSupportsCandle(symbol: string): boolean {
    return capsBySymbol.get(symbol)?.has('ohlcv') ?? false;
  }

  // Sync layout with panel list.
  useEffect(() => {
    setLayout((prev) => {
      const byId = new Map(prev.map((l) => [l.i, l] as const));
      let nextY = prev.reduce((m, l) => Math.max(m, l.y + l.h), 0);
      const merged: Layout[] = [];
      for (const panel of panels) {
        const existing = byId.get(panel.panel_id);
        if (existing) {
          merged.push(existing);
        } else {
          merged.push({
            i: panel.panel_id,
            x: panel.x ?? 0,
            y: nextY,
            w: Math.max(6, panel.w ?? 8),
            h: Math.max(8, panel.h ?? 10),
          });
          nextY += Math.max(8, panel.h ?? 10);
        }
      }
      return merged;
    });
  }, [panels]);

  useEffect(() => {
    saveLayout(LS_WORKING, layout);
  }, [layout]);

  // First-run seeder.
  useEffect(() => {
    if (seedAttemptedRef.current) return;
    if (panels.length > 0) {
      seedAttemptedRef.current = true;
      return;
    }
    if (typeof localStorage !== 'undefined' && localStorage.getItem(LS_SEED_DONE)) {
      seedAttemptedRef.current = true;
      return;
    }
    if (targets.length === 0) return; // wait until targets arrive
    seedAttemptedRef.current = true;
    const sym = targets[0].instrument.symbol;
    const supportsOhlcv = panelSupportsCandle(sym);
    void (async () => {
      try {
        if (supportsOhlcv) {
          await apiJson<{ panel: any }>('/api/admin/charts/panels', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              chart_type: 'candle',
              symbol: sym,
              source: 'raw_event',
              series_ref: '',
              x: 0,
              y: 0,
              w: 8,
              h: 10,
              title: `${sym} Candle`,
              series_bindings: [
                {
                  binding_id: uid('bind'),
                  source_kind: 'raw',
                  symbol: sym,
                  event_name: 'ohlcv',
                  axis: 'left',
                  label: 'OHLCV',
                  visible: true,
                },
              ],
            }),
          });
        }
        await apiJson<{ panel: any }>('/api/admin/charts/panels', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chart_type: 'line',
            symbol: sym,
            source: 'raw_event',
            series_ref: '',
            x: 0,
            y: supportsOhlcv ? 10 : 0,
            w: 8,
            h: 10,
            title: `${sym} Trades`,
            series_bindings: [
              {
                binding_id: uid('bind'),
                source_kind: 'raw',
                symbol: sym,
                event_name: 'trade',
                field_name: 'price',
                axis: 'left',
                label: 'trade.price',
                visible: true,
              },
            ],
          }),
        });
        try {
          localStorage.setItem(LS_SEED_DONE, '1');
        } catch {
          /* ignore */
        }
        await refresh();
      } catch {
        /* ignore seeding errors */
      }
    })();
  }, [panels.length, targets, panelSupportsCandle, refresh]);

  // ── actions ──

  async function addPanel(chartType: 'line' | 'candle') {
    const defaultSymbol = targets[0]?.instrument.symbol ?? '';
    const baseBinding: ChartSeriesBinding = {
      binding_id: uid('bind'),
      source_kind: 'raw',
      target_id: '',
      symbol: defaultSymbol,
      event_name: chartType === 'candle' ? 'ohlcv' : 'trade',
      field_name: chartType === 'candle' ? '' : 'price',
      output_name: '',
      axis: 'left',
      color: '',
      label: chartType === 'candle' ? 'OHLCV' : 'trade.price',
      visible: true,
    };
    try {
      const resp = await apiJson<{ panel: any }>('/api/admin/charts/panels', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chart_type: chartType,
          symbol: defaultSymbol,
          source: chartType === 'candle' ? 'raw_event' : 'indicator_output',
          series_ref: '',
          x: 0,
          y: 0,
          w: 8,
          h: 10,
          title: chartType === 'candle' ? `${defaultSymbol} Candle` : `${defaultSymbol} Line`,
          series_bindings: [baseBinding],
        }),
      });
      const normalized = normalizePanel(resp.panel);
      setPanels((prev) => [...prev, normalized]);
      setSelectedPanelId(normalized.panel_id);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'add panel failed');
      setBannerError(true);
    }
  }

  async function persistPanel(next: ChartPanelSpec) {
    try {
      const resp = await apiJson<{ panel: any }>('/api/admin/charts/panels', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      });
      const normalized = normalizePanel(resp.panel);
      setPanels((prev) =>
        prev.map((p) => (p.panel_id === normalized.panel_id ? normalized : p)),
      );
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'update panel failed');
      setBannerError(true);
    }
  }

  async function removePanel(panelId: string) {
    try {
      await apiJson(`/api/admin/charts/panels/${encodeURIComponent(panelId)}`, {
        method: 'DELETE',
      });
      setPanels((prev) => prev.filter((p) => p.panel_id !== panelId));
      if (selectedPanelId === panelId) setSelectedPanelId(null);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'delete panel failed');
      setBannerError(true);
    }
  }

  function savePreferredLayout() {
    saveLayout(LS_PREFERRED, layout);
    setBanner('선호 레이아웃이 저장되었습니다.');
    setBannerError(false);
  }

  function restorePreferredLayout() {
    const preferred = loadLayout(LS_PREFERRED);
    if (preferred) {
      setLayout(preferred);
      setBanner('선호 레이아웃으로 복원했습니다.');
      setBannerError(false);
    }
  }

  // Inspector change → persist (debounced via fire-and-forget).
  const persistTimeoutRef = useRef<number | null>(null);
  function onInspectorChange(next: ChartPanelSpec) {
    setPanels((prev) => prev.map((p) => (p.panel_id === next.panel_id ? next : p)));
    if (persistTimeoutRef.current != null) {
      window.clearTimeout(persistTimeoutRef.current);
    }
    persistTimeoutRef.current = window.setTimeout(() => {
      void persistPanel(next);
    }, 300);
  }

  async function activateInstance(scriptId: string, symbol: string, topN = 5): Promise<string | null> {
    try {
      const resp = await apiJson<{ instance: IndicatorInstanceSpec }>(
        '/api/admin/charts/instances',
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            script_id: scriptId,
            symbol,
            market_scope: '',
            params: scriptId === 'builtin.obi' ? { top_n: topN } : {},
            enabled: true,
          }),
        },
      );
      setInstances((prev) => {
        const has = prev.some((i) => i.instance_id === resp.instance.instance_id);
        return has
          ? prev.map((i) => (i.instance_id === resp.instance.instance_id ? resp.instance : i))
          : [...prev, resp.instance];
      });
      await refresh();
      return resp.instance.instance_id;
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'activate failed');
      setBannerError(true);
      return null;
    }
  }

  async function deactivateInstance(id: string) {
    try {
      await apiJson(`/api/admin/charts/instances/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
      setInstances((prev) => prev.filter((i) => i.instance_id !== id));
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'deactivate failed');
      setBannerError(true);
    }
  }

  // Script editor.
  function startNewScript() {
    setEditingScriptId(uid('script'));
    setEditorSource(hubStubSource);
    setEditorName('새 인디케이터');
    setEditorClassName('MyOBI');
    setValidationErrors([]);
  }

  function editScript(script: IndicatorScriptSpec) {
    setEditingScriptId(script.script_id);
    setEditorSource(script.source || hubStubSource);
    setEditorName(script.name);
    setEditorClassName(script.class_name);
    setValidationErrors([]);
  }

  async function saveScript() {
    if (!editingScriptId) return;
    try {
      setValidationErrors([]);
      const resp = await apiJson<{ script: IndicatorScriptSpec }>('/api/admin/charts/scripts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          script_id: editingScriptId,
          name: editorName,
          source: editorSource,
          class_name: editorClassName,
        }),
      });
      setScripts((prev) => {
        const has = prev.some((s) => s.script_id === resp.script.script_id);
        return has
          ? prev.map((s) => (s.script_id === resp.script.script_id ? resp.script : s))
          : [...prev, resp.script];
      });
      setBanner('스크립트 저장 완료.');
      setBannerError(false);
    } catch (err: any) {
      const payload = err?.payload as { errors?: string[] } | undefined;
      if (payload?.errors) {
        setValidationErrors(payload.errors);
      } else {
        setValidationErrors([err instanceof Error ? err.message : 'save failed']);
      }
    }
  }

  async function deleteScript(script: IndicatorScriptSpec) {
    if (script.builtin) return;
    if (!confirm(`'${script.name}' 스크립트를 삭제할까요?`)) return;
    try {
      await apiJson(`/api/admin/charts/scripts/${encodeURIComponent(script.script_id)}`, {
        method: 'DELETE',
      });
      setScripts((prev) => prev.filter((s) => s.script_id !== script.script_id));
      setInstances((prev) => prev.filter((i) => i.script_id !== script.script_id));
      if (editingScriptId === script.script_id) setEditingScriptId(null);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'delete failed');
      setBannerError(true);
    }
  }

  const symbols = useMemo(
    () => Array.from(new Set(targets.map((t) => t.instrument.symbol))),
    [targets],
  );

  const selectedPanel = panels.find((p) => p.panel_id === selectedPanelId) ?? null;

  return (
    <div className="col-stack charts-view">
      {banner && <div className={bannerError ? 'banner error' : 'banner'}>{banner}</div>}

      <div className="charts-main-grid">
        <section className="panel">
          <div className="panel-head">
            <span className="eyebrow">Charts Layout</span>
            <div className="row-actions">
              <button type="button" className="sm-btn" onClick={() => void addPanel('line')}>
                + Line 패널
              </button>
              <button type="button" className="sm-btn" onClick={() => void addPanel('candle')}>
                + Candle 패널
              </button>
              <button type="button" className="sm-btn" onClick={savePreferredLayout}>
                레이아웃 저장
              </button>
              <button type="button" className="sm-btn" onClick={restorePreferredLayout}>
                레이아웃 복원
              </button>
            </div>
          </div>

          {panels.length === 0 ? (
            <div className="empty-row">
              패널이 없습니다. 위의 버튼으로 Line/Candle 패널을 추가하세요.
            </div>
          ) : (
            <ResponsiveGridLayout
              className="layout"
              cols={12}
              rowHeight={40}
              layout={layout}
              onLayoutChange={(next) => setLayout(next)}
              draggableHandle=".panel-drag-handle"
              isDraggable
              isResizable
              margin={[8, 8]}
            >
              {panels.map((panel) => {
                const isSelected = panel.panel_id === selectedPanelId;
                const candleDisabled =
                  panel.chart_type === 'candle' && !panelSupportsCandle(panel.symbol);
                return (
                  <div
                    key={panel.panel_id}
                    className={`chart-wrapper${isSelected ? ' selected' : ''}`}
                    onClick={() => setSelectedPanelId(panel.panel_id)}
                  >
                    <div className="chart-wrapper-head">
                      <span className="panel-drag-handle" title="drag">
                        ⋮⋮
                      </span>
                      <strong>
                        {panel.title ||
                          `${panel.chart_type.toUpperCase()} · ${panel.symbol || '—'}`}
                      </strong>
                      <span className="badge muted">{panel.chart_type}</span>
                      <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="sm-btn"
                          onClick={() => setSelectedPanelId(panel.panel_id)}
                        >
                          선택
                        </button>
                        <button
                          type="button"
                          className="sm-btn danger-sm"
                          onClick={() => void removePanel(panel.panel_id)}
                        >
                          삭제
                        </button>
                      </div>
                    </div>
                    {candleDisabled ? (
                      <div className="empty-row">
                        이 심볼의 소스는 OHLCV 캔들 스트림을 제공하지 않습니다. line 타입으로
                        변경하거나 OHLCV 지원 심볼을 선택하세요.
                      </div>
                    ) : (
                      <ChartPanel
                        spec={panel}
                        indicatorOutputs={indicatorOutputs}
                        rawEvents={rawEvents}
                      />
                    )}
                  </div>
                );
              })}
            </ResponsiveGridLayout>
          )}
        </section>

        <aside className="panel inspector-panel">
          <div className="panel-head">
            <span className="eyebrow">Inspector</span>
          </div>
          {selectedPanel ? (
            <PanelInspector
              panel={selectedPanel}
              symbols={symbols}
              instances={instances}
              scripts={scripts}
              onChange={onInspectorChange}
              onActivate={(scriptId, symbol) => activateInstance(scriptId, symbol, 5)}
            />
          ) : (
            <div className="empty-row">
              왼쪽의 패널 카드를 클릭해 시리즈/축/레이블을 편집하세요.
            </div>
          )}
        </aside>
      </div>

      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">Indicator Scripts</span>
          <div className="row-actions">
            <button type="button" className="sm-btn" onClick={startNewScript}>
              + 새 스크립트
            </button>
          </div>
        </div>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>이름</th>
                <th>클래스</th>
                <th>built-in</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {scripts.map((s) => (
                <tr key={s.script_id}>
                  <td>
                    <strong>{s.name}</strong>
                  </td>
                  <td className="mono small">{s.class_name}</td>
                  <td>{s.builtin ? 'yes' : '—'}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="sm-btn"
                        onClick={() => editScript(s)}
                        disabled={s.builtin}
                      >
                        편집
                      </button>
                      <button
                        type="button"
                        className="sm-btn danger-sm"
                        onClick={() => void deleteScript(s)}
                        disabled={s.builtin}
                      >
                        삭제
                      </button>
                      <button
                        type="button"
                        className="sm-btn"
                        onClick={() =>
                          void activateInstance(s.script_id, symbols[0] ?? '', 5)
                        }
                        disabled={symbols.length === 0}
                      >
                        활성화
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {editingScriptId && (
          <div className="script-editor">
            <div className="field-row">
              <label className="field">
                <span>이름</span>
                <input value={editorName} onChange={(e) => setEditorName(e.target.value)} />
              </label>
              <label className="field">
                <span>클래스명</span>
                <input
                  value={editorClassName}
                  onChange={(e) => setEditorClassName(e.target.value)}
                  placeholder="MyOBI"
                />
              </label>
            </div>
            <Editor
              height="420px"
              defaultLanguage="python"
              value={editorSource}
              onChange={(v) => setEditorSource(v ?? '')}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                scrollBeyondLastLine: false,
              }}
            />
            {validationErrors.length > 0 && (
              <div className="banner error">
                <strong>검증 실패</strong>
                <ul>
                  {validationErrors.map((err, idx) => (
                    <li key={idx}>{err}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="form-actions">
              <button type="button" onClick={() => void saveScript()}>
                저장 + 검증
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setEditingScriptId(null)}
              >
                취소
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">Indicator Instances</span>
          <span className="count-pill">{instances.length}</span>
        </div>
        {instances.length === 0 ? (
          <div className="empty-row">활성화된 인디케이터 인스턴스가 없습니다.</div>
        ) : (
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>instance</th>
                  <th>script</th>
                  <th>symbol</th>
                  <th>params</th>
                  <th>state</th>
                  <th>output</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {instances.map((inst) => {
                  const err = errors.find((e) => e.instance_id === inst.instance_id);
                  return (
                    <tr key={inst.instance_id}>
                      <td className="mono small">{inst.instance_id}</td>
                      <td className="mono small">{inst.script_id}</td>
                      <td>{inst.symbol || '*'}</td>
                      <td className="mono small">{JSON.stringify(inst.params)}</td>
                      <td>
                        <span className={`badge ${err?.state === 'error' ? 'danger' : 'good'}`}>
                          {err?.state ?? (inst.enabled ? 'running' : 'disabled')}
                        </span>
                        {err?.last_error && (
                          <div className="sub mono small error-cell">
                            {err.last_error.slice(0, 140)}
                          </div>
                        )}
                      </td>
                      <td>{err?.output_count ?? 0}</td>
                      <td>
                        <button
                          type="button"
                          className="sm-btn danger-sm"
                          onClick={() => void deactivateInstance(inst.instance_id)}
                        >
                          해제
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
    </div>
  );
}
