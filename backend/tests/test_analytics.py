from datetime import datetime, timezone
import math
from app.analytics import (
    aggregate_hourly_actuals,
    build_series,
    compare_methodologies,
    forecast_map,
    actual_map,
    metrics,
    dt,
    cutoff,
)

def test_aggregate_hourly_actuals_complete_pairs():
    """Verify that two 30-minute intervals (3000 MW and 3200 MW) aggregate to 3100 MW average power."""
    t0 = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    raw = {t0: 3000.0, t1: 3200.0}
    hourly, incomplete = aggregate_hourly_actuals(raw)
    assert len(hourly) == 1
    assert hourly[t0] == 3100.0
    assert len(incomplete) == 0

def test_aggregate_hourly_never_sums_mw():
    """Verify MW values are averaged, not summed into MWh."""
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    raw = {t0: 5000.0, t1: 5000.0}
    hourly, _ = aggregate_hourly_actuals(raw)
    assert hourly[t0] == 5000.0
    assert hourly[t0] != 10000.0

def test_aggregate_hourly_missing_half_hour_is_omitted():
    """Incomplete hours must not be imputed with 0 and must be excluded from hourly actuals."""
    t0 = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    raw = {t0: 3000.0}  # 14:30 is missing
    hourly, incomplete = aggregate_hourly_actuals(raw)
    assert t0 not in hourly
    assert t0 in incomplete
    assert incomplete[t0]['has_hh0'] is True
    assert incomplete[t0]['has_hh1'] is False

def test_latest_eligible_vintage_only():
    """Select the latest forecast vintage published before the D-1 decision cutoff."""
    rows = [
        {'startTime': '2026-01-02T00:00:00Z', 'publishTime': '2026-01-01T08:30:00Z', 'generation': 100},
        {'startTime': '2026-01-02T00:00:00Z', 'publishTime': '2026-01-01T09:20:00Z', 'generation': 110},
        {'startTime': '2026-01-02T00:00:00Z', 'publishTime': '2026-01-01T10:00:00Z', 'generation': 999},  # post-cutoff
    ]
    chosen, _, _ = forecast_map(rows)
    assert chosen[datetime(2026, 1, 2, tzinfo=timezone.utc)][1] == 110

def test_post_cutoff_rejection():
    """Forecasts published strictly after cutoff are not selected."""
    rows = [
        {'startTime': '2026-01-02T00:00:00Z', 'publishTime': '2026-01-01T09:25:00Z', 'generation': 500}
    ]
    chosen, _, _ = forecast_map(rows)
    assert datetime(2026, 1, 2, tzinfo=timezone.utc) not in chosen

def test_zero_is_valid_actual_and_forecast():
    """Zero generation is physically valid and must not be treated as missing or invalid."""
    actual = [
        {'startTime': '2026-01-01T00:00:00Z', 'fuelType': 'WIND', 'generation': 0},
        {'startTime': '2026-01-01T00:30:00Z', 'fuelType': 'WIND', 'generation': 0},
    ]
    forecast = [
        {'startTime': '2026-01-01T00:00:00Z', 'publishTime': '2025-12-31T08:30:00Z', 'generation': 0}
    ]
    series, quality = build_series(actual, forecast, granularity='hourly')
    assert quality['matchedRows'] == 1
    assert series[0]['actual'] == 0.0
    assert series[0]['forecast'] == 0.0
    assert series[0]['error'] == 0.0
    m = metrics(series, granularity='hourly')
    assert m['mae'] == 0.0
    assert m['rmse'] == 0.0
    assert m['bias'] == 0.0

def test_prior_vintages_are_not_duplicate_records():
    """Different vintages for the same delivery interval are valid revisions, not duplicates."""
    rows = [
        {'startTime': '2026-01-02T00:00:00Z', 'publishTime': '2026-01-01T07:30:00Z', 'generation': 100},
        {'startTime': '2026-01-02T00:00:00Z', 'publishTime': '2026-01-01T08:30:00Z', 'generation': 110},
        {'startTime': '2026-01-02T00:00:00Z', 'publishTime': '2026-01-01T08:30:00Z', 'generation': 110},  # exact duplicate
    ]
    _, duplicates, _ = forecast_map(rows)
    assert duplicates == 1

def test_timezone_required():
    """Timestamps without timezone information must be rejected as invalid."""
    chosen, _, invalid = forecast_map([
        {'startTime': '2026-01-01T00:00:00', 'publishTime': '2025-12-31T08:30:00Z', 'generation': 10}
    ])
    assert not chosen and invalid == 1

def test_independent_metric_calculation():
    """Verify statistical metrics against independently calculated values."""
    series = [
        {'error': 10.0},
        {'error': -20.0},
        {'error': 30.0},
        {'error': None},  # unpopulated
    ]
    # Errors: [10, -20, 30]
    # Abs errors: [10, 20, 30] -> sum = 60, mean = 20.0
    # Sq errors: [100, 400, 900] -> sum = 1400, mean = 466.666..., sqrt = 21.6024... -> 21.60
    # Bias: (10 + -20 + 30) / 3 = 20 / 3 = 6.666... -> 6.67
    m = metrics(series, granularity='hourly')
    assert m['count'] == 3
    assert m['mae'] == 20.0
    assert m['rmse'] == round(math.sqrt(1400 / 3), 2)
    assert m['bias'] == round(20 / 3, 2)

def test_granularity_toggle_and_coverage():
    """Verify that hourly aggregation resolves the 50% coverage artifact of half-hourly matching."""
    actuals = [
        {'startTime': '2026-01-01T00:00:00Z', 'fuelType': 'WIND', 'generation': 2000},
        {'startTime': '2026-01-01T00:30:00Z', 'fuelType': 'WIND', 'generation': 2200},
    ]
    forecasts = [
        {'startTime': '2026-01-01T00:00:00Z', 'publishTime': '2025-12-31T08:30:00Z', 'generation': 2100}
    ]

    # Hourly: 1 matched interval out of 1 hourly period (100% coverage, 0 error)
    s_h, q_h = build_series(actuals, forecasts, granularity='hourly')
    assert q_h['matchedRows'] == 1
    assert q_h['missingForecast'] == 0
    assert s_h[0]['actual'] == 2100.0
    assert s_h[0]['error'] == 0.0

    # Half-hourly: 1 matched, 1 missing forecast (:30 interval), coverage = 50%
    s_hh, q_hh = build_series(actuals, forecasts, granularity='half-hourly')
    assert q_hh['matchedRows'] == 1
    assert q_hh['missingForecast'] == 1
    m_hh = metrics(s_hh, granularity='half-hourly')
    assert m_hh['forecastCoveragePct'] == 50.0

def test_compare_methodologies_structure():
    """Verify compare_methodologies returns both hourly and half-hourly evaluations."""
    actuals = [
        {'startTime': '2026-01-01T00:00:00Z', 'fuelType': 'WIND', 'generation': 1000},
        {'startTime': '2026-01-01T00:30:00Z', 'fuelType': 'WIND', 'generation': 1100},
    ]
    forecasts = [
        {'startTime': '2026-01-01T00:00:00Z', 'publishTime': '2025-12-31T08:30:00Z', 'generation': 1050}
    ]
    comp = compare_methodologies(actuals, forecasts)
    assert 'hourly' in comp and 'halfHourly' in comp
    assert comp['hourly']['metrics']['mae'] == 0.0
    assert comp['halfHourly']['metrics']['mae'] == 50.0
