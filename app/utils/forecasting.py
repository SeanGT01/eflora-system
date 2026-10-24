"""Pure-Python time-series forecasting for seller analytics (no numpy/statsmodels)."""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

MethodName = str

_ALPHA_GRID = (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4)
_BETA_GRID = (0.05, 0.1, 0.15, 0.2, 0.25)
_GAMMA_GRID = (0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45)


def _clamp_nonneg(values: Sequence[float]) -> List[float]:
    return [round(max(0.0, float(v)), 2) for v in values]


def _mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    n = min(len(actual), len(predicted))
    if n == 0:
        return 0.0
    return sum(abs(float(actual[i]) - float(predicted[i])) for i in range(n)) / n


def _rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    n = min(len(actual), len(predicted))
    if n == 0:
        return 0.0
    return math.sqrt(sum((float(actual[i]) - float(predicted[i])) ** 2 for i in range(n)) / n)


def _mape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    n = min(len(actual), len(predicted))
    if n == 0:
        return 0.0
    errs = []
    for i in range(n):
        a = float(actual[i])
        if abs(a) < 1e-9:
            continue
        errs.append(abs(a - float(predicted[i])) / abs(a))
    if not errs:
        return 0.0
    return sum(errs) / len(errs) * 100.0


def _bounds(forecast: Sequence[float], rmse: float) -> Tuple[List[float], List[float]]:
    band = 1.96 * rmse
    lower = _clamp_nonneg([v - band for v in forecast])
    upper = _clamp_nonneg([v + band for v in forecast])
    return lower, upper


def _empty_result(horizon: int = 7) -> dict:
    zeros = [0.0] * horizon
    return {
        'method': 'simple_exponential',
        'forecast': zeros,
        'lower_bound': zeros,
        'upper_bound': zeros,
        'metrics': {'mae': 0.0, 'rmse': 0.0, 'mape': 0.0},
        'confidence_level': 0.95,
        'is_insufficient_data': True,
    }


def _simple_exponential(
    y: List[float],
    horizon: int,
    alpha: float = 0.3,
) -> dict:
    level = y[0]
    fitted: List[float] = []
    for val in y:
        fitted.append(level)
        level = alpha * val + (1.0 - alpha) * level
    forecast = _clamp_nonneg([level] * horizon)
    rmse = _rmse(y, fitted)
    lower, upper = _bounds(forecast, rmse)
    return {
        'method': 'simple_exponential',
        'forecast': forecast,
        'lower_bound': lower,
        'upper_bound': upper,
        'metrics': {
            'mae': round(_mae(y, fitted), 2),
            'rmse': round(rmse, 2),
            'mape': round(_mape(y, fitted), 2),
        },
        'confidence_level': 0.95,
        'is_insufficient_data': True,
    }


