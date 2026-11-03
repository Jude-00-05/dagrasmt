import json, os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import httpx

BASE = os.getenv('ELEXON_BASE_URL', 'https://data.elexon.co.uk/bmrs/api/v1').rstrip('/')

def _resolve_raw_dir() -> Path:
    env_dir = os.getenv('DATA_DIR')
    if env_dir:
        p = Path(env_dir)
        return p / 'raw' if (p / 'raw').is_dir() else p
    docker_raw = Path('/app/data/raw')
    if docker_raw.is_dir() and any(docker_raw.iterdir()):
        return docker_raw
    p = Path(__file__).resolve()
    for parent in p.parents:
        candidate = parent / 'data' / 'raw'
        if candidate.is_dir() and any(candidate.iterdir()):
            return candidate
    return p.parents[2] / 'data' / 'raw'

RAW = _resolve_raw_dir()

class Client:
    def __init__(self): self.client = httpx.Client(base_url=BASE, timeout=30)
    def get(self, path, params):
        response = self.client.get(path, params=params); response.raise_for_status(); return response.json()
    @staticmethod
    def rows(payload):
        return payload if isinstance(payload, list) else payload.get('data', [])
    def actuals(self):
        payload = self.get('/datasets/FUELHH/stream', {'settlementDateFrom':'2026-01-01','settlementDateTo':'2026-01-31'})
        return self.rows(payload)
    def publications(self):
        found = set()
        for i in range(31):
            day = date(2026,1,1) + timedelta(days=i)
            payload = self.get('/forecast/generation/wind/evolution', {'startTime':f'{day.isoformat()}T00:00:00Z'})
            for row in self.rows(payload): found.add(row['publishTime'])
        return sorted(found)
    def forecasts(self):
        rows=[]
        for publish in self.publications():
            payload=self.get('/forecast/generation/wind/history', {'publishTime':publish})
            rows.extend(self.rows(payload))
        return rows

def load(refresh=False):
    RAW.mkdir(parents=True, exist_ok=True)
    a_path, f_path = RAW/'fuelhh_january_2026.json', RAW/'windfor_january_2026.json'
    if not refresh and a_path.exists() and f_path.exists(): return json.loads(a_path.read_text()), json.loads(f_path.read_text()), 'cached'
    client=Client(); actuals, forecasts=client.actuals(), client.forecasts()
    a_path.write_text(json.dumps(actuals)); f_path.write_text(json.dumps(forecasts))
    return actuals, forecasts, 'live'

