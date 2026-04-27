import { useCallback, useEffect, useRef, useState } from 'react';
import GridLayout, { Layout, WidthProvider } from 'react-grid-layout';
import Editor from '@monaco-editor/react';
import * as echarts from 'echarts';
import type { EChartsOption, EChartsType, SeriesOption } from 'echarts';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import hubStubSource from '../assets/hub-stub.py?raw';

// ─── Contract types (indicator-first) ────────────────────────────────────

export interface ChartInputBinding {
  slot_name: string;
  target_id: string;
  event_name: string;
  time_field_name: string;
  field_name: string;
}

export interface ChartSeriesBinding {
  binding_id: string;
  indicator_ref: string;
  instance_id?: string;
  input_bindings: ChartInputBinding[];
  param_values: Record<string, unknown>;
  output_name: string;
  axis: 'left' | 'right';
  color: string;
  label: string;
  visible: boolean;
}

export interface ChartPanelBaseFeed {
  target_id: string;
  event_name: string;
  time_field_name: string;
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

export interface ChartPanelSpec {
  panel_id: string;
  chart_type: 'line' | 'candle';
  symbol: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title?: string | null;
  notes?: string | null;
  series_bindings: ChartSeriesBinding[];
  base_feed?: ChartPanelBaseFeed | null;
  scripts: IndicatorScriptSpec[];
  instances: IndicatorInstanceSpec[];
}

interface IndicatorInputDecl {
  slot_name: string;
  event_names: string[];
  field_hints: string[];
  required: boolean;
}
interface IndicatorParamDecl {
  name: string;
  kind: 'int' | 'float' | 'str' | 'bool' | 'enum';
  default?: unknown;
  min?: number;
  max?: number;
  choices?: unknown[];
  label?: string;
  help?: string;
}
interface IndicatorOutputDecl {
  name: string;
  kind: string;
  label: string;
  is_primary: boolean;
}
interface IndicatorDeclaration {
  inputs: IndicatorInputDecl[];
  params: IndicatorParamDecl[];
  outputs: IndicatorOutputDecl[];
}
interface IndicatorCatalogEntry {
  script_id: string;
  name: string;
  builtin: boolean;
  declaration: IndicatorDeclaration | null;
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

interface AdminRecentEventRow {
  event_name?: string;
  symbol?: string;
  published_at?: string | null;
  matched_target_ids?: string[];
  payload?: Record<string, unknown> | null;
}

type UTCTimestamp = number;
type EChartLinePoint = [number, number];
type EChartCandlePoint = [number, number, number, number, number];

// ─── LocalStorage keys ───────────────────────────────────────────────────

const LS_PREFIX = 'korea-market-data-hub.admin-charts';
const LS_PREFERRED = `${LS_PREFIX}.preferredLayout.v4`;
const LS_WORKING = `${LS_PREFIX}.workingLayout.v4`;

const DEFAULT_LAYOUT: Layout[] = [];
const CHART_LAYOUT_COLS = 12;
const MIN_CHART_LAYOUT_H = 14;
const DEFAULT_COLORS = ['#4aa3ff', '#f59e0b', '#22c55e', '#ef4444', '#a855f7', '#14b8a6'];

const ResponsiveGridLayout = WidthProvider(GridLayout);

// ─── Helpers ──────────────────────────────────────────────────────────────

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

export function clampChartLayoutItem(item: Layout): Layout {
  return {
    ...item,
    x: 0,
    w: CHART_LAYOUT_COLS,
    h: Math.max(MIN_CHART_LAYOUT_H, Number(item.h) || MIN_CHART_LAYOUT_H),
  };
}

export function clampChartLayout(layout: Layout[]): Layout[] {
  return layout.map(clampChartLayoutItem);
}

function loadLayout(key: string): Layout[] | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return clampChartLayout(parsed as Layout[]);
  } catch {
    /* ignore */
  }
  return null;
}

function saveLayout(key: string, layout: Layout[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(clampChartLayout(layout)));
  } catch {
    /* ignore */
  }
}

function paramValuesToTuples(values: Record<string, unknown>): Array<[string, unknown]> {
  return Object.entries(values);
}

function paramValuesFromAny(raw: unknown): Record<string, unknown> {
  if (!raw) return {};
  if (Array.isArray(raw)) {
    const out: Record<string, unknown> = {};
    for (const pv of raw) {
      if (Array.isArray(pv) && pv.length >= 2) out[String(pv[0])] = pv[1];
    }
    return out;
  }
  if (typeof raw === 'object') return raw as Record<string, unknown>;
  return {};
}

function scrubLegacyNormalizedBindingValue(value: unknown): unknown {
  if (typeof value === 'string' && value.startsWith('normalized.')) return '';
  return value;
}

function bindingText(value: unknown): string {
  return String(scrubLegacyNormalizedBindingValue(value) ?? '');
}

function sanitizeParamValues(values: Record<string, unknown>): Record<string, unknown> {
  return {
    ...values,
    field: scrubLegacyNormalizedBindingValue(values.field),
    time_field: scrubLegacyNormalizedBindingValue(values.time_field),
  };
}

function normalizePanel(raw: any): ChartPanelSpec {
  return {
    panel_id: raw.panel_id,
    chart_type: raw.chart_type,
    symbol: raw.symbol ?? '',
    x: raw.x ?? 0,
    y: raw.y ?? 0,
    w: raw.w ?? 12,
    h: raw.h ?? 14,
    title: raw.title ?? null,
    notes: raw.notes ?? null,
    base_feed: raw.base_feed
      ? {
          target_id: raw.base_feed.target_id ?? '',
          event_name: raw.base_feed.event_name ?? 'ohlcv',
          time_field_name: bindingText(raw.base_feed.time_field_name),
        }
      : null,
    scripts: Array.isArray(raw.scripts) ? raw.scripts : [],
    instances: Array.isArray(raw.instances) ? raw.instances : [],
    series_bindings: Array.isArray(raw.series_bindings)
      ? raw.series_bindings.map((b: any) => ({
          binding_id: b.binding_id ?? uid('bind'),
          indicator_ref: b.indicator_ref ?? '',
          instance_id: b.instance_id ?? '',
          input_bindings: Array.isArray(b.input_bindings)
            ? b.input_bindings.map((s: any) => ({
                slot_name: s.slot_name ?? '',
                target_id: s.target_id ?? '',
                event_name: s.event_name ?? '',
                time_field_name: bindingText(s.time_field_name),
                field_name: bindingText(s.field_name),
              }))
            : [],
          param_values: sanitizeParamValues(paramValuesFromAny(b.param_values)),
          output_name: b.output_name ?? '',
          axis: b.axis ?? 'left',
          color: b.color ?? '',
          label: b.label ?? '',
          visible: b.visible !== false,
        }))
      : [],
  };
}

