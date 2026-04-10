from __future__ import annotations

import asyncio
import json
from datetime import datetime
from textwrap import dedent
from typing import Any

import pandas as pd
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from src.config import settings
from src.kis_websocket import KISProgramTradeClient


app = FastAPI(title="KIS Program Trade Realtime")


HTML = dedent(
    """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>KIS Program Trade Realtime</title>
      <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/gridstack@10.3.1/dist/gridstack.min.css" />
      <script src="https://cdn.jsdelivr.net/npm/gridstack@10.3.1/dist/gridstack-all.min.js"></script>
      <style>
        :root {
          color-scheme: dark;
          --bg: #050b14;
          --bg-2: #08111e;
          --panel: #09111d;
          --panel-2: #0d1726;
          --panel-border: rgba(148, 163, 184, 0.14);
          --grid: rgba(148, 163, 184, 0.08);
          --muted: #7f93b0;
          --text: #dce7f6;
          --accent: #38bdf8;
          --accent-2: #22c55e;
          --danger: #f87171;
          --warn: #facc15;
          --ask: #ff6b7a;
          --ask-soft: rgba(255, 107, 122, 0.18);
          --bid: #34d399;
          --bid-soft: rgba(52, 211, 153, 0.16);
        }
        * { box-sizing: border-box; }
        body { font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: var(--bg); color: var(--text); }
        .wrap { max-width: 1680px; margin: 0 auto; padding: 8px; }
        .sub { color: var(--muted); font-size: 12px; }
        .controls { display: grid; gap: 6px; }
        .controls { grid-template-columns: minmax(180px, 1fr) 120px 160px 160px; margin-bottom: 8px; }
        .dashboard { min-height: 760px; }
        .grid-stack { background: transparent; }
        .grid-stack > .grid-stack-item { min-width: 0; }
        .grid-stack > .grid-stack-item > .grid-stack-item-content { inset: 0; overflow: hidden; background: transparent; }
        .dashboard-widget { min-width: 280px; min-height: 220px; }
        .widget-frame { display: flex; flex-direction: column; height: 100%; background: var(--panel); border: 1px solid var(--panel-border); overflow: hidden; }
        .widget-handle { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px; border-bottom: 1px solid rgba(148, 163, 184, 0.08); background: rgba(8, 15, 27, 0.9); cursor: move; user-select: none; touch-action: none; }
        .widget-title { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; }
        .widget-note { color: var(--muted); font-size: 11px; }
        .widget-body { flex: 1; min-height: 0; padding: 8px; overflow: hidden; display: flex; flex-direction: column; }
        .panel { background: var(--panel); border: 1px solid var(--panel-border); border-radius: 0; box-shadow: none; }
        .panel { padding: 8px; display: flex; flex-direction: column; flex: 1; min-height: 0; }
        .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; }
        .chart-header-tools { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .title { font-size: 14px; font-weight: 800; letter-spacing: 0.02em; }
        .label { color: var(--muted); font-size: 10px; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.08em; }
        .value { font-size: 22px; font-weight: 800; line-height: 1.15; }
        .value.small { font-size: 17px; }
        .value.tiny { font-size: 15px; }
        input, select, button { border-radius: 0; border: 1px solid rgba(148, 163, 184, 0.16); background: #09111d; color: var(--text); padding: 9px 10px; font-size: 13px; }
        button { cursor: pointer; background: #0f3d91; border: 1px solid rgba(56, 189, 248, 0.18); font-weight: 800; }
        button.secondary { background: rgba(51, 65, 85, 0.92); }
        .tick-toggle, .series-toggle { display: inline-flex; align-items: center; gap: 4px; padding: 3px; border: 1px solid rgba(148, 163, 184, 0.14); background: rgba(8, 15, 27, 0.82); }
        .tick-toggle-label { color: var(--muted); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; margin-right: 2px; }
        .tick-btn, .series-btn, .price-mode-btn { min-width: 32px; padding: 5px 8px; font-size: 11px; background: transparent; border: 1px solid transparent; color: var(--muted); }
        .tick-btn.active, .series-btn.active, .price-mode-btn.active { background: rgba(56, 189, 248, 0.14); border-color: rgba(56, 189, 248, 0.28); color: #e0f2fe; }
        .chart-canvas { width: 100%; flex: 1; min-height: 0; height: 100%; }
        .orderbook-shell { margin: 0 -8px -8px; padding: 0; background: transparent; border: none; display: flex; flex-direction: column; flex: 1; min-height: 0; }
        .orderbook-scroll { flex: 1; min-height: 0; overflow: auto; }
        .ladder-header { display: grid; grid-template-columns: 1fr 82px 70px; gap: 0; color: var(--muted); font-size: 10px; padding: 0 0 4px; letter-spacing: 0.06em; text-transform: uppercase; border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
        .ladder-header > div { padding: 0 6px; }
        .orderbook-table, .history-table { width: 100%; border-collapse: collapse; border-spacing: 0; font-size: 12px; }
        .orderbook-table th, .orderbook-table td, .history-table th, .history-table td { padding: 4px 6px; text-align: right; }
        .orderbook-table td { padding-top: 0; padding-bottom: 0; }
        .history-table { border-spacing: 0; }
        .history-table th, .history-table td { border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
        .orderbook-table th:first-child, .orderbook-table td:first-child, .history-table th:first-child, .history-table td:first-child { text-align: left; }
        .orderbook-table tbody tr { background: rgba(8, 15, 27, 0.72); border-bottom: none; }
        .orderbook-table tr.ask .price, .down { color: #ff9aa6; }
        .orderbook-table tr.bid .price, .up { color: #8ef0c0; }
        .orderbook-table tr.latest-match { background: rgba(250, 204, 21, 0.08); box-shadow: inset 3px 0 0 rgba(250, 204, 21, 0.8); }
        .orderbook-table tr.latest-match .price { color: #fde68a; }
        .bar-cell { width: 100%; }
        .qty-track { position: relative; height: 18px; overflow: hidden; background: rgba(148, 163, 184, 0.03); border: none; }
        .qty-fill { position: absolute; top: 0; bottom: 0; left: 0; border-radius: 0; }
        .qty-fill.ask { background: rgba(255, 107, 122, 0.72); }
        .qty-fill.bid { background: rgba(52, 211, 153, 0.75); }
        .qty-value { position: relative; z-index: 1; display: flex; align-items: center; justify-content: flex-end; height: 100%; padding: 0 4px; font-weight: 700; font-size: 10px; color: #edf5ff; }
        .depth-summary { display: grid; grid-template-columns: 1fr; gap: 8px; padding: 6px 0 8px; border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
        .depth-compare { display: grid; gap: 4px; }
        .depth-compare-header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
        .depth-compare-header .label { margin-bottom: 0; }
        .depth-compare-note { color: var(--muted); font-size: 10px; letter-spacing: 0.04em; }
        .imbalance-bar { position: relative; height: 32px; overflow: hidden; background: rgba(148, 163, 184, 0.08); display: flex; }
        .imbalance-fill { height: 100%; min-width: 0; }
        .imbalance-ask { background: rgba(255, 107, 122, 0.82); }
        .imbalance-bid { background: rgba(52, 211, 153, 0.82); }
        .imbalance-overlay { position: absolute; inset: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); pointer-events: none; }
        .imbalance-text { display: flex; flex-direction: column; justify-content: center; gap: 1px; padding: 0 8px; color: #f8fafc; font-size: 11px; font-weight: 800; line-height: 1.15; }
        .imbalance-text strong, .imbalance-text span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .imbalance-text strong { font-size: 11px; }
        .imbalance-text span { font-size: 10px; opacity: 0.96; }
        .imbalance-text.ask { text-align: left; }
        .imbalance-text.bid { text-align: right; }
        .toast { position: fixed; left: 50%; bottom: 24px; transform: translate(-50%, 12px); padding: 10px 14px; background: rgba(8, 15, 27, 0.96); color: #f8fafc; border: 1px solid rgba(148, 163, 184, 0.22); box-shadow: 0 10px 24px rgba(0, 0, 0, 0.28); font-size: 12px; font-weight: 700; opacity: 0; pointer-events: none; transition: opacity 0.18s ease, transform 0.18s ease; z-index: 1000; }
        .toast.visible { opacity: 1; transform: translate(-50%, 0); }
        .dashboard-widget[data-widget="history"] .table-scroll { flex: 1; min-height: 0; max-height: none; }
        .table-scroll { overflow: auto; flex: 1; min-height: 0; max-height: none; }
        .footer { margin-top: 8px; color: var(--muted); font-size: 11px; }
        @media (max-width: 1180px) {
          .dashboard { min-height: 0; }
          .dashboard-widget { min-width: 0; }
        }
        @media (max-width: 760px) {
          .controls { grid-template-columns: 1fr; }
          .ladder-header { grid-template-columns: 1fr 80px 64px; }
        }
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="controls">
          <input id="symbol" value="005930" placeholder="종목코드" />
          <select id="market">
            <option value="krx">KRX</option>
            <option value="nxt">NXT</option>
            <option value="total">TOTAL</option>
          </select>
          <button id="saveDefaultLayoutBtn" class="secondary">현재 배치를 기본값으로 저장</button>
          <button id="resetLayoutBtn" class="secondary">기본 레이아웃 복원</button>
        </div>

        <div id="dashboard" class="dashboard grid-stack">
          <div class="grid-stack-item dashboard-widget" gs-x="0" gs-y="0" gs-w="6" gs-h="4" gs-min-w="4" gs-min-h="3" data-widget="program-chart">
            <div class="grid-stack-item-content">
            <div class="widget-frame">
              <div class="widget-handle">
                <div class="widget-title">프로그램 순매수 차트</div>
                <div class="widget-note">그리드 정렬 이동 / 리사이즈</div>
              </div>
              <div class="widget-body">
                <div class="panel-header">
                  <div class="chart-header-tools">
                    <div class="series-toggle" aria-label="프로그램 차트 기준 선택">
                      <span class="tick-toggle-label">지표</span>
                      <button class="series-btn active" data-program-mode="qty">체결량</button>
                      <button class="series-btn" data-program-mode="amt">거래대금</button>
                    </div>
                  </div>
                </div>
                <div id="programChart" class="chart-canvas"></div>
               </div>
             </div>
             </div>
          </div>

          <div class="grid-stack-item dashboard-widget" gs-x="0" gs-y="4" gs-w="6" gs-h="4" gs-min-w="4" gs-min-h="3" data-widget="trade-price-chart">
            <div class="grid-stack-item-content">
            <div class="widget-frame">
              <div class="widget-handle">
                <div class="widget-title">가격 차트</div>
                <div class="widget-note">그리드 정렬 이동 / 리사이즈</div>
              </div>
              <div class="widget-body">
                <div class="panel-header">
                  <div class="chart-header-tools">
                    <div class="tick-toggle" aria-label="가격 차트 모드 선택">
                      <span class="tick-toggle-label">모드</span>
                      <button class="price-mode-btn active" data-price-mode="tick-1">1틱</button>
                      <button class="price-mode-btn" data-price-mode="tick-5">5틱</button>
                      <button class="price-mode-btn" data-price-mode="tick-10">10틱</button>
                      <button class="price-mode-btn" data-price-mode="tick-30">30틱</button>
                      <button class="price-mode-btn" data-price-mode="minute-10">10분</button>
                      <button class="price-mode-btn" data-price-mode="minute-30">30분</button>
                      <button class="price-mode-btn" data-price-mode="minute-60">60분</button>
                    </div>
                    <div class="sub" id="priceModeLabel">1틱 라인</div>
                  </div>
                </div>
                <div id="tradePriceChart" class="chart-canvas"></div>
               </div>
             </div>
             </div>
          </div>

          <div class="grid-stack-item dashboard-widget" gs-x="6" gs-y="0" gs-w="3" gs-h="8" gs-min-w="3" gs-min-h="4" data-widget="orderbook">
            <div class="grid-stack-item-content">
            <div class="widget-frame">
              <div class="widget-handle">
                <div class="widget-title">실시간 호가</div>
                <div id="bookTime" class="widget-note">-</div>
              </div>
              <div class="widget-body">
                <div class="depth-summary">
                  <div class="depth-compare">
                    <div class="depth-compare-header">
                      <div class="label">전체 호가 잔량 비교</div>
                      <div id="depthSummaryNote" class="depth-compare-note">-</div>
                    </div>
                    <div class="imbalance-bar">
                      <div id="imbalanceAskBar" class="imbalance-fill imbalance-ask" style="width:50%"></div>
                      <div id="imbalanceBidBar" class="imbalance-fill imbalance-bid" style="width:50%"></div>
                      <div class="imbalance-overlay">
                        <div id="askPressure" class="imbalance-text ask">-</div>
                        <div id="bidPressure" class="imbalance-text bid">-</div>
                      </div>
                    </div>
                  </div>
                  <div class="depth-compare">
                    <div class="depth-compare-header">
                      <div class="label">프로그램 호가 잔량 비교</div>
                      <div class="depth-compare-note">program_trade 기준</div>
                    </div>
                    <div class="imbalance-bar">
                      <div id="programAskBar" class="imbalance-fill imbalance-ask" style="width:50%"></div>
                      <div id="programBidBar" class="imbalance-fill imbalance-bid" style="width:50%"></div>
                      <div class="imbalance-overlay">
                        <div id="programAskPressure" class="imbalance-text ask">-</div>
                        <div id="programBidPressure" class="imbalance-text bid">-</div>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="orderbook-shell">
                  <div class="orderbook-scroll">
                      <div class="ladder-header">
                       <div>Depth</div>
                       <div>Price</div>
                       <div>Qty</div>
                      </div>
                    <table class="orderbook-table">
                      <tbody id="orderbookBody">
                        <tr><td colspan="3" style="text-align:center; color:#93a4bf;">호가 수신 대기 중</td></tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
            </div>
          </div>

          <div class="grid-stack-item dashboard-widget" gs-x="9" gs-y="0" gs-w="3" gs-h="8" gs-min-w="3" gs-min-h="4" data-widget="history">
            <div class="grid-stack-item-content">
            <div class="widget-frame">
              <div class="widget-handle">
                <div class="widget-title">체결 히스토리</div>
                <div class="widget-note">최신 데이터가 위로 누적됩니다.</div>
              </div>
              <div class="widget-body">
                <table class="history-table">
                  <thead>
                    <tr>
                      <th>체결시각</th>
                      <th>순매수 체결량</th>
                      <th>순매수 거래대금</th>
                      <th>매도잔량</th>
                      <th>매수잔량</th>
                    </tr>
                  </thead>
                </table>
                <div class="table-scroll">
                  <table class="history-table">
                    <tbody id="historyBody">
                      <tr><td colspan="5" style="text-align:center; color:#93a4bf;">수신 대기 중</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            </div>
          </div>
        </div>

        <div class="footer">브라우저 연결 동안 서버가 프로그램매매, 호가, 현재가 체결 웹소켓을 함께 구독해 대시보드를 갱신합니다.</div>
        <div id="layoutToast" class="toast" role="status" aria-live="polite"></div>
      </div>

      <script>
        let eventSource = null;
        const maxPoints = 120;
        const tickOptions = [1, 5, 10, 30];
        const maxTickSize = Math.max(...tickOptions);
        const maxRawPoints = maxPoints * maxTickSize;
        const maxHistory = 60;
        const reconnectDelayMs = 1200;
        const minuteRefreshMs = 30000;
        const workingLayoutStorageKey = 'kis-program-trade-realtime.dashboard-layout.v3';
        const preferredLayoutStorageKey = 'kis-program-trade-realtime.dashboard-layout.preferred.v3';
        const historyRows = [];
        const rawProgramTrades = [];
        const rawTradePrices = [];
        const priceModeConfig = {
          'tick-1': { type: 'tick', size: 1, label: '1틱 라인' },
          'tick-5': { type: 'tick', size: 5, label: '5틱 라인' },
          'tick-10': { type: 'tick', size: 10, label: '10틱 라인' },
          'tick-30': { type: 'tick', size: 30, label: '30틱 라인' },
          'minute-10': { type: 'minute', size: 10, label: '10분 캔들' },
          'minute-30': { type: 'minute', size: 30, label: '30분 캔들' },
          'minute-60': { type: 'minute', size: 60, label: '60분 캔들' },
        };
        let currentOrderBook = null;
        let currentTradePrice = null;
        let currentProgramDepth = null;
        let selectedPriceMode = 'tick-1';
        let selectedProgramMode = 'qty';
        let toastTimer = null;
        let reconnectTimer = null;
        let minuteRefreshTimer = null;
        let streamToken = 0;
        let unloading = false;

        const chartGridColor = '#24314f';
        const chartTextColor = '#cbd5e1';
        const dashboard = document.getElementById('dashboard');
        const grid = GridStack.init({
          column: 12,
          cellHeight: 92,
          margin: 8,
          minRow: 8,
          animate: false,
          float: false,
          oneColumnSize: 1180,
          draggable: { handle: '.widget-handle', scroll: false },
          resizable: { handles: 'all' },
        }, dashboard);
        const programChart = echarts.init(document.getElementById('programChart'), null, { renderer: 'canvas' });
        const tradePriceChart = echarts.init(document.getElementById('tradePriceChart'), null, { renderer: 'canvas' });
        const shippedDefaultLayout = Array.from(document.querySelectorAll('.dashboard-widget')).map((widget) => ({
          id: widget.dataset.widget,
          x: Number(widget.getAttribute('gs-x') || 0),
          y: Number(widget.getAttribute('gs-y') || 0),
          w: Number(widget.getAttribute('gs-w') || 1),
          h: Number(widget.getAttribute('gs-h') || 1),
        }));

        const makeLineChartOption = (seriesName, color) => ({
          animation: false,
          backgroundColor: 'transparent',
          grid: { left: 52, right: 18, top: 18, bottom: 34 },
          legend: {
            top: 0,
            left: 0,
            itemWidth: 14,
            itemHeight: 2,
            textStyle: { color: chartTextColor, fontSize: 11 }
          },
          tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'line' },
            backgroundColor: 'rgba(9, 17, 29, 0.96)',
            borderColor: 'rgba(148, 163, 184, 0.22)',
            textStyle: { color: '#e5e7eb' }
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: [],
            axisLine: { lineStyle: { color: chartGridColor } },
            axisTick: { show: false },
            axisLabel: { color: chartTextColor, fontSize: 10, hideOverlap: true },
            splitLine: { show: false }
          },
          yAxis: {
            type: 'value',
            scale: true,
            axisLine: { show: false },
            axisTick: { show: false },
            axisLabel: { color: chartTextColor, fontSize: 10 },
            splitLine: { lineStyle: { color: chartGridColor, width: 1 } }
          },
          series: [{
            name: seriesName,
            type: 'line',
            data: [],
            showSymbol: false,
            smooth: 0.18,
            lineStyle: { color, width: 1.4 },
            itemStyle: { color },
            emphasis: { focus: 'series' }
          }]
        });

        const makeCandlestickChartOption = () => ({
          animation: false,
          backgroundColor: 'transparent',
          grid: { left: 52, right: 18, top: 18, bottom: 34 },
          tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(9, 17, 29, 0.96)',
            borderColor: 'rgba(148, 163, 184, 0.22)',
            textStyle: { color: '#e5e7eb' }
          },
          xAxis: {
            type: 'category',
            data: [],
            axisLine: { lineStyle: { color: chartGridColor } },
            axisTick: { show: false },
            axisLabel: { color: chartTextColor, fontSize: 10, hideOverlap: true },
            splitLine: { show: false }
          },
          yAxis: {
            type: 'value',
            scale: true,
            axisLine: { show: false },
            axisTick: { show: false },
            axisLabel: { color: chartTextColor, fontSize: 10 },
            splitLine: { lineStyle: { color: chartGridColor, width: 1 } }
          },
          series: [{
            name: '가격',
            type: 'candlestick',
            data: [],
            itemStyle: {
              color: '#ef4444',
              color0: '#22c55e',
              borderColor: '#ef4444',
              borderColor0: '#22c55e'
            }
          }]
        });

        const chartState = {
          programChart: { labels: [], data: [], label: '순매수 체결량', color: '#22c55e' },
          tradePriceChart: { labels: [], data: [], label: '가격', color: '#facc15', chartType: 'line' }
        };

        programChart.setOption(makeLineChartOption(chartState.programChart.label, chartState.programChart.color));
        tradePriceChart.setOption(makeLineChartOption(chartState.tradePriceChart.label, chartState.tradePriceChart.color));

        function showToast(message) {
          const toastEl = document.getElementById('layoutToast');
          if (!toastEl) return;
          toastEl.textContent = message;
          toastEl.classList.add('visible');
          if (toastTimer) {
            window.clearTimeout(toastTimer);
          }
          toastTimer = window.setTimeout(() => {
            toastEl.classList.remove('visible');
          }, 1800);
        }

        function setStatus(text) {
          const statusEl = document.getElementById('status');
          if (statusEl) {
            statusEl.textContent = text;
          }
        }

        function resizeDashboardCharts() {
          requestAnimationFrame(() => {
            programChart.resize();
            tradePriceChart.resize();
          });
        }

        function getCurrentLayout() {
          return Array.from(document.querySelectorAll('.dashboard-widget')).map((widget) => {
            const node = widget.gridstackNode || {};
            return {
              id: widget.dataset.widget,
              x: Number(node.x ?? widget.getAttribute('gs-x') ?? 0),
              y: Number(node.y ?? widget.getAttribute('gs-y') ?? 0),
              w: Number(node.w ?? widget.getAttribute('gs-w') ?? 1),
              h: Number(node.h ?? widget.getAttribute('gs-h') ?? 1),
            };
          });
        }

        function saveLayout() {
          try {
            localStorage.setItem(workingLayoutStorageKey, JSON.stringify(getCurrentLayout()));
          } catch (error) {
            console.warn('레이아웃 저장 실패', error);
          }
        }

        function savePreferredLayout() {
          try {
            const layout = getCurrentLayout();
            localStorage.setItem(preferredLayoutStorageKey, JSON.stringify(layout));
            localStorage.setItem(workingLayoutStorageKey, JSON.stringify(layout));
            showToast('기본 레이아웃을 저장했습니다.');
          } catch (error) {
            console.warn('기본 레이아웃 저장 실패', error);
            showToast('기본 레이아웃 저장에 실패했습니다.');
          }
        }

        function readStoredLayout(storageKey) {
          try {
            const saved = localStorage.getItem(storageKey);
            if (!saved) return null;
            const parsed = JSON.parse(saved);
            const savedIds = new Set(Array.isArray(parsed) ? parsed.map((item) => item?.id).filter(Boolean) : []);
            const hasAllWidgets = shippedDefaultLayout.every((item) => savedIds.has(item.id));
            if (!hasAllWidgets) {
              localStorage.removeItem(storageKey);
              return null;
            }
            return parsed;
          } catch (error) {
            console.warn('저장된 레이아웃 읽기 실패', error);
            return null;
          }
        }

        function applyLayout(layout) {
          if (!Array.isArray(layout) || !layout.length) return;
          grid.batchUpdate();
          layout.forEach((item) => {
            const widget = dashboard.querySelector(`[data-widget="${item.id}"]`);
            if (!widget) return;
            grid.update(widget, {
              x: Number(item.x ?? 0),
              y: Number(item.y ?? 0),
              w: Number(item.w ?? widget.getAttribute('gs-w') ?? 1),
              h: Number(item.h ?? widget.getAttribute('gs-h') ?? 1),
            });
          });
          grid.batchUpdate(false);
          resizeDashboardCharts();
        }

        function restoreLayout() {
          const layout = readStoredLayout(workingLayoutStorageKey)
            || readStoredLayout(preferredLayoutStorageKey)
            || shippedDefaultLayout;
          applyLayout(layout);
        }

        function resetLayout() {
          localStorage.removeItem(workingLayoutStorageKey);
          const layout = readStoredLayout(preferredLayoutStorageKey) || shippedDefaultLayout;
          applyLayout(layout);
          saveLayout();
        }

        function formatNumber(value) {
          if (value === null || value === undefined || value === '') return '-';
          return new Intl.NumberFormat('ko-KR').format(value);
        }

        function formatTime(value) {
          if (!value) return '-';
          const text = String(value).trim();
          if (/^[0-9]{6}$/.test(text)) {
            return `${text.slice(0, 2)}:${text.slice(2, 4)}:${text.slice(4, 6)}`;
          }
          return text;
        }

        function syncLineChart(chart, state) {
          chart.setOption({
            xAxis: { data: state.labels },
            series: [{ data: state.data }]
          });
        }

        function syncCandlestickChart(chart, labels, data) {
          chart.setOption({
            xAxis: { data: labels },
            series: [{ data }]
          });
        }

        function ensurePriceChartType(chartType) {
          if (chartState.tradePriceChart.chartType === chartType) return;
          chartState.tradePriceChart.chartType = chartType;
          if (chartType === 'candlestick') {
            tradePriceChart.clear();
            tradePriceChart.setOption(makeCandlestickChartOption());
          } else {
            tradePriceChart.clear();
            tradePriceChart.setOption(makeLineChartOption(chartState.tradePriceChart.label, chartState.tradePriceChart.color));
          }
        }

        function updatePriceModeLabel() {
          document.getElementById('priceModeLabel').textContent = priceModeConfig[selectedPriceMode].label;
        }

        function updateProgramChartHeader() {
          const nextLabel = selectedProgramMode === 'qty' ? '순매수 체결량' : '순매수 거래대금';
          const nextColor = selectedProgramMode === 'qty' ? '#22c55e' : '#38bdf8';
          chartState.programChart.label = nextLabel;
          chartState.programChart.color = nextColor;
          programChart.setOption({
            legend: { data: [nextLabel] },
            series: [{ name: nextLabel, lineStyle: { color: nextColor }, itemStyle: { color: nextColor } }]
          });
        }

        function aggregateProgramTrades() {
          const labels = [];
          const data = [];

          for (const item of rawProgramTrades) {
            labels.push(item.label);
            data.push(selectedProgramMode === 'qty' ? item.qty : item.amt);
          }

          chartState.programChart.labels = labels.slice(-maxPoints);
          chartState.programChart.data = data.slice(-maxPoints);
          updateProgramChartHeader();
          syncLineChart(programChart, chartState.programChart);
        }

        function appendRawProgramTrade(item) {
          rawProgramTrades.push({
            label: formatTime(item['체결시각'] || item['received_at'] || ''),
            qty: safeNumber(item['프로그램순매수체결량']) || 0,
            amt: safeNumber(item['프로그램순매수거래대금']) || 0,
          });

          if (rawProgramTrades.length > maxRawPoints) {
            rawProgramTrades.splice(0, rawProgramTrades.length - maxRawPoints);
          }

          aggregateProgramTrades();
        }

        function aggregateTradePrices() {
          const mode = priceModeConfig[selectedPriceMode];
          if (!mode || mode.type !== 'tick') return;
          const labels = [];
          const data = [];

          for (let index = 0; index < rawTradePrices.length; index += mode.size) {
            const bucket = rawTradePrices.slice(index, index + mode.size);
            if (!bucket.length) continue;
            const lastItem = bucket[bucket.length - 1];
            labels.push(lastItem.label);
            data.push(lastItem.price);
          }

          ensurePriceChartType('line');
          chartState.tradePriceChart.labels = labels.slice(-maxPoints);
          chartState.tradePriceChart.data = data.slice(-maxPoints);
          syncLineChart(tradePriceChart, chartState.tradePriceChart);
        }

        function appendRawTradePrice(item) {
          rawTradePrices.push({
            label: formatTime(item['체결시각'] || item['received_at'] || ''),
            price: safeNumber(item['현재가']) || 0,
          });

          if (rawTradePrices.length > maxRawPoints) {
            rawTradePrices.splice(0, rawTradePrices.length - maxRawPoints);
          }

          if (priceModeConfig[selectedPriceMode].type === 'tick') {
            aggregateTradePrices();
          }
        }

        async function refreshMinuteChart() {
          const mode = priceModeConfig[selectedPriceMode];
          if (!mode || mode.type !== 'minute') return;
          const symbol = document.getElementById('symbol').value.trim();
          const market = document.getElementById('market').value;
          if (!symbol) return;

          const response = await fetch(`/api/price-chart?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(market)}&interval=${encodeURIComponent(mode.size)}`);
          if (!response.ok) {
            throw new Error(`minute chart fetch failed: ${response.status}`);
          }

          const payload = await response.json();
          const candles = Array.isArray(payload.candles) ? payload.candles : [];
          ensurePriceChartType('candlestick');
          chartState.tradePriceChart.labels = candles.map((item) => item.label);
          chartState.tradePriceChart.data = candles.map((item) => [item.open, item.close, item.low, item.high]);
          syncCandlestickChart(tradePriceChart, chartState.tradePriceChart.labels, chartState.tradePriceChart.data);
        }

        function scheduleMinuteRefresh(immediate = false) {
          if (minuteRefreshTimer) {
            window.clearTimeout(minuteRefreshTimer);
            minuteRefreshTimer = null;
          }
          if (priceModeConfig[selectedPriceMode].type !== 'minute') return;

          const run = async () => {
            try {
              await refreshMinuteChart();
            } catch (error) {
              console.warn('분봉 차트 갱신 실패', error);
            } finally {
              if (!unloading && priceModeConfig[selectedPriceMode].type === 'minute') {
                minuteRefreshTimer = window.setTimeout(run, minuteRefreshMs);
              }
            }
          };

          minuteRefreshTimer = window.setTimeout(run, immediate ? 0 : minuteRefreshMs);
        }

        function setPriceMode(modeKey) {
          selectedPriceMode = modeKey;
          document.querySelectorAll('.price-mode-btn').forEach((button) => {
            button.classList.toggle('active', button.dataset.priceMode === selectedPriceMode);
          });
          updatePriceModeLabel();
          if (priceModeConfig[selectedPriceMode].type === 'tick') {
            if (minuteRefreshTimer) {
              window.clearTimeout(minuteRefreshTimer);
              minuteRefreshTimer = null;
            }
            aggregateTradePrices();
          } else {
            scheduleMinuteRefresh(true);
          }
        }

        function setProgramMode(mode) {
          selectedProgramMode = mode;
          document.querySelectorAll('.series-btn').forEach((button) => {
            button.classList.toggle('active', button.dataset.programMode === selectedProgramMode);
          });
          aggregateProgramTrades();
        }

        function resetCharts() {
          rawProgramTrades.length = 0;
          rawTradePrices.length = 0;
          for (const [key, chart] of [['programChart', programChart], ['tradePriceChart', tradePriceChart]]) {
            chartState[key].labels = [];
            chartState[key].data = [];
          }
          syncLineChart(programChart, chartState.programChart);
          ensurePriceChartType(priceModeConfig[selectedPriceMode].type === 'minute' ? 'candlestick' : 'line');
          if (chartState.tradePriceChart.chartType === 'candlestick') {
            syncCandlestickChart(tradePriceChart, [], []);
          } else {
            syncLineChart(tradePriceChart, chartState.tradePriceChart);
          }
          updateProgramChartHeader();
          updatePriceModeLabel();
        }

        function resetTables() {
          historyRows.length = 0;
          currentOrderBook = null;
          currentTradePrice = null;
          currentProgramDepth = null;
          document.getElementById('historyBody').innerHTML = '<tr><td colspan="5" style="text-align:center; color:#93a4bf;">수신 대기 중</td></tr>';
          document.getElementById('orderbookBody').innerHTML = '<tr><td colspan="3" style="text-align:center; color:#93a4bf;">호가 수신 대기 중</td></tr>';
          document.getElementById('bookTime').textContent = '-';
          document.getElementById('depthSummaryNote').textContent = '-';
          document.getElementById('askPressure').textContent = '-';
          document.getElementById('bidPressure').textContent = '-';
          document.getElementById('imbalanceAskBar').style.width = '50%';
          document.getElementById('imbalanceBidBar').style.width = '50%';
          document.getElementById('programAskPressure').textContent = '-';
          document.getElementById('programBidPressure').textContent = '-';
          document.getElementById('programAskBar').style.width = '50%';
          document.getElementById('programBidBar').style.width = '50%';
        }

        function safeNumber(value) {
          const numeric = Number(value);
          return Number.isFinite(numeric) ? numeric : null;
        }

        function formatPercent(value) {
          if (value === null || value === undefined || Number.isNaN(value)) return '-';
          return `${value.toFixed(1)}%`;
        }

        function makeQtyBar(quantity, side, maxQty) {
          const qty = safeNumber(quantity) || 0;
          const width = maxQty > 0 ? Math.max(6, (qty / maxQty) * 100) : 0;
          return `
            <div class="qty-track">
              <div class="qty-fill ${side}" style="width:${width}%"></div>
              <div class="qty-value">${formatNumber(qty)}</div>
            </div>
          `;
        }

        function formatDepthBarText(label, quantity, ratio) {
          return `<strong>${label} ${formatPercent(ratio)}</strong><span>${formatNumber(quantity)}</span>`;
        }

        function updateComparisonBar(askValue, bidValue, elements) {
          const askQty = safeNumber(askValue) || 0;
          const bidQty = safeNumber(bidValue) || 0;
          const total = askQty + bidQty;
          const askRatio = total > 0 ? (askQty / total) * 100 : 50;
          const bidRatio = total > 0 ? (bidQty / total) * 100 : 50;
          document.getElementById(elements.askText).innerHTML = formatDepthBarText('매도', askQty, askRatio);
          document.getElementById(elements.bidText).innerHTML = formatDepthBarText('매수', bidQty, bidRatio);
          document.getElementById(elements.askBar).style.width = `${askRatio}%`;
          document.getElementById(elements.bidBar).style.width = `${bidRatio}%`;
          return { askQty, bidQty, askRatio, bidRatio, total };
        }

        function renderOrderBook() {
          const tbody = document.getElementById('orderbookBody');
          if (!currentOrderBook) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:#93a4bf;">호가 수신 대기 중</td></tr>';
            return;
          }

          const askLevels = Array.from({ length: 10 }, (_, index) => 10 - index);
          const bidLevels = Array.from({ length: 10 }, (_, index) => index + 1);
          const rows = [];
          const quantities = [];
          const latestTradePrice = safeNumber(currentTradePrice?.['현재가']);

          askLevels.forEach((level) => quantities.push(safeNumber(currentOrderBook[`매도잔량${level}`]) || 0));
          bidLevels.forEach((level) => quantities.push(safeNumber(currentOrderBook[`매수잔량${level}`]) || 0));
          const maxQty = Math.max(...quantities, 1);

          askLevels.forEach((level) => {
            const price = safeNumber(currentOrderBook[`매도호가${level}`]);
            const isLatestMatch = latestTradePrice !== null && price === latestTradePrice;
            rows.push(`
              <tr class="ask${isLatestMatch ? ' latest-match' : ''}">
                <td class="bar-cell">${makeQtyBar(currentOrderBook[`매도잔량${level}`], 'ask', maxQty)}</td>
                <td class="price">${formatNumber(currentOrderBook[`매도호가${level}`])}</td>
                <td>${formatNumber(currentOrderBook[`매도잔량${level}`])}</td>
              </tr>
            `);
          });

          bidLevels.forEach((level) => {
            const price = safeNumber(currentOrderBook[`매수호가${level}`]);
            const isLatestMatch = latestTradePrice !== null && price === latestTradePrice;
            rows.push(`
              <tr class="bid${isLatestMatch ? ' latest-match' : ''}">
                <td class="bar-cell">${makeQtyBar(currentOrderBook[`매수잔량${level}`], 'bid', maxQty)}</td>
                <td class="price">${formatNumber(currentOrderBook[`매수호가${level}`])}</td>
                <td>${formatNumber(currentOrderBook[`매수잔량${level}`])}</td>
              </tr>
            `);
          });

          tbody.innerHTML = rows.join('');
        }

        function renderHistory() {
          const tbody = document.getElementById('historyBody');
          if (!historyRows.length) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#93a4bf;">수신 대기 중</td></tr>';
            return;
          }

          tbody.innerHTML = historyRows.map((item) => `
            <tr>
              <td>${formatTime(item['체결시각'])}</td>
              <td class="${(item['프로그램순매수체결량'] || 0) >= 0 ? 'up' : 'down'}">${formatNumber(item['프로그램순매수체결량'])}</td>
              <td class="${(item['프로그램순매수거래대금'] || 0) >= 0 ? 'up' : 'down'}">${formatNumber(item['프로그램순매수거래대금'])}</td>
              <td>${formatNumber(item['매도호가잔량'])}</td>
              <td>${formatNumber(item['매수호가잔량'])}</td>
            </tr>
          `).join('');
        }

        function updateHistory(item) {
          historyRows.unshift(item);
          if (historyRows.length > maxHistory) {
            historyRows.length = maxHistory;
          }
          renderHistory();
        }

        function updateDepthSummary(item) {
          const summary = updateComparisonBar(item['총매도잔량'], item['총매수잔량'], {
            askText: 'askPressure',
            bidText: 'bidPressure',
            askBar: 'imbalanceAskBar',
            bidBar: 'imbalanceBidBar',
          });
          document.getElementById('depthSummaryNote').textContent = `총 ${formatNumber(summary.total)}`;
        }

        function updateProgramDepthSummary(item) {
          currentProgramDepth = item;
          updateComparisonBar(item['매도호가잔량'], item['매수호가잔량'], {
            askText: 'programAskPressure',
            bidText: 'programBidPressure',
            askBar: 'programAskBar',
            bidBar: 'programBidBar',
          });
        }

        function updateOrderBook(item) {
          currentOrderBook = item;
          renderOrderBook();
          document.getElementById('bookTime').textContent = formatTime(item['호가시각']);
          updateDepthSummary(item);
        }

        function updateTradePrice(item) {
          currentTradePrice = item;
          appendRawTradePrice(item);
          renderOrderBook();
        }

        function closeStream() {
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
        }

        function getCurrentSelection() {
          const symbol = document.getElementById('symbol').value.trim();
          const market = document.getElementById('market').value;
          return { symbol, market };
        }

        function scheduleReconnect() {
          if (unloading || reconnectTimer) return;
          reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;
            connectStream();
          }, reconnectDelayMs);
        }

        function connectStream() {
          const { symbol, market } = getCurrentSelection();
          if (!symbol) {
            closeStream();
            return;
          }

          if (reconnectTimer) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = null;
          }

          const token = ++streamToken;
          closeStream();

          resetCharts();
          resetTables();
          scheduleMinuteRefresh(true);
          eventSource = new EventSource(`/stream?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(market)}`);

          eventSource.addEventListener('program_trade', (event) => {
            if (token !== streamToken) return;
            const item = JSON.parse(event.data);
            appendRawProgramTrade(item);
            updateProgramDepthSummary(item);
            updateHistory(item);
          });

          eventSource.addEventListener('order_book', (event) => {
            if (token !== streamToken) return;
            const item = JSON.parse(event.data);
            updateOrderBook(item);
          });

          eventSource.addEventListener('trade_price', (event) => {
            if (token !== streamToken) return;
            const item = JSON.parse(event.data);
            updateTradePrice(item);
          });

          eventSource.addEventListener('error', async () => {
            if (token !== streamToken || unloading) return;
            closeStream();
            scheduleReconnect();
          });
        }

        function handleSelectionChange() {
          connectStream();
        }

        document.getElementById('saveDefaultLayoutBtn').addEventListener('click', savePreferredLayout);
        document.getElementById('resetLayoutBtn').addEventListener('click', resetLayout);
        document.getElementById('symbol').addEventListener('change', handleSelectionChange);
        document.getElementById('symbol').addEventListener('keydown', (event) => {
          if (event.key === 'Enter') {
            handleSelectionChange();
          }
        });
        document.getElementById('market').addEventListener('change', handleSelectionChange);
        document.querySelectorAll('.price-mode-btn').forEach((button) => {
          button.addEventListener('click', () => setPriceMode(button.dataset.priceMode));
        });
        document.querySelectorAll('.series-btn').forEach((button) => {
          button.addEventListener('click', () => setProgramMode(button.dataset.programMode));
        });
        const widgetResizeObserver = new ResizeObserver(() => resizeDashboardCharts());
        document.querySelectorAll('.dashboard-widget').forEach((widget) => widgetResizeObserver.observe(widget));
        restoreLayout();
        grid.on('change resizestop dragstop', () => {
          saveLayout();
          resizeDashboardCharts();
        });
        window.addEventListener('resize', () => {
          resizeDashboardCharts();
        });
        const shutdown = () => {
          unloading = true;
          if (reconnectTimer) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = null;
          }
          if (minuteRefreshTimer) {
            window.clearTimeout(minuteRefreshTimer);
            minuteRefreshTimer = null;
          }
          closeStream();
        };
        window.addEventListener('beforeunload', shutdown);
        window.addEventListener('pagehide', shutdown);
        updateProgramChartHeader();
        updatePriceModeLabel();
        resizeDashboardCharts();
        saveLayout();
        connectStream();
      </script>
    </body>
    </html>
    """
)


