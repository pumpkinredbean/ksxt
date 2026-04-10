import argparse
import asyncio
import pandas as pd

from src.config import settings
from src.kis_websocket import KISProgramTradeClient


VIEW_COLUMNS = [
    "종목코드",
    "체결시각",
    "프로그램매도체결량",
    "프로그램매수체결량",
    "프로그램순매수체결량",
    "프로그램순매수거래대금",
    "매도호가잔량",
    "매수호가잔량",
    "전체순매수호가잔량",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KIS realtime program trade watcher")
    parser.add_argument("--symbol", required=True, help="종목코드 예: 005930")
    parser.add_argument(
        "--market",
        default="krx",
        choices=["krx", "nxt", "total"],
        help="시장 선택",
    )
    return parser.parse_args()


def render(df: pd.DataFrame) -> None:
    if df.empty:
        return

    cols = [col for col in VIEW_COLUMNS if col in df.columns]
    print("\n" + "=" * 100)
    print(df[cols].tail(1).to_string(index=False))
    print("=" * 100)


async def run() -> None:
    args = parse_args()
    client = KISProgramTradeClient(settings)

    print(f"[INFO] symbol={args.symbol} market={args.market} ws={settings.ws_url}")

    async for frame in client.subscribe(symbol=args.symbol, market=args.market):
        render(frame)


if __name__ == "__main__":
    asyncio.run(run())