function panelToWire(panel: ChartPanelSpec): unknown {
  return {
    ...panel,
    base_feed: panel.base_feed
      ? { ...panel.base_feed, time_field_name: bindingText(panel.base_feed.time_field_name) }
      : undefined,
    series_bindings: panel.series_bindings.map((b) => ({
      ...b,
      input_bindings: b.input_bindings.map((s) => ({
        ...s,
        time_field_name: bindingText(s.time_field_name),
        field_name: bindingText(s.field_name),
      })),
      param_values: paramValuesToTuples(sanitizeParamValues(b.param_values)),
    })),
  };
}

function pathTokens(fieldName: string): Array<string | number> | null {
  const tokens: Array<string | number> = [];
  let i = 0;
  while (i < fieldName.length) {
    if (fieldName[i] === '.') {
      i += 1;
      continue;
    }
    if (fieldName[i] === '[') {
      const end = fieldName.indexOf(']', i);
      if (end < 0) return null;
      const n = Number(fieldName.slice(i + 1, end));
      if (!Number.isInteger(n) || n < 0) return null;
      tokens.push(n);
      i = end + 1;
      continue;
    }
    let j = i;
    while (j < fieldName.length && fieldName[j] !== '.' && fieldName[j] !== '[') j += 1;
    const key = fieldName.slice(i, j);
    if (!key) return null;
    tokens.push(key);
    i = j;
  }
  return tokens;
}

export function valueAtPath(payload: Record<string, unknown> | null | undefined, fieldName: string): unknown {
  if (!payload || !fieldName) return null;
  if (fieldName in payload) return payload[fieldName];
  let cur: unknown = payload;
  const tokens = pathTokens(fieldName);
  if (!tokens) return null;
  for (const part of tokens) {
    if (typeof part === 'number') {
      if (Array.isArray(cur) && part < cur.length) cur = cur[part];
      else return null;
    } else if (cur && typeof cur === 'object' && !Array.isArray(cur) && part in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[part];
    } else {
      return null;
    }
  }
  return cur;
}

function extractScalar(payload: Record<string, unknown> | null | undefined, fieldName: string): number | null {
  const v = Number(valueAtPath(payload, fieldName));
  return Number.isFinite(v) ? v : null;
}

export function parseChartTime(raw: unknown): UTCTimestamp | null {
  if (raw == null || raw === '') return null;
  let ms: number;
  if (typeof raw === 'number') {
    ms = raw < 10_000_000_000 ? raw * 1000 : raw;
  } else if (typeof raw === 'string' && /^\d+(\.\d+)?$/.test(raw.trim())) {
    const n = Number(raw.trim());
    ms = n < 10_000_000_000 ? n * 1000 : n;
  } else {
    ms = new Date(String(raw)).getTime();
  }
  if (!Number.isFinite(ms)) return null;
  return Math.floor(ms / 1000);
}

export function extractChartTime(row: Record<string, unknown>, timeFieldName?: string): UTCTimestamp | null {
  const payload = ((row as any).__payload ?? row) as Record<string, unknown>;
  const selected = timeFieldName ? valueAtPath(payload, timeFieldName) : null;
  const raw = selected ?? (row as any).timestamp ?? (row as any).published_at ?? (row as any).occurred_at
    ?? valueAtPath(payload, 'timestamp') ?? valueAtPath(payload, 'published_at') ?? valueAtPath(payload, 'occurred_at');
  return parseChartTime(raw);
}

function scalarRawPaths(value: unknown, prefix = 'raw', depth = 0): string[] {
  const out: string[] = [];
  if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') {
    out.push(prefix);
  } else if (Array.isArray(value)) {
    if (depth >= 4) return out;
    for (let i = 0; i < Math.min(value.length, 5); i += 1) {
      out.push(...scalarRawPaths(value[i], `${prefix}[${i}]`, depth + 1));
    }
  } else if (value && typeof value === 'object') {
    if (depth >= 8) return out;
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (!k || k === 'normalized') continue;
      out.push(...scalarRawPaths(v, `${prefix}.${k}`, depth + 1));
    }
  }
  return out;
}

function uniqueOrdered(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const v of values) {
    if (!v || seen.has(v)) continue;
    seen.add(v);
    out.push(v);
  }
  return out;
}

function selectedFieldValue(fields: string[], current: string): string {
  if (!current || current.startsWith('normalized.')) return '';
  return fields.includes(current) ? current : '';
}

function sampleOptionLabel(hasTarget: boolean, hasEvent: boolean, optionCount: number, kind: 'x' | 'y'): string {
  if (!hasTarget || !hasEvent) return '— select target/event first —';
  if (optionCount > 0) return kind === 'x' ? '— x raw path —' : '— y raw path —';
  return '— sample unavailable —';
}

function rowFromRecentEvent(ev: AdminRecentEventRow): Record<string, unknown> | null {
  const eventName = String(ev.event_name ?? '');
  if (!eventName) return null;
  const payload = ev.payload ?? {};
  return {
    ...payload,
    __payload: payload,
    symbol: ev.symbol,
    event_name: eventName,
    timestamp: (payload as any).occurred_at ?? (payload as any).timestamp ?? ev.published_at,
    published_at: ev.published_at,
    occurred_at: (payload as any).occurred_at,
  } as Record<string, unknown>;
}

function selectedSamplePairs(panels: ChartPanelSpec[]): Array<{ targetId: string; eventName: string }> {
  const seen = new Set<string>();
  const out: Array<{ targetId: string; eventName: string }> = [];
  const add = (targetId?: string, eventName?: string) => {
    if (!targetId || !eventName) return;
    const key = rawSampleKey(targetId, eventName);
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ targetId, eventName });
  };
  for (const panel of panels) {
    add(panel.base_feed?.target_id, panel.base_feed?.event_name);
    for (const binding of panel.series_bindings) {
      for (const slot of binding.input_bindings) add(slot.target_id, slot.event_name);
    }
  }
  return out;
}

function syncRawFieldParam(binding: ChartSeriesBinding, slots: ChartInputBinding[]): Record<string, unknown> {
  if (binding.indicator_ref !== 'builtin.raw') return binding.param_values;
  const source = slots.find((s) => s.slot_name === 'source') ?? slots[0];
  return { ...binding.param_values, field: source?.field_name ?? '', time_field: source?.time_field_name ?? '' };
}

function isFieldParamHidden(binding: ChartSeriesBinding, paramName: string): boolean {
  return binding.indicator_ref === 'builtin.raw' && (paramName === 'field' || paramName === 'time_field');
}

function chartTimeToMs(ts: UTCTimestamp): number {
  return ts * 1000;
}