def _holt_linear(
    y: List[float],
    horizon: int,
    alpha: float = 0.3,
    beta: float = 0.1,
) -> dict:
    if len(y) == 1:
        return _simple_exponential(y, horizon, alpha=alpha)

    level = y[0]
    trend = y[1] - y[0]
    fitted: List[float] = []
    for val in y:
        fitted.append(level + trend)
        prev_level = level
        level = alpha * val + (1.0 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * trend
    forecast = _clamp_nonneg([level + h * trend for h in range(1, horizon + 1)])
    rmse = _rmse(y, fitted)
    lower, upper = _bounds(forecast, rmse)
    return {
        'method': 'holt_linear',
        'forecast': forecast,
        'lower_bound': lower,
        'upper_bound': upper,
        'metrics': {
            'mae': round(_mae(y, fitted), 2),
            'rmse': round(rmse, 2),
            'mape': round(_mape(y, fitted), 2),
        },
        'confidence_level': 0.95,
        'is_insufficient_data': False,
    }


def _init_additive_seasonal(y: List[float], seasonal_period: int) -> Tuple[float, float, List[float]]:
    l0 = sum(y[:seasonal_period]) / seasonal_period
    b0 = sum(y[i + seasonal_period] - y[i] for i in range(seasonal_period)) / (seasonal_period ** 2)
    season = [y[i] - l0 for i in range(seasonal_period)]
    adj = sum(season) / seasonal_period
    season = [s - adj for s in season]
    return l0, b0, season


def _fit_holt_winters(
    y: List[float],
    seasonal_period: int,
    alpha: float,
    beta: float,
    gamma: float,
) -> Tuple[float, float, List[float], List[float]]:
    n = len(y)
    l0, b0, season = _init_additive_seasonal(y, seasonal_period)
    level = l0
    trend = b0
    fitted: List[float] = []

    for t in range(n):
        s_idx = t % seasonal_period
        if t < seasonal_period:
            fitted.append(max(0.0, level + trend + season[s_idx]))
            continue
        s_old = season[s_idx]
        prev_level = level
        level = alpha * (y[t] - s_old) + (1.0 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * trend
        season[s_idx] = gamma * (y[t] - level) + (1.0 - gamma) * s_old
        fitted.append(max(0.0, level + trend + season[s_idx]))

    return level, trend, season, fitted


def _forecast_holt_winters(
    level: float,
    trend: float,
    season: List[float],
    seasonal_period: int,
    start_index: int,
    horizon: int,
) -> List[float]:
    out: List[float] = []
    for h in range(1, horizon + 1):
        s_idx = (start_index + h - 1) % seasonal_period
        out.append(max(0.0, level + h * trend + season[s_idx]))
    return out


def _tune_holt_winters(y: List[float], seasonal_period: int) -> Tuple[float, float, float]:
    best = (0.25, 0.15, 0.35)
    best_mse = float('inf')
    for alpha in _ALPHA_GRID:
        for beta in _BETA_GRID:
            for gamma in _GAMMA_GRID:
                _, _, _, fitted = _fit_holt_winters(y, seasonal_period, alpha, beta, gamma)
                if len(fitted) < seasonal_period:
                    continue
                tail = y[seasonal_period:]
                pred = fitted[seasonal_period:]
                mse = sum((float(a) - float(p)) ** 2 for a, p in zip(tail, pred)) / len(tail)
                if mse < best_mse:
                    best_mse = mse
                    best = (alpha, beta, gamma)
    return best


def _holt_winters_additive(
    y: List[float],
    horizon: int,
    seasonal_period: int,
    alpha: Optional[float],
    beta: Optional[float],
    gamma: Optional[float],
) -> dict:
    if alpha is None or beta is None or gamma is None:
        alpha, beta, gamma = _tune_holt_winters(y, seasonal_period)
    level, trend, season, fitted = _fit_holt_winters(y, seasonal_period, alpha, beta, gamma)
    forecast = _clamp_nonneg(
        _forecast_holt_winters(level, trend, season, seasonal_period, len(y), horizon)
    )
    rmse = _rmse(y, fitted)
    lower, upper = _bounds(forecast, rmse)
    return {
        'method': 'holt_winters_additive',
        'forecast': forecast,
        'lower_bound': lower,
        'upper_bound': upper,
        'metrics': {
            'mae': round(_mae(y, fitted), 2),
            'rmse': round(rmse, 2),
            'mape': round(_mape(y, fitted), 2),
        },
        'confidence_level': 0.95,
        'is_insufficient_data': False,
        'params': {'alpha': alpha, 'beta': beta, 'gamma': gamma},
    }


def holt_winters_forecast(
    series: Sequence[float],
    seasonal_period: int = 7,
    horizon: int = 7,
    alpha: Optional[float] = 0.25,
    beta: Optional[float] = 0.15,
    gamma: Optional[float] = 0.35,
) -> dict:
    """Forecast the next ``horizon`` points with tiered Holt-Winters degradation."""
    y = [max(0.0, float(v)) for v in series]
    n = len(y)
    if n == 0:
        return _empty_result(horizon)
    if n < seasonal_period:
        return _simple_exponential(y, horizon)
    if n < seasonal_period * 2:
        return _holt_linear(y, horizon, alpha=alpha or 0.3, beta=beta or 0.15)
    return _holt_winters_additive(
        y,
        horizon,
        seasonal_period,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
    )