def to_native_dict(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in record.items():
        if pd.isna(value):
            normalized[key] = None
        elif hasattr(value, "item"):
            normalized[key] = value.item()
        else:
            normalized[key] = value
    return normalized


def _aggregate_minute_candles(rows: list[dict[str, Any]], interval: int) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for row in rows:
        time_text = str(row.get("stck_cntg_hour") or "").strip()
        if len(time_text) != 6 or not time_text.isdigit():
            continue

        try:
            price = float(row.get("stck_prpr", 0) or 0)
            open_price = float(row.get("stck_oprc", 0) or 0)
            high_price = float(row.get("stck_hgpr", 0) or 0)
            low_price = float(row.get("stck_lwpr", 0) or 0)
            volume = int(float(row.get("cntg_vol", 0) or 0))
        except (TypeError, ValueError):
            continue

        point_time = datetime.strptime(time_text, "%H%M%S")
        bucket_minute = (point_time.minute // interval) * interval
        bucket_time = point_time.replace(minute=bucket_minute, second=0)
        bucket_key = bucket_time.strftime("%H%M")

        if current is None or current["key"] != bucket_key:
            current = {
                "key": bucket_key,
                "label": bucket_time.strftime("%H:%M"),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": price,
                "volume": volume,
            }
            buckets.append(current)
        else:
            current["high"] = max(current["high"], high_price)
            current["low"] = min(current["low"], low_price)
            current["close"] = price
            current["volume"] += volume

    return buckets[-120:]


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/api/price-chart")
async def price_chart(
    symbol: str = Query(..., min_length=1),
    market: str = Query("krx", pattern="^(krx|nxt|total)$"),
    interval: int = Query(..., ge=10, le=60),
) -> JSONResponse:
    if interval not in {10, 30, 60}:
        return JSONResponse({"error": "unsupported interval"}, status_code=400)

    client = KISProgramTradeClient(settings)
    rows = client.fetch_intraday_chart(symbol=symbol, market=market)
    candles = _aggregate_minute_candles(rows, interval)
    return JSONResponse({
        "symbol": symbol,
        "market": market,
        "interval": interval,
        "candles": candles,
        "source": "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        "tr_id": "FHKST03010200",
    })


@app.get("/stream")
async def stream(
    request: Request,
    symbol: str = Query(..., min_length=1),
    market: str = Query("krx", pattern="^(krx|nxt|total)$"),
) -> StreamingResponse:
    client = KISProgramTradeClient(settings)

    async def event_generator():
        disconnect_task = None

        async def watch_disconnect() -> None:
            while not await request.is_disconnected():
                await asyncio.sleep(0.25)
            await client.aclose()

        try:
            disconnect_task = asyncio.create_task(watch_disconnect())
            async for event in client.subscribe_dashboard(symbol=symbol, market=market):
                if await request.is_disconnected():
                    break
                event_name = event["event"]
                frame = event["frame"]
                if frame.empty:
                    continue

                for _, row in frame.iterrows():
                    if await request.is_disconnected():
                        return
                    payload = to_native_dict(row.to_dict())
                    yield f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as exc:
            if not await request.is_disconnected():
                error_payload = {"error": str(exc)}
                yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        finally:
            if disconnect_task is not None:
                disconnect_task.cancel()
            await client.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