function finiteNumber(raw: unknown): number | null {
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function extractOhlc(payload: Record<string, unknown>): { open: number; high: number; low: number; close: number } | null {
  const raw = payload.raw;
  const open = finiteNumber(valueAtPath(payload, 'open') ?? valueAtPath(payload, 'raw.open') ?? (Array.isArray(raw) ? raw[1] : null));
  const high = finiteNumber(valueAtPath(payload, 'high') ?? valueAtPath(payload, 'raw.high') ?? (Array.isArray(raw) ? raw[2] : null));
  const low = finiteNumber(valueAtPath(payload, 'low') ?? valueAtPath(payload, 'raw.low') ?? (Array.isArray(raw) ? raw[3] : null));
  const close = finiteNumber(valueAtPath(payload, 'close') ?? valueAtPath(payload, 'raw.close') ?? (Array.isArray(raw) ? raw[4] : null));
  if (open == null || high == null || low == null || close == null) return null;
  return { open, high, low, close };
}

// ─── Selector helpers (target-aware events + observed raw sample fields) ──

export interface TargetCapabilityRef {
  provider: string;
  venue: string;
  instrument_type: string;
  supported_event_types: string[];
}

export interface TargetRef {
  target_id: string;
  instrument: { symbol: string; instrument_type?: string | null; venue?: string | null };
  provider?: string | null;
  event_types?: string[];
  enabled?: boolean;
}

/** Map a target → its source-capability row from the snapshot. */
export function findCapabilityForTarget(
  target: TargetRef | undefined,
  capabilities: TargetCapabilityRef[],
): TargetCapabilityRef | null {
  if (!target) return null;
  const provider = String(target.provider ?? '').toLowerCase();
  const venue = String(target.instrument?.venue ?? '').toLowerCase();
  const itype = String(target.instrument?.instrument_type ?? '').toLowerCase();
  // Strict triple match first.
  let hit = capabilities.find(
    (c) => c.provider === provider && c.venue === venue && c.instrument_type === itype,
  );
  if (hit) return hit;
  // Fallback: provider + instrument_type only (some legacy targets miss venue).
  hit = capabilities.find((c) => c.provider === provider && c.instrument_type === itype);
  return hit ?? null;
}

/** Intersect configured target events with the target's capability events. */
export function computeAllowedEvents(
  _slotEventNames: readonly string[],
  target: TargetRef | undefined,
  capability: TargetCapabilityRef | null,
): string[] {
  if (!target || target.enabled === false || !capability) return [];
  const capSet = new Set(capability.supported_event_types.map(String));
  return (target.event_types ?? []).map(String).filter((e) => capSet.has(e));
}

export type FieldOptionLayer = 'sampled' | 'empty';

export function rawSampleKey(targetId: string, eventName: string): string {
  return `${targetId}:${eventName}`;
}

export function rawRowsForTargetEvent(
  target: TargetRef | undefined,
  eventName: string,
  rawEvents: Map<string, Array<Record<string, unknown>>>,
): Array<Record<string, unknown>> {
  if (!target || !eventName) return [];
  return rawEvents.get(rawSampleKey(target.target_id, eventName)) ?? [];
}

/** Sample observed exact raw.* / raw[index] paths from raw events seen for this target+event. */
export function sampledRawPathCatalog(
  target: TargetRef | undefined,
  eventName: string,
  rawEvents: Map<string, Array<Record<string, unknown>>>,
): string[] {
  const out = new Set<string>();
  for (const row of rawRowsForTargetEvent(target, eventName, rawEvents).slice(-5)) {
    const payload = ((row as any).__payload ?? row) as Record<string, unknown>;
    if (!Object.prototype.hasOwnProperty.call(payload, 'raw')) continue;
    for (const path of scalarRawPaths((payload as any).raw, 'raw')) out.add(path);
  }
  return Array.from(out);
}

export function computeRawPathCatalog(
  eventName: string,
  target: TargetRef | undefined,
  rawEvents: Map<string, Array<Record<string, unknown>>>,
): { fields: string[]; layer: FieldOptionLayer } {
  if (!target || !eventName) return { fields: [], layer: 'empty' };
  const sampled = uniqueOrdered(sampledRawPathCatalog(target, eventName, rawEvents)).sort((a, b) => a.localeCompare(b));
  if (sampled.length > 0) return { fields: sampled, layer: 'sampled' };
  return { fields: [], layer: 'empty' };
}

export function sampledTimeFields(
  target: TargetRef | undefined,
  eventName: string,
  rawEvents: Map<string, Array<Record<string, unknown>>>,
): string[] {
  return sampledRawPathCatalog(target, eventName, rawEvents);
}

export function computeAllowedTimeFields(
  eventName: string,
  target: TargetRef | undefined,
  rawEvents: Map<string, Array<Record<string, unknown>>>,
): { fields: string[]; layer: FieldOptionLayer } {
  return computeRawPathCatalog(eventName, target, rawEvents);
}

/** Compute y/value options from the actual raw sample only. */
export function computeAllowedFields(
  eventName: string,
  target: TargetRef | undefined,
  rawEvents: Map<string, Array<Record<string, unknown>>>,
): { fields: string[]; layer: FieldOptionLayer } {
  return computeRawPathCatalog(eventName, target, rawEvents);
}

export function rawEventMirrorKeysForPanels(
  symbol: string,
  eventName: string,
  panels: ChartPanelSpec[],
  targets: TargetRef[],
): string[] {
  const keys = new Set<string>();
  for (const panel of panels) {
    for (const b of panel.series_bindings) {
      for (const slot of b.input_bindings) {
        if (!slot.target_id || !slot.event_name || slot.event_name !== eventName) continue;
        const tgt = targets.find((t) => t.target_id === slot.target_id);
        if (tgt?.instrument.symbol === symbol) keys.add(`${slot.target_id}:${eventName}`);
      }
    }
    if (panel.base_feed?.target_id) {
      const baseEvent = panel.base_feed.event_name || 'ohlcv';
      if (baseEvent !== eventName) continue;
      const tgt = targets.find((t) => t.target_id === panel.base_feed!.target_id);
      if (tgt?.instrument.symbol === symbol) keys.add(`${panel.base_feed.target_id}:${baseEvent}`);
    }
  }
  return Array.from(keys);
}

// ─── ChartPanel ───────────────────────────────────────────────────────────

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
  const chartRef = useRef<EChartsType | null>(null);
  const [chartWarnings, setChartWarnings] = useState<string[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current, 'dark', { renderer: 'canvas' });
    chartRef.current = chart;
    // ResizeObserver on the host to trigger ECharts resize defensively.
    const ro = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return;
      const { width, height } = containerRef.current.getBoundingClientRect();
      if (width > 0 && height > 0) chartRef.current.resize({ width, height });
    });
    ro.observe(containerRef.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  // Render all production chart content with ECharts.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const series: SeriesOption[] = [];
    const warnings: string[] = [];
    if (spec.chart_type === 'candle' && spec.base_feed?.target_id) {
      const key = `${spec.base_feed.target_id}:${spec.base_feed.event_name || 'ohlcv'}`;
      const rows = rawEvents.get(key) ?? [];
      const data = rows
        .map((r): EChartCandlePoint | null => {
          const ts = extractChartTime(r, spec.base_feed?.time_field_name);
          if (!ts) return null;
          const payload = ((r as any).__payload ?? r) as Record<string, unknown>;
          const ohlc = extractOhlc(payload);
          if (!ohlc) return null;
          return [chartTimeToMs(ts), ohlc.open, ohlc.close, ohlc.low, ohlc.high];
        })
        .filter((d): d is EChartCandlePoint => d != null)
        .sort((a, b) => a[0] - b[0]);
      if (rows.length > 0 && data.length === 0) {
        warnings.push('selected candle x raw path produced 0 chartable points');
      }
      series.push({
        id: 'base-candle',
        name: 'OHLCV',
        type: 'candlestick',
        data,
        itemStyle: { color: '#22c55e', color0: '#ef4444', borderColor: '#22c55e', borderColor0: '#ef4444' },
      });
    }

    spec.series_bindings.forEach((binding, idx) => {
      if (!binding.visible) return;
      const color = binding.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];

      let data: EChartLinePoint[] = [];
      if (binding.indicator_ref === 'builtin.raw') {
        // Pull from raw stream using the source slot.
        const slot = binding.input_bindings.find((s) => s.slot_name === 'source')
          ?? binding.input_bindings[0];
        if (slot && slot.target_id) {
          const key = `${slot.target_id}:${slot.event_name || 'trade'}`;
          const rows = rawEvents.get(key) ?? [];
          const field = String(slot.field_name ?? binding.param_values.field ?? '');
          const timeField = String(slot.time_field_name ?? binding.param_values.time_field ?? '');
          data = rows
            .map((r) => {
              const ts = extractChartTime(r, timeField);
              const payload = ((r as any).__payload ?? r) as Record<string, unknown>;
              const value = extractScalar(payload, field);
              if (value == null || !ts) return null;
              return [chartTimeToMs(ts), value] as EChartLinePoint;
            })
            .filter((d): d is EChartLinePoint => d != null)
            .sort((a, b) => a[0] - b[0]);
          if (field && timeField && rows.length > 0 && data.length === 0) {
            warnings.push(`${binding.label || binding.indicator_ref || 'series'} selected x/y raw paths produced 0 chartable points`);
          }
        }
      } else if (binding.instance_id) {
        // Indicator output stream.
        const pts = indicatorOutputs.get(binding.instance_id) ?? [];
        data = pts
          .map((p) => ({
            time: new Date(p.timestamp).getTime(),
            value: p.value,
          }))
          .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value))
          .map((p) => [p.time, p.value] as EChartLinePoint)
          .sort((a, b) => a[0] - b[0]);
      }
      series.push({
        id: binding.binding_id,
        name: binding.label || binding.indicator_ref || 'series',
        type: 'line',
        data,
        showSymbol: false,
        smooth: false,
        yAxisIndex: binding.axis === 'right' ? 1 : 0,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
      });
    });

    const option: EChartsOption = {
      backgroundColor: '#1a1a1a',
      animation: false,
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      grid: { left: 52, right: 52, top: 16, bottom: 48, containLabel: true },
      xAxis: { type: 'time', axisLine: { lineStyle: { color: '#475569' } }, splitLine: { lineStyle: { color: '#262626' } } },
      yAxis: [
        { type: 'value', scale: true, position: 'left', axisLine: { show: true, lineStyle: { color: '#64748b' } }, splitLine: { lineStyle: { color: '#262626' } } },
        { type: 'value', scale: true, position: 'right', axisLine: { show: true, lineStyle: { color: '#64748b' } }, splitLine: { show: false } },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        { type: 'slider', xAxisIndex: 0, height: 22, bottom: 12, filterMode: 'none' },
      ],
      series,
    };
    chart.setOption(option, { notMerge: true, lazyUpdate: false });
    setChartWarnings(warnings);
    if (containerRef.current) {
      containerRef.current.dataset.tooltip = 'axis';
      containerRef.current.dataset.dataZoom = 'inside,slider';
      containerRef.current.dataset.seriesCount = String(series.length);
    }
  }, [spec.chart_type, spec.base_feed?.target_id, spec.base_feed?.event_name, spec.base_feed?.time_field_name, spec.series_bindings, indicatorOutputs, rawEvents]);

  return (
    <>
      <div className="chart-host" data-renderer="echarts" ref={containerRef} />
      {chartWarnings.length > 0 && (
        <div className="chart-warning" role="status">
          {chartWarnings.join(' · ')}
        </div>
      )}
      {spec.series_bindings.length > 0 && (
        <div className="chart-legend">
          {spec.series_bindings
            .filter((b) => b.visible)
            .map((b, idx) => (
              <span key={b.binding_id} className="chart-legend-item">
                <span
                  className="chart-legend-dot"
                  style={{ background: b.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length] }}
                />
                {b.label || b.indicator_ref || 'series'}
              </span>
            ))}
        </div>
      )}
    </>
  );
}

