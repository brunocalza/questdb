"""
Seeds the `trades` table on a local QuestDB instance via PG wire.

Canonical QuestDB time-series schema:
- designated TIMESTAMP column for time-based queries
- PARTITION BY DAY so each day's data lives in its own files
- SYMBOL columns for low-cardinality, dictionary-encoded categorical fields
- WAL mode for parallel ingest (default for partitioned tables in modern QuestDB)

Usage:
    pip install psycopg
    python scripts/seed_trades.py                   # default: 500_000 trades
    python scripts/seed_trades.py 2000000           # custom row count

Connection:
    postgresql://admin:quest@localhost:8812/qdb
"""

import random
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg

DSN = "postgresql://admin:quest@localhost:8812/qdb"

DDL = """
CREATE TABLE IF NOT EXISTS trades (
    symbol   SYMBOL CAPACITY 16 CACHE,
    side     SYMBOL CAPACITY 2  CACHE,
    price    DOUBLE,
    amount   DOUBLE,
    exchange SYMBOL CAPACITY 8  CACHE,
    ts       TIMESTAMP
) TIMESTAMP(ts) PARTITION BY DAY
"""

INSERT_SQL = """
INSERT INTO trades (symbol, side, price, amount, exchange, ts)
VALUES (%s, %s, %s, %s, %s, %s)
"""

# Symbol -> rough base price (USD)
SYMBOLS = {
    "BTC-USD":   45_000.0,
    "ETH-USD":    2_500.0,
    "SOL-USD":       100.0,
    "XRP-USD":         0.50,
    "ADA-USD":         0.45,
    "DOT-USD":         7.0,
    "DOGE-USD":        0.08,
    "AVAX-USD":       35.0,
    "MATIC-USD":       0.90,
    "LINK-USD":       15.0,
}
SYMBOL_NAMES = list(SYMBOLS.keys())

SIDES = ["BUY", "SELL"]
EXCHANGES = ["BINANCE", "COINBASE", "KRAKEN", "BITSTAMP"]

BATCH_SIZE = 10_000

# 5 days of trading starting Mon 2025-01-13 (crypto trades 24/7, so use full days)
START_TS = datetime(2025, 1, 13, 0, 0, 0, tzinfo=timezone.utc)
TIME_SPAN = timedelta(days=5)


def gen_row(i: int, total: int, time_span_us: int):
    # Timestamps spread uniformly across the time span, in ascending order.
    # Ascending ts keeps QuestDB's writer happy (no out-of-order O3 overhead).
    # Using (i - 1) keeps the FIRST row at offset 0 and the LAST row strictly
    # below time_span_us, so no row lands exactly on the day-N boundary and
    # creates an orphan single-row partition.
    ts_offset_us = ((i - 1) * time_span_us) // total
    ts = START_TS + timedelta(microseconds=ts_offset_us)

    symbol = random.choice(SYMBOL_NAMES)
    base_price = SYMBOLS[symbol]
    # ±5% gaussian-ish jitter around the base price
    price = round(base_price * (1.0 + random.uniform(-0.05, 0.05)), 6)

    # Larger amounts for cheaper tokens, smaller amounts for BTC/ETH
    if base_price > 100:
        amount = round(random.uniform(0.001, 5.0), 6)
    else:
        amount = round(random.uniform(10.0, 5000.0), 2)

    side = random.choice(SIDES)
    exchange = random.choice(EXCHANGES)

    return (symbol, side, price, amount, exchange, ts)


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 500_000
    time_span_us = int(TIME_SPAN.total_seconds() * 1_000_000)

    print(f"Connecting to {DSN}")
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            print("Creating table if not exists...")
            cur.execute(DDL)

            print(f"Inserting {total:,} trades spread over {TIME_SPAN.days} days "
                  f"(~{total // TIME_SPAN.days:,} per day) "
                  f"in batches of {BATCH_SIZE:,}...")
            start = time.perf_counter()
            batch = []
            for i in range(1, total + 1):
                batch.append(gen_row(i, total, time_span_us))
                if len(batch) >= BATCH_SIZE:
                    cur.executemany(INSERT_SQL, batch)
                    batch.clear()
                    elapsed = time.perf_counter() - start
                    rate = i / elapsed if elapsed > 0 else 0
                    print(f"  inserted {i:>9,} / {total:,}  ({rate:,.0f} rows/s)")

            if batch:
                cur.executemany(INSERT_SQL, batch)

            elapsed = time.perf_counter() - start
            print(f"Done. {total:,} trades in {elapsed:.1f}s "
                  f"({total/elapsed:,.0f} rows/s)")

            # Give WAL-apply a brief moment to flush before sanity checks.
            print("\nWaiting 2s for WAL apply...")
            time.sleep(2)

            print("\nSanity check:")
            cur.execute("SELECT count() FROM trades")
            print(f"  row count:        {cur.fetchone()[0]:>12,}")
            cur.execute("SELECT count_distinct(symbol) FROM trades")
            print(f"  distinct symbols: {cur.fetchone()[0]:>12,}")
            cur.execute("SELECT min(ts), max(ts) FROM trades")
            mn, mx = cur.fetchone()
            print(f"  ts range:         {mn}  ->  {mx}")

            print("\nTotal notional volume (price * amount) per symbol:")
            cur.execute("""
                SELECT symbol, ROUND(SUM(amount * price), 2) AS volume_usd
                FROM trades
                GROUP BY symbol
                ORDER BY volume_usd DESC
            """)
            for sym, vol in cur.fetchall():
                print(f"  {sym:>10}  ${vol:>16,.2f}")

            print("\nTrade count by day:")
            cur.execute("""
                SELECT ts, count
                FROM (
                    SELECT ts, count() AS count
                    FROM trades
                    SAMPLE BY 1d
                )
                ORDER BY ts
            """)
            for ts, n in cur.fetchall():
                print(f"  {ts}  {n:>9,}")


if __name__ == "__main__":
    main()
