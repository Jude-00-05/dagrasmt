from collections import defaultdict
import os
from datetime import datetime, timedelta, timezone, time
from math import sqrt

UTC = timezone.utc
_cutoff_parts = os.getenv('DECISION_CUTOFF_UTC', '09:20').split(':')
DEFAULT_CUTOFF = time(int(_cutoff_parts[0]), int(_cutoff_parts[1]))

def dt(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None: raise ValueError('timestamp must include timezone')
    return parsed.astimezone(UTC)

def cutoff(start, cutoff_time=DEFAULT_CUTOFF):
    return datetime.combine(dt(start).date() - timedelta(days=1), cutoff_time, tzinfo=UTC)

def number(value):
    try:
        value = float(value)
        return value if value == value and abs(value) != float('inf') else None
    except (TypeError, ValueError): return None

def actual_map(rows):
    grouped, invalid = defaultdict(list), 0
    for row in rows:
        if str(row.get('fuelType', '')).upper() != 'WIND': continue
        try: key = dt(row['startTime'])
        except (KeyError, ValueError): invalid += 1; continue
        value = number(row.get('generation'))
        if value is None: invalid += 1; continue
        grouped[key].append(value)
    return {key: values[-1] for key, values in grouped.items()}, sum(max(0, len(v)-1) for v in grouped.values()), invalid

def forecast_map(rows):
    grouped, seen, invalid, duplicates = defaultdict(list), set(), 0, 0
    for row in rows:
        try: start, publish = dt(row['startTime']), dt(row['publishTime'])
        except (KeyError, ValueError): invalid += 1; continue
        value = number(row.get('generation'))
        if value is None: invalid += 1; continue
        record = (start, publish, value)
        if record in seen:
            duplicates += 1
            continue
        seen.add(record)
        if publish <= cutoff(start): grouped[start].append((publish, value))
    selected = {key: sorted(values)[-1] for key, values in grouped.items()}
    return selected, duplicates, invalid

def aggregate_hourly_actuals(half_hourly_actuals):
    """
    Aggregates consecutive 30-minute FUELHH wind actual observations (MW)
    into 1-hour average MW observations matching 1-hour WINDFOR delivery periods [T, T+1h).

    Conditions:
    - Both 30-minute intervals [T, T+30m) and [T+30m, T+1h) must be present and valid numbers.
    - Missing half-hourly observations are never replaced with zero.
    - Incomplete hourly periods are omitted from hourly actuals and tracked in incomplete_periods.
    - Values are averaged ((HH1 + HH2) / 2) to preserve MW power dimensions (never summed as MWh).
    """
    hourly_actuals = {}
    incomplete_periods = {}
    hour_keys = {k.replace(minute=0, second=0, microsecond=0) for k in half_hourly_actuals}

    for h in sorted(hour_keys):
        h0 = h
        h1 = h + timedelta(minutes=30)
        v0 = half_hourly_actuals.get(h0)
        v1 = half_hourly_actuals.get(h1)

        if v0 is not None and v1 is not None:
            hourly_actuals[h] = round((v0 + v1) / 2.0, 4)
        else:
            incomplete_periods[h] = {
                'startTime': h.isoformat().replace('+00:00', 'Z'),
                'has_hh0': v0 is not None,
                'has_hh1': v1 is not None,
                'hh0_mw': v0,
                'hh1_mw': v1
            }

    return hourly_actuals, incomplete_periods

def build_series(actual_rows, forecast_rows, granularity='hourly'):
    """
    Builds aligned evaluation series and data quality metrics.
    granularity='hourly': aggregates FUELHH half-hours into hourly average MW matching WINDFOR.
    granularity='half-hourly': retains raw 30-minute FUELHH observations with exact timestamp matching.
    """
    raw_actuals, adups, ainvalid = actual_map(actual_rows)
    forecasts, fdups, finvalid = forecast_map(forecast_rows)

    if granularity == 'hourly':
        actuals, incomplete = aggregate_hourly_actuals(raw_actuals)
    elif granularity == 'half-hourly':
        actuals, incomplete = raw_actuals, {}
    else:
        raise ValueError(f"Unsupported granularity: {granularity}. Expected 'hourly' or 'half-hourly'.")

    keys = sorted({k for k in actuals | forecasts if k.strftime('%Y-%m') == '2026-01'})
    output, matched = [], 0
    for key in keys:
        forecast = forecasts.get(key)
        actual = actuals.get(key)
        item = {
            'startTime': key.isoformat().replace('+00:00', 'Z'),
            'forecast': forecast[1] if forecast else None,
            'actual': actual,
            'publishTime': forecast[0].isoformat().replace('+00:00', 'Z') if forecast else None
        }
        item['error'] = round(item['forecast'] - actual, 4) if forecast and actual is not None else None
        item['absoluteError'] = abs(item['error']) if item['error'] is not None else None
        matched += item['error'] is not None
        output.append(item)

    quality = {
        'granularity': granularity,
        'actualRows': len(actuals),
        'rawActualObservations': len(raw_actuals),
        'forecastRows': len(forecasts),
        'matchedRows': matched,
        'missingForecast': sum(x['forecast'] is None for x in output),
        'missingActual': sum(x['actual'] is None for x in output),
        'incompleteActualPeriods': len(incomplete),
        'duplicateActuals': adups,
        'duplicateForecasts': fdups,
        'invalidRows': ainvalid + finvalid
    }
    return output, quality

def metrics(series, granularity='hourly'):
    errors = [x['error'] for x in series if x.get('error') is not None]
    return {
        'granularity': granularity,
        'count': len(errors),
        'mae': round(sum(abs(x) for x in errors)/len(errors), 2) if errors else None,
        'rmse': round(sqrt(sum(x*x for x in errors)/len(errors)), 2) if errors else None,
        'bias': round(sum(errors)/len(errors), 2) if errors else None,
        'forecastCoveragePct': round(sum(x.get('forecast') is not None for x in series)/len(series)*100, 1) if series else 0,
        'actualCoveragePct': round(sum(x.get('actual') is not None for x in series)/len(series)*100, 1) if series else 0
    }

def compare_methodologies(actual_rows, forecast_rows):
    """
    Computes both evaluation methodologies side-by-side for audit and comparison.
    """
    s_hourly, q_hourly = build_series(actual_rows, forecast_rows, granularity='hourly')
    m_hourly = metrics(s_hourly, granularity='hourly')

    s_hh, q_hh = build_series(actual_rows, forecast_rows, granularity='half-hourly')
    m_hh = metrics(s_hh, granularity='half-hourly')

    return {
        'hourly': {
            'granularity': 'hourly',
            'label': 'Hourly Delivery-Period Aggregation (Recommended)',
            'description': 'Aggregates consecutive 30-minute FUELHH observations into average MW matching 1-hour WINDFOR delivery periods [T, T+1h).',
            'metrics': m_hourly,
            'quality': q_hourly
        },
        'halfHourly': {
            'granularity': 'half-hourly',
            'label': 'Half-Hourly Exact Match (Legacy Baseline)',
            'description': 'Unaggregated 30-minute FUELHH actuals matched only where WINDFOR shares identical interval start; leaves :30 intervals unmatched.',
            'metrics': m_hh,
            'quality': q_hh
        }
    }
