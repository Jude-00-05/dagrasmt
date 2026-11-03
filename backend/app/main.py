import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from .analytics import build_series, metrics, compare_methodologies, DEFAULT_CUTOFF
from .data import load

app = FastAPI(title='WindLens API', version='1.1.0')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', '*').split(','), allow_methods=['*'], allow_headers=['*'])

def data(refresh=False):
    try: return load(refresh)
    except Exception as exc: raise HTTPException(503, f'Elexon dataset unavailable: {exc}') from exc

@app.get('/health')
def health(): return {'status': 'ok'}

@app.get('/api/overview')
def overview(
    refresh: bool = False,
    granularity: str = Query('hourly', pattern=r'^(hourly|half-hourly)$')
):
    actuals, forecasts, status = data(refresh)
    series_selected, quality_selected = build_series(actuals, forecasts, granularity=granularity)
    metrics_selected = metrics(series_selected, granularity=granularity)
    comparison = compare_methodologies(actuals, forecasts)

    cutoff_label = f'{DEFAULT_CUTOFF.strftime("%H:%M")} GMT on D-1 (configurable conservative assumption)'
    source_notes = {
        'hourly': 'WINDFOR forecasts represent average MW over 1-hour delivery periods. Actual wind generation is aggregated from two 30-minute FUELHH observations ((HH1 + HH2) / 2) to evaluate matching delivery periods [T, T+1h). Incomplete periods are reported separately and excluded from error metrics.',
        'half-hourly': 'WINDFOR forecasts are hourly while FUELHH outturns are half-hourly. Under exact timestamp matching, all 744 :30 intervals have no matching forecast and are excluded from accuracy metrics.'
    }

    return {
        'granularity': granularity,
        'metrics': metrics_selected,
        'quality': quality_selected,
        'comparison': comparison,
        'cutoffUtc': f'2025-12-31T{DEFAULT_CUTOFF.strftime("%H:%M")}:00Z',
        'cutoffLabel': cutoff_label,
        'sourceStatus': status,
        'sourceNote': source_notes[granularity]
    }

@app.get('/api/series')
def series(
    date: str = Query('2026-01-01', pattern=r'^2026-01-(0[1-9]|[12][0-9]|3[01])$'),
    granularity: str = Query('hourly', pattern=r'^(hourly|half-hourly)$')
):
    actuals, forecasts, status = data()
    values, quality = build_series(actuals, forecasts, granularity=granularity)
    return {
        'date': date,
        'granularity': granularity,
        'cutoff': f'{date} previous day {DEFAULT_CUTOFF.strftime("%H:%M")} GMT',
        'sourceStatus': status,
        'quality': quality,
        'series': [x for x in values if x['startTime'].startswith(date)]
    }

@app.get('/api/interval')
def interval(
    startTime: datetime,
    granularity: str = Query('hourly', pattern=r'^(hourly|half-hourly)$')
):
    actuals, forecasts, status = data()
    values, _ = build_series(actuals, forecasts, granularity=granularity)
    key = startTime.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    match = next((x for x in values if x['startTime'] == key), None)
    if not match:
        raise HTTPException(404, 'Delivery interval not found')
    return {'granularity': granularity, 'sourceStatus': status, 'interval': match}

@app.get('/api/compare')
def compare():
    actuals, forecasts, _ = data()
    return compare_methodologies(actuals, forecasts)
