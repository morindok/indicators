# Order Flow System

> Dash-based order-flow analysis dashboard (CVD, footprint) for the Bybit market.

## How to Use

- Run `pip install -r requirements.txt`
- Run `python app.py` and open `http://127.0.0.1:8050`

## Notes

- `app.py`: Dash user interface.
- `bybit_engine.py`: REST klines, ticker and WebSocket data.
- `signals_engine.py`: signal detection with SL/TP, stored in SQLite.

## Disclaimer

Educational purposes only. This is not financial advice.