// ─── PanelInspector (declaration-driven) ─────────────────────────────────

function ParamWidget({
  decl,
  value,
  onChange,
}: {
  decl: IndicatorParamDecl;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const eff = value === undefined ? decl.default : value;
  if (decl.kind === 'enum' && Array.isArray(decl.choices)) {
    return (
      <select value={String(eff ?? '')} onChange={(e) => onChange(e.target.value)}>
        {decl.choices.map((c) => (
          <option key={String(c)} value={String(c)}>
            {String(c)}
          </option>
        ))}
      </select>
    );
  }
  if (decl.kind === 'bool') {
    return (
      <input
        type="checkbox"
        checked={Boolean(eff)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (decl.kind === 'int' || decl.kind === 'float') {
    return (
      <input
        type="number"
        value={eff == null ? '' : String(eff)}
        min={decl.min as number | undefined}
        max={decl.max as number | undefined}
        step={decl.kind === 'int' ? 1 : 'any'}
        onChange={(e) => {
          const n = Number(e.target.value);
          onChange(Number.isFinite(n) ? n : 0);
        }}
      />
    );
  }
  return (
    <input
      type="text"
      value={eff == null ? '' : String(eff)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function PanelInspector({
  panel,
  targets,
  indicators,
  capabilities,
  rawEvents,
  onChange,
  onDelete,
  onAddPanelScript,
  onSavePanelScript,
}: {
  panel: ChartPanelSpec;
  targets: TargetRef[];
  indicators: IndicatorCatalogEntry[];
  capabilities: TargetCapabilityRef[];
  rawEvents: Map<string, Array<Record<string, unknown>>>;
  onChange: (next: ChartPanelSpec) => void;
  onDelete: () => void;
  onAddPanelScript: () => void;
  onSavePanelScript: (script: IndicatorScriptSpec) => void;
}) {
  const [editingScriptId, setEditingScriptId] = useState<string | null>(null);
  const [editorSource, setEditorSource] = useState<string>(hubStubSource);
  const [editorName, setEditorName] = useState<string>('');
  const [editorClassName, setEditorClassName] = useState<string>('MyInd');

  function commit(next: ChartPanelSpec) {
    onChange(next);
  }

  function updateBinding(idx: number, patch: Partial<ChartSeriesBinding>) {
    const next = panel.series_bindings.map((b, i) => (i === idx ? { ...b, ...patch } : b));
    commit({ ...panel, series_bindings: next });
  }

  function removeBinding(idx: number) {
    commit({ ...panel, series_bindings: panel.series_bindings.filter((_, i) => i !== idx) });
  }

  function addBinding() {
    const fresh: ChartSeriesBinding = {
      binding_id: uid('bind'),
      indicator_ref: 'builtin.raw',
      instance_id: '',
      input_bindings: [
        { slot_name: 'source', target_id: '', event_name: '', time_field_name: '', field_name: '' },
      ],
      param_values: { field: '', time_field: '' },
      output_name: 'value',
      axis: 'left',
      color: '',
      label: '',
      visible: true,
    };
    commit({ ...panel, series_bindings: [...panel.series_bindings, fresh] });
  }

  function setBaseFeed(patch: Partial<ChartPanelBaseFeed>) {
    const cur = panel.base_feed ?? { target_id: '', event_name: 'ohlcv', time_field_name: '' };
    const next = { ...cur, ...patch };
    if ('target_id' in patch && !patch.target_id) {
      next.event_name = '';
      next.time_field_name = '';
    } else if ('target_id' in patch || 'event_name' in patch) {
      next.time_field_name = '';
    }
    commit({ ...panel, base_feed: next });
  }

  function getDeclaration(ref: string): IndicatorDeclaration | null {
    return indicators.find((i) => i.script_id === ref)?.declaration ?? null;
  }

  const baseTarget = targets.find((t) => t.target_id === (panel.base_feed?.target_id ?? ''));
  const baseCapability = findCapabilityForTarget(baseTarget, capabilities);
  const baseAllowedEvents = computeAllowedEvents([], baseTarget, baseCapability);
  const baseTimeRes = computeRawPathCatalog(panel.base_feed?.event_name ?? '', baseTarget, rawEvents);
  const baseTimeFields = baseTimeRes.fields;

  return (
    <div className="charts-inspector">
      <div className="inspector-section">
        <div className="inspector-section-head">
          <span className="eyebrow">Panel</span>
          <button type="button" className="sm-btn danger-sm" onClick={onDelete}>
            패널 삭제
          </button>
        </div>
        <label className="field">
          <span>Title</span>
          <input
            value={panel.title ?? ''}
            onChange={(e) => commit({ ...panel, title: e.target.value })}
          />
        </label>
        <div className="binding-row-grid">
          <div className="field">
            <span>Type</span>
            <span className="badge muted">{panel.chart_type}</span>
          </div>
          <label className="field">
            <span>Symbol (label)</span>
            <input
              value={panel.symbol ?? ''}
              onChange={(e) => commit({ ...panel, symbol: e.target.value })}
            />
          </label>
        </div>
      </div>

      {panel.chart_type === 'candle' && (
        <div className="inspector-section">
          <span className="eyebrow">Base feed (OHLCV)</span>
          <label className="field">
            <span>Target</span>
            <select
              value={panel.base_feed?.target_id ?? ''}
              onChange={(e) => setBaseFeed({ target_id: e.target.value })}
            >
              <option value="">— target —</option>
              {targets.map((t) => (
                <option key={t.target_id} value={t.target_id}>
                  {t.instrument.symbol} ({t.target_id.slice(0, 8)})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Event</span>
            <select
              value={baseTarget ? (panel.base_feed?.event_name ?? 'ohlcv') : ''}
              onChange={(e) => setBaseFeed({ event_name: e.target.value })}
              disabled={!baseTarget}
            >
              {!baseTarget && <option value="">— select target first —</option>}
              {baseTarget && !baseAllowedEvents.includes(panel.base_feed?.event_name ?? '') && <option value="">— event —</option>}
              {baseAllowedEvents.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>x raw path <small className="hint-inline">({baseTimeRes.layer})</small></span>
            <select
              value={selectedFieldValue(baseTimeFields, panel.base_feed?.time_field_name ?? '')}
              onChange={(e) => setBaseFeed({ time_field_name: e.target.value })}
              disabled={!baseTarget || !(panel.base_feed?.event_name) || baseTimeFields.length === 0}
            >
              {selectedFieldValue(baseTimeFields, panel.base_feed?.time_field_name ?? '') === '' && (
                <option value="">{sampleOptionLabel(Boolean(baseTarget), Boolean(panel.base_feed?.event_name), baseTimeFields.length, 'x')}</option>
              )}
              {baseTimeFields.map((h) => (
                <option key={h} value={h}>{h}</option>
              ))}
            </select>
          </label>
        </div>
      )}

      <div className="inspector-section">
        <div className="inspector-section-head">
          <span className="eyebrow">
            {panel.chart_type === 'candle' ? 'Overlays' : 'Series'} ({panel.series_bindings.length})
          </span>
          <button type="button" className="sm-btn" onClick={addBinding}>
            + 추가
          </button>
        </div>
        {panel.series_bindings.length === 0 && (
          <div className="empty-row">
            {panel.chart_type === 'candle' ? '오버레이가 없습니다.' : '시리즈가 없습니다.'}
          </div>
        )}
        {panel.series_bindings.map((binding, idx) => {
          const decl = getDeclaration(binding.indicator_ref);
          return (
            <div key={binding.binding_id} className="binding-row">
              <div className="binding-row-head">
                <strong>#{idx + 1}</strong>
                <button type="button" className="sm-btn danger-sm" onClick={() => removeBinding(idx)}>
                  삭제
                </button>
              </div>
              <label className="field">
                <span>Indicator</span>
                <select
                  value={binding.indicator_ref}
                  onChange={(e) => {
                    const ref = e.target.value;
                    const d = getDeclaration(ref);
                    const defaults: Record<string, unknown> = {};
                    for (const p of d?.params ?? []) defaults[p.name] = p.default;
                    const slots = (d?.inputs ?? []).map((inp) => ({
                      slot_name: inp.slot_name,
                      target_id: '',
                      event_name: '',
                      time_field_name: '',
                      field_name: '',
                    }));
                    updateBinding(idx, {
                      indicator_ref: ref,
                      input_bindings: slots,
                      param_values: defaults,
                      output_name:
                        d?.outputs.find((o) => o.is_primary)?.name ?? d?.outputs[0]?.name ?? '',
                    });
                  }}
                >
                  <option value="">— select —</option>
                  {indicators.map((i) => (
                    <option key={i.script_id} value={i.script_id}>
                      {i.name} {i.builtin ? '(built-in)' : ''}
                    </option>
                  ))}
                </select>
              </label>

              {/* Inputs */}
              {decl && decl.inputs.length > 0 && (
                <div className="field">
                  <span>Inputs</span>
                  {decl.inputs.map((inp) => {
                    const slot = binding.input_bindings.find((s) => s.slot_name === inp.slot_name) ?? {
                      slot_name: inp.slot_name,
                      target_id: '',
                      event_name: '',
                      time_field_name: '',
                      field_name: '',
                    };
                    const slotTarget = targets.find((t) => t.target_id === slot.target_id);
                    const capability = findCapabilityForTarget(slotTarget, capabilities);
                    const allowedEvents = computeAllowedEvents(inp.event_names, slotTarget, capability);
                    const fieldRes = computeAllowedFields(
                      slot.event_name,
                      slotTarget,
                      rawEvents,
                    );
                    const timeFieldRes = computeRawPathCatalog(slot.event_name, slotTarget, rawEvents);
                    const timeFields = timeFieldRes.fields;
                    const valueFields = fieldRes.fields;
                    const showCompatibilityWarning = binding.indicator_ref !== 'builtin.raw'
                      && slot.event_name
                      && inp.event_names.length > 0
                      && !inp.event_names.includes(slot.event_name);
                    function patchSlot(patch: Partial<ChartInputBinding>) {
                      const next = { ...slot, ...patch };
                      // Cascade: target change → re-evaluate event; event change
                      // (or stale event after target change) → re-evaluate field.
                      const newTarget = targets.find((t) => t.target_id === next.target_id);
                      const newCap = findCapabilityForTarget(newTarget, capabilities);
                      const newAllowedEvents = computeAllowedEvents(inp.event_names, newTarget, newCap);
                      if (!newTarget) {
                        next.event_name = '';
                        next.time_field_name = '';
                        next.field_name = '';
                      } else if ('target_id' in patch || !next.event_name || !newAllowedEvents.includes(next.event_name)) {
                        next.event_name = '';
                        next.time_field_name = '';
                        next.field_name = '';
                      } else if ('event_name' in patch) {
                        next.time_field_name = '';
                        next.field_name = '';
                      }
                      const newTimeFieldRes = computeRawPathCatalog(next.event_name, newTarget, rawEvents);
                      if (next.time_field_name && !newTimeFieldRes.fields.includes(next.time_field_name)) {
                        next.time_field_name = '';
                      }
                      const newFieldRes = computeAllowedFields(
                        next.event_name,
                        newTarget,
                        rawEvents,
                      );
                      if (next.field_name && !newFieldRes.fields.includes(next.field_name)) {
                        next.field_name = '';
                      }
                      const others = binding.input_bindings.filter((s) => s.slot_name !== inp.slot_name);
                      const input_bindings = [...others, next];
                      updateBinding(idx, {
                        input_bindings,
                        param_values: syncRawFieldParam(binding, input_bindings),
                      });
                    }
                    return (
                      <div key={inp.slot_name} className="binding-row-grid">
                        <label className="field">
                          <span>{inp.slot_name}: target</span>
                          <select
                            value={slot.target_id}
                            onChange={(e) => patchSlot({ target_id: e.target.value })}
                          >
                            <option value="">— target —</option>
                            {targets.map((t) => (
                              <option key={t.target_id} value={t.target_id}>
                                {t.instrument.symbol}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>event</span>
                          <select
                            value={allowedEvents.includes(slot.event_name) ? slot.event_name : ''}
                            onChange={(e) => patchSlot({ event_name: e.target.value })}
                            disabled={!slotTarget || allowedEvents.length === 0}
                          >
                            {!allowedEvents.includes(slot.event_name) && (
                              <option value="">{slotTarget ? '— event —' : '— select target first —'}</option>
                            )}
                            {allowedEvents.map((e) => (
                              <option key={e} value={e}>{e}</option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>x raw path <small className="hint-inline">({timeFieldRes.layer})</small></span>
                          <select
                            value={selectedFieldValue(timeFields, slot.time_field_name)}
                            onChange={(e) => patchSlot({ time_field_name: e.target.value })}
                            disabled={!slotTarget || !slot.event_name || timeFields.length === 0}
                          >
                            {selectedFieldValue(timeFields, slot.time_field_name) === '' && (
                              <option value="">{sampleOptionLabel(Boolean(slotTarget), Boolean(slot.event_name), timeFields.length, 'x')}</option>
                            )}
                            {timeFields.map((h) => (
                              <option key={h} value={h}>{h}</option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>y raw path <small className="hint-inline">({fieldRes.layer})</small></span>
                          <select
                            value={selectedFieldValue(valueFields, slot.field_name)}
                            onChange={(e) => patchSlot({ field_name: e.target.value })}
                            disabled={!slotTarget || !slot.event_name || valueFields.length === 0}
                          >
                            {selectedFieldValue(valueFields, slot.field_name) === '' && (
                              <option value="">{sampleOptionLabel(Boolean(slotTarget), Boolean(slot.event_name), valueFields.length, 'y')}</option>
                            )}
                            {valueFields.map((h) => (
                              <option key={h} value={h}>{h}</option>
                            ))}
                          </select>
                        </label>
                        {showCompatibilityWarning && (
                          <small className="hint-inline warning-inline">
                            selected event is outside this indicator declaration metadata
                          </small>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Params */}
              {decl && decl.params.some((p) => !isFieldParamHidden(binding, p.name)) && (
                <div className="field">
                  <span>Params</span>
                  {decl.params.filter((p) => !isFieldParamHidden(binding, p.name)).map((p) => (
                    <label key={p.name} className="field">
                      <span>{p.label || p.name}</span>
                      <ParamWidget
                        decl={p}
                        value={binding.param_values[p.name]}
                        onChange={(v) =>
                          updateBinding(idx, {
                            param_values: { ...binding.param_values, [p.name]: v },
                          })
                        }
                      />
                      {p.help && <small className="hint-inline">{p.help}</small>}
                    </label>
                  ))}
                </div>
              )}

              {/* Output */}
              {decl && decl.outputs.length > 0 && (
                <label className="field">
                  <span>Output</span>
                  <select
                    value={binding.output_name}
                    onChange={(e) => updateBinding(idx, { output_name: e.target.value })}
                  >
                    {decl.outputs.map((o) => (
                      <option key={o.name} value={o.name}>
                        {o.label || o.name} ({o.kind})
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {/* Style */}
              <div className="binding-row-grid">
                <label className="field">
                  <span>Axis</span>
                  <select
                    value={binding.axis}
                    onChange={(e) => updateBinding(idx, { axis: e.target.value as 'left' | 'right' })}
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

      <div className="inspector-section">
        <div className="inspector-section-head">
          <span className="eyebrow">Scripts ({panel.scripts.length})</span>
          <button
            type="button"
            className="sm-btn"
            onClick={() => {
              setEditingScriptId(uid('script'));
              setEditorSource(hubStubSource);
              setEditorName('새 인디케이터');
              setEditorClassName('MyInd');
              onAddPanelScript();
            }}
          >
            + 새 스크립트
          </button>
        </div>
        {panel.scripts.length === 0 && (
          <div className="empty-row">패널 전용 커스텀 인디케이터가 없습니다.</div>
        )}
        {panel.scripts.map((s) => (
          <div key={s.script_id} className="binding-row">
            <strong>{s.name}</strong>
            <small className="hint-inline">{s.class_name}</small>
            <div className="row-actions">
              <button
                type="button"
                className="sm-btn"
                onClick={() => {
                  setEditingScriptId(s.script_id);
                  setEditorSource(s.source || hubStubSource);
                  setEditorName(s.name);
                  setEditorClassName(s.class_name);
                }}
              >
                편집
              </button>
            </div>
          </div>
        ))}
        {editingScriptId && (
          <div className="script-editor">
            <label className="field">
              <span>이름</span>
              <input value={editorName} onChange={(e) => setEditorName(e.target.value)} />
            </label>
            <label className="field">
              <span>클래스명</span>
              <input value={editorClassName} onChange={(e) => setEditorClassName(e.target.value)} />
            </label>
            <Editor
              height="280px"
              defaultLanguage="python"
              value={editorSource}
              onChange={(v) => setEditorSource(v ?? '')}
              theme="vs-dark"
              options={{ minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false }}
            />
            <div className="form-actions">
              <button
                type="button"
                onClick={() => {
                  onSavePanelScript({
                    script_id: editingScriptId,
                    name: editorName,
                    source: editorSource,
                    class_name: editorClassName,
                    builtin: false,
                  });
                  setEditingScriptId(null);
                }}
              >
                저장
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
      </div>
    </div>
  );
}

// ─── Main ChartsView ─────────────────────────────────────────────────────

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
    instrument: { symbol: string; instrument_type?: string | null; venue?: string | null };
    provider?: string | null;
    event_types?: string[];
    enabled?: boolean;
  }>;
  onRefresh?: () => void | Promise<void>;
}

export default function ChartsView({ capabilities, targets, onRefresh }: ChartsViewProps) {
  const [panels, setPanels] = useState<ChartPanelSpec[]>([]);
  const [indicatorsByPanel, setIndicatorsByPanel] = useState<Map<string, IndicatorCatalogEntry[]>>(
    new Map(),
  );
  const [globalIndicators, setGlobalIndicators] = useState<IndicatorCatalogEntry[]>([]);
  const [errors, setErrors] = useState<IndicatorErrorRow[]>([]);
  const [banner, setBanner] = useState('');
  const [bannerError, setBannerError] = useState(false);
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null);

  const [layout, setLayout] = useState<Layout[]>(
    () => clampChartLayout(loadLayout(LS_WORKING) ?? loadLayout(LS_PREFERRED) ?? DEFAULT_LAYOUT),
  );

  const [indicatorOutputs, setIndicatorOutputs] = useState<Map<string, SeriesPoint[]>>(new Map());
  const [rawEvents, setRawEvents] = useState<Map<string, Array<Record<string, unknown>>>>(new Map());

  const panelsRef = useRef<ChartPanelSpec[]>(panels);
  const targetsRef = useRef<TargetRef[]>(targets);

  useEffect(() => { panelsRef.current = panels; }, [panels]);
  useEffect(() => { targetsRef.current = targets; }, [targets]);

  const refresh = useCallback(async () => {
    try {
      const [p, e, ind] = await Promise.all([
        apiJson<{ panels: any[] }>('/api/admin/charts/panels'),
        apiJson<{ instances: IndicatorErrorRow[] }>('/api/admin/charts/errors'),
        apiJson<{ indicators: IndicatorCatalogEntry[] }>('/api/admin/charts/indicators'),
      ]);
      setPanels((p.panels ?? []).map(normalizePanel));
      setErrors(e.instances ?? []);
      setGlobalIndicators(ind.indicators ?? []);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'charts state load failed');
      setBannerError(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void onRefresh?.();
  }, [onRefresh]);

  function ingestRawEventRow(
    prev: Map<string, Array<Record<string, unknown>>>,
    eventName: string,
    targetIds: string[],
    row: Record<string, unknown>,
  ): Map<string, Array<Record<string, unknown>>> {
    if (!eventName || targetIds.length === 0) return prev;
    const next = new Map(prev);
    for (const targetId of targetIds) {
      if (!targetId) continue;
      const key = rawSampleKey(targetId, eventName);
      const cur = next.get(key) ?? [];
      next.set(key, [...cur, row].slice(-500));
    }
    return next;
  }

  // Raw sample catalog is populated only for explicitly selected target/event pairs.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const pairs = selectedSamplePairs(panels);
      for (const pair of pairs) {
        try {
          const resp = await apiJson<{ recent_events?: AdminRecentEventRow[] }>(
            `/api/admin/events?target_id=${encodeURIComponent(pair.targetId)}&event_name=${encodeURIComponent(pair.eventName)}&limit=50`,
          );
          if (cancelled) return;
          const rows = (resp.recent_events ?? [])
            .filter((ev) => String(ev.event_name ?? '') === pair.eventName)
            .map(rowFromRecentEvent)
            .filter((row): row is Record<string, unknown> => row != null)
            .slice(-50);
          setRawEvents((prev) => {
            const next = new Map(prev);
            next.set(rawSampleKey(pair.targetId, pair.eventName), rows);
            return next;
          });
        } catch {
          if (cancelled) return;
          setRawEvents((prev) => {
            const next = new Map(prev);
            next.set(rawSampleKey(pair.targetId, pair.eventName), []);
            return next;
          });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [panels]);

  // Per-panel indicators fetch (built-ins + panel scripts).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next = new Map<string, IndicatorCatalogEntry[]>();
      for (const panel of panels) {
        try {
          const resp = await apiJson<{ indicators: IndicatorCatalogEntry[] }>(
            `/api/admin/charts/indicators?panel_id=${encodeURIComponent(panel.panel_id)}`,
          );
          next.set(panel.panel_id, resp.indicators ?? []);
        } catch {
          next.set(panel.panel_id, globalIndicators);
        }
      }
      if (!cancelled) setIndicatorsByPanel(next);
    })();
    return () => { cancelled = true; };
  }, [panels, globalIndicators]);

  // SSE stream.
  useEffect(() => {
    const es = new EventSource('/api/admin/charts/stream');
    es.addEventListener('indicator_output', (evt: MessageEvent) => {
      try {
        const payload = JSON.parse(evt.data) as IndicatorOutputEnvelope;
        setIndicatorOutputs((prev) => {
          const next = new Map(prev);
          const cur = next.get(payload.instance_id) ?? [];
          next.set(payload.instance_id, [...cur, payload.point].slice(-500));
          return next;
        });
      } catch { /* ignore */ }
    });
    es.addEventListener('raw_event', (evt: MessageEvent) => {
      try {
        const envelope = JSON.parse(evt.data) as {
          symbol?: string;
          event_name?: string;
          timestamp?: string | null;
          published_at?: string | null;
          payload?: Record<string, unknown> | null;
        };
        const symbol = envelope.symbol;
        const eventName = envelope.event_name;
        if (!symbol || !eventName) return;
        const row = {
          ...(envelope.payload ?? {}),
          __payload: envelope.payload ?? {},
          symbol,
          event_name: eventName,
          timestamp: envelope.timestamp,
          published_at: envelope.published_at,
          occurred_at: (envelope.payload as any)?.occurred_at,
        } as Record<string, unknown>;
        setRawEvents((prev) => {
          const targetKeys = rawEventMirrorKeysForPanels(
            symbol,
            eventName,
            panelsRef.current,
            targetsRef.current,
          ).map((key) => key.split(':')[0]);
          return ingestRawEventRow(prev, eventName, targetKeys, row);
        });
      } catch { /* ignore */ }
    });
    return () => es.close();
  }, []);

  // Sync layout with panels.
  useEffect(() => {
    setLayout((prev) => {
      const byId = new Map(prev.map((l) => [l.i, l] as const));
      let nextY = prev.reduce((m, l) => Math.max(m, l.y + l.h), 0);
      const merged: Layout[] = [];
      for (const panel of panels) {
        const existing = byId.get(panel.panel_id);
        if (existing) {
          merged.push(clampChartLayoutItem(existing));
        } else {
          merged.push(clampChartLayoutItem({
            i: panel.panel_id,
            x: panel.x ?? 0,
            y: nextY,
            w: panel.w ?? CHART_LAYOUT_COLS,
            h: panel.h ?? MIN_CHART_LAYOUT_H,
          }));
          nextY += Math.max(MIN_CHART_LAYOUT_H, panel.h ?? MIN_CHART_LAYOUT_H);
        }
      }
      return merged;
    });
  }, [panels]);

  useEffect(() => {
    saveLayout(LS_WORKING, clampChartLayout(layout));
  }, [layout]);

  // ── actions ──

  async function persistPanel(next: ChartPanelSpec) {
    try {
      const resp = await apiJson<{ panel: any }>('/api/admin/charts/panels', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(panelToWire(next)),
      });
      const normalized = normalizePanel(resp.panel);
      setPanels((prev) => prev.map((p) => (p.panel_id === normalized.panel_id ? normalized : p)));
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'update panel failed');
      setBannerError(true);
    }
  }

  async function addPanel(chartType: 'line' | 'candle') {
    const tgt = targets[0];
    try {
      const body: any = {
        chart_type: chartType,
        symbol: tgt?.instrument.symbol ?? '',
        x: 0, y: 0, w: 12, h: 14,
        title: chartType === 'candle' ? 'Candle' : 'Line',
        series_bindings: [],
      };
      if (chartType === 'candle' && tgt) {
        body.base_feed = { target_id: tgt.target_id, event_name: 'ohlcv', time_field_name: '' };
      }
      const resp = await apiJson<{ panel: any }>('/api/admin/charts/panels', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const normalized = normalizePanel(resp.panel);
      setPanels((prev) => [...prev, normalized]);
      setSelectedPanelId(normalized.panel_id);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'add panel failed');
      setBannerError(true);
    }
  }

  async function removePanel(panelId: string) {
    try {
      await apiJson(`/api/admin/charts/panels/${encodeURIComponent(panelId)}`, { method: 'DELETE' });
      setPanels((prev) => prev.filter((p) => p.panel_id !== panelId));
      if (selectedPanelId === panelId) setSelectedPanelId(null);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : 'delete panel failed');
      setBannerError(true);
    }
  }

  function savePreferredLayout() {
    saveLayout(LS_PREFERRED, clampChartLayout(layout));
    setBanner('선호 레이아웃 저장됨.');
    setBannerError(false);
  }

  function restorePreferredLayout() {
    const preferred = loadLayout(LS_PREFERRED);
    if (preferred) {
      setLayout(clampChartLayout(preferred));
      setBanner('선호 레이아웃 복원됨.');
      setBannerError(false);
    }
  }

  const persistTimeoutRef = useRef<number | null>(null);
  function onInspectorChange(next: ChartPanelSpec) {
    setPanels((prev) => prev.map((p) => (p.panel_id === next.panel_id ? next : p)));
    if (persistTimeoutRef.current != null) window.clearTimeout(persistTimeoutRef.current);
    persistTimeoutRef.current = window.setTimeout(() => void persistPanel(next), 350);
  }

  const selectedPanel = panels.find((p) => p.panel_id === selectedPanelId) ?? null;
  const layoutKey = `lk-${panels.length}`;

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
            <div className="empty-row">패널이 없습니다. + 버튼으로 추가하세요.</div>
          ) : (
            <ResponsiveGridLayout
              key={layoutKey}
              className="layout"
              cols={CHART_LAYOUT_COLS}
              rowHeight={40}
              layout={layout}
              onLayoutChange={(next) => setLayout(clampChartLayout(next))}
              draggableHandle=".panel-drag-handle"
              isDraggable
              isResizable
              useCSSTransforms
              measureBeforeMount
              margin={[8, 8]}
            >
              {panels.map((panel) => {
                const isSelected = panel.panel_id === selectedPanelId;
                return (
                  <div
                    key={panel.panel_id}
                    className={`chart-wrapper${isSelected ? ' selected' : ''}`}
                    onClick={() => setSelectedPanelId(panel.panel_id)}
                  >
                    <div className="chart-wrapper-head">
                      <span className="panel-drag-handle" title="drag">⋮⋮</span>
                      <strong>
                        {panel.title || `${panel.chart_type.toUpperCase()} · ${panel.symbol || '—'}`}
                      </strong>
                      <span className="badge muted">{panel.chart_type}</span>
                      <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="sm-btn danger-sm"
                          onClick={() => void removePanel(panel.panel_id)}
                        >
                          삭제
                        </button>
                      </div>
                    </div>
                    <ChartPanel
                      spec={panel}
                      indicatorOutputs={indicatorOutputs}
                      rawEvents={rawEvents}
                    />
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
              targets={targets}
              indicators={indicatorsByPanel.get(selectedPanel.panel_id) ?? globalIndicators}
              capabilities={capabilities}
              rawEvents={rawEvents}
              onChange={onInspectorChange}
              onDelete={() => void removePanel(selectedPanel.panel_id)}
              onAddPanelScript={() => { /* placeholder; editing gates by inspector state */ }}
              onSavePanelScript={(script) => {
                const next = {
                  ...selectedPanel,
                  scripts: selectedPanel.scripts.some((s) => s.script_id === script.script_id)
                    ? selectedPanel.scripts.map((s) => (s.script_id === script.script_id ? script : s))
                    : [...selectedPanel.scripts, script],
                };
                onInspectorChange(next);
              }}
            />
          ) : (
            <div className="empty-row">왼쪽 패널을 클릭해 편집하세요.</div>
          )}
        </aside>
      </div>

      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">Indicator Errors</span>
          <span className="count-pill">{errors.filter((e) => e.state === 'error').length}</span>
        </div>
        {errors.length === 0 ? (
          <div className="empty-row">활성화된 인스턴스 오류 없음.</div>
        ) : (
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>instance</th>
                  <th>script</th>
                  <th>symbol</th>
                  <th>state</th>
                  <th>output</th>
                </tr>
              </thead>
              <tbody>
                {errors.map((row) => (
                  <tr key={row.instance_id}>
                    <td className="mono small">{row.instance_id}</td>
                    <td className="mono small">{row.script_id}</td>
                    <td>{row.symbol || '*'}</td>
                    <td>
                      <span className={`badge ${row.state === 'error' ? 'danger' : 'good'}`}>
                        {row.state}
                      </span>
                      {row.last_error && (
                        <div className="sub mono small error-cell">{row.last_error.slice(0, 200)}</div>
                      )}
                    </td>
                    <td>{row.output_count}</td>
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
