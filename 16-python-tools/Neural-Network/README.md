# Neural Network Predictor

> Dash dashboard with continual-learning LSTM price prediction (PyTorch).

## How to Use

- Run `pip install -r requirements.txt`
- Run `python app.py` and open `http://127.0.0.1:8050`

## Notes

- `config.py`: central configuration.
- `data_feed.py`: data fetching with retry/backoff.
- `features.py`: feature engineering.
- `neural_net.py`: LSTM model with walk-forward validation.
- `path_simulator.py`: block-bootstrap Monte Carlo simulation.
- `engine.py`: signal generation and risk engine.
- `app.py`: Dash user interface.

## Disclaimer

Educational purposes only. This is not financial advice.
