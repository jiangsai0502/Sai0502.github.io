# Strategy Lab

This folder is for testing the MGC 5m MSS/BOS 61.8 strategy before using the Chrome extension.

Workflow:

1. Fetch recent TradingView MGC 5m OHLCV data.
2. Replay the current Pine strategy logic in Python.
3. Save every signal, filled trade, skipped trade, and summary report.

Run:

```bash
/opt/anaconda3/envs/py3.10/bin/python Strategy_Lab/fetch_mgc_30d.py
/opt/anaconda3/envs/py3.10/bin/python Strategy_Lab/backtest_mss_618.py
```

Outputs are written to `Strategy_Lab/data/` and `Strategy_Lab/reports/`.
