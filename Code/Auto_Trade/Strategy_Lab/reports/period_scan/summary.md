# MGC 5m MSS/BOS 61.8 Period Scan

- Full data range: 2025-06-09 06:00:00 to 2026-06-02 02:00:00 Beijing time
- Full actual span: 357.8 days
- Full bars: 37695
- Data source: Databento GLBX.MDP3 MGC.c.0 continuous futures, ohlcv-1m aggregated to 5m.
- Break mode: Loose
- Contract assumption: MGC $10/point, qty 1

| Requested Days | Actual Days | Trades | Win Rate | Net PnL | Profit Factor | Max DD | Winning Days | Losing Days |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 28.8 | 347 | 41.21% | $552.01 | 1.06 | $-841.58 | 13 | 9 |
| 60 | 59.9 | 407 | 43.73% | $1402.16 | 1.14 | $-841.58 | 16 | 11 |
| 90 | 90.0 | 720 | 46.67% | $9335.60 | 1.47 | $-841.58 | 38 | 13 |
| 120 | 119.8 | 780 | 47.31% | $10795.71 | 1.49 | $-841.58 | 41 | 18 |
| 150 | 150.0 | 1116 | 45.70% | $10985.90 | 1.35 | $-1480.59 | 51 | 32 |
| 180 | 179.9 | 1164 | 45.79% | $11695.87 | 1.36 | $-1480.59 | 54 | 33 |
| 210 | 210.0 | 1468 | 45.16% | $12971.93 | 1.33 | $-1480.59 | 68 | 42 |
| 240 | 238.8 | 1515 | 45.41% | $13889.05 | 1.35 | $-1480.59 | 70 | 44 |
| 270 | 270.0 | 1825 | 43.95% | $13941.02 | 1.32 | $-1480.59 | 82 | 54 |
| 300 | 300.0 | 1935 | 43.62% | $13837.33 | 1.31 | $-1480.59 | 84 | 59 |
| 330 | 329.8 | 2243 | 43.47% | $14368.72 | 1.30 | $-1480.59 | 99 | 67 |
| 360 | 357.8 | 2345 | 43.45% | $14820.32 | 1.30 | $-1480.59 | 105 | 70 |

Each period has its own `report.md`, `trades.csv`, `signals.csv`, `skipped.csv`, and `daily_summary.csv` folder.
