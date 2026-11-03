import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import './styles.css';

type Point = {
  startTime: string;
  forecast: number | null;
  actual: number | null;
  publishTime: string | null;
  error: number | null;
};

type MetricSummary = {
  granularity: string;
  count: number;
  mae: number | null;
  rmse: number | null;
  bias: number | null;
  forecastCoveragePct: number;
  actualCoveragePct: number;
};

type QualitySummary = {
  granularity: string;
  actualRows: number;
  rawActualObservations: number;
  forecastRows: number;
  matchedRows: number;
  missingForecast: number;
  missingActual: number;
  incompleteActualPeriods: number;
  duplicateActuals: number;
  duplicateForecasts: number;
  invalidRows: number;
};

type ComparisonItem = {
  granularity: string;
  label: string;
  description: string;
  metrics: MetricSummary;
  quality: QualitySummary;
};

type Overview = {
  granularity: string;
  metrics: MetricSummary;
  quality: QualitySummary;
  comparison: {
    hourly: ComparisonItem;
    halfHourly: ComparisonItem;
  };
  sourceStatus: string;
  sourceNote: string;
  cutoffLabel: string;
};

type SeriesResponse = {
  series: Point[];
  granularity: string;
};

const API = import.meta.env.VITE_API_BASE_URL !== undefined
  ? import.meta.env.VITE_API_BASE_URL
  : (import.meta.env.DEV ? 'http://localhost:8000' : '');
const mw = (value: number | null) => (value == null ? '—' : `${value.toLocaleString()} MW`);

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (response.ok) return response.json() as Promise<T>;
  const body = await response.json().catch(() => ({}));
  throw new Error(body.detail || `Request failed (${response.status})`);
}

function Chart({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="panel chart">
      <label>TIME SERIES</label>
      <h2>{title}</h2>
      <div>{children}</div>
    </article>
  );
}

function formatDeliveryInterval(isoString: string, granularity: string): string {
  const start = new Date(isoString);
  const end = new Date(start.getTime() + (granularity === 'hourly' ? 60 : 30) * 60 * 1000);
  const fmt = (d: Date) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `${fmt(start)}–${fmt(end)}`;
}

function App() {
  const [granularity, setGranularity] = useState<'hourly' | 'half-hourly'>('hourly');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [day, setDay] = useState('2026-01-01');
  const [points, setPoints] = useState<Point[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchJson<Overview>(`/api/overview?granularity=${granularity}`)
      .then(setOverview)
      .catch(e => setError(e.message));
  }, [granularity]);

  useEffect(() => {
    fetchJson<SeriesResponse>(`/api/series?date=${day}&granularity=${granularity}`)
      .then(result => setPoints(result.series))
      .catch(e => setError(e.message));
  }, [day, granularity]);

  const chart = useMemo(
    () =>
      points.map(point => ({
        ...point,
        time: new Date(point.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        errorValue: point.error
      })),
    [points]
  );

  if (error) {
    return (
      <main className="shell">
        <div className="message">
          <h2>Data connection unavailable</h2>
          <p>{error}</p>
          <p>Start FastAPI and reload.</p>
        </div>
      </main>
    );
  }

  if (!overview) {
    return (
      <main className="shell">
        <div className="message">Loading January 2026 analysis…</div>
      </main>
    );
  }

  const { metrics, quality, comparison } = overview;
  const cutoffTime = overview.cutoffLabel.split(' GMT')[0];

  return (
    <main className="shell">
      <header>
        <div className="brand">
          <b>W</b>
          <div>
            <strong>WindLens</strong>
            <small>Procurement intelligence</small>
          </div>
        </div>
        <span className="status">
          ● {overview.sourceStatus === 'cached' ? 'Cached source data' : 'Elexon source data'}
        </span>
      </header>

      <section className="hero">
        <div>
          <label>GB NATIONAL WIND · JANUARY 2026</label>
          <h1>Forecast confidence for the day-ahead desk.</h1>
          <p>
            A decision-time view of wind forecast error, built from historical Elexon BMRS vintages before each delivery
            day.
          </p>

          <div className="granularity-controls">
            <span className="granularity-label">Evaluation Methodology:</span>
            <div className="granularity-toggle">
              <button
                type="button"
                className={`granularity-btn ${granularity === 'hourly' ? 'active' : ''}`}
                onClick={() => setGranularity('hourly')}
              >
                Hourly Delivery-Period Aggregation (Recommended)
              </button>
              <button
                type="button"
                className={`granularity-btn ${granularity === 'half-hourly' ? 'active' : ''}`}
                onClick={() => setGranularity('half-hourly')}
              >
                Half-Hourly Exact Match (Legacy Baseline)
              </button>
            </div>
          </div>
        </div>

        <div className="cutoff">
          <small>ANALYTICAL CUTOFF</small>
          <strong>{cutoffTime} GMT</strong>
          <span>Previous day · configurable conservative assumption</span>
        </div>
      </section>

      <section className="metrics">
        {[
          ['MAE', mw(metrics.mae), `Average absolute error (${granularity})`],
          ['RMSE', mw(metrics.rmse), `Penalises larger misses (${granularity})`],
          ['BIAS', mw(metrics.bias), `Forecast − actual (${granularity})`],
          ['MATCHED', `${metrics.count} intervals`, `${metrics.forecastCoveragePct}% forecast coverage`]
        ].map(item => (
          <article key={item[0]}>
            <label>
              {item[0]}
              <span className="badge">{granularity === 'hourly' ? '1-HOUR' : '30-MIN'}</span>
            </label>
            <strong>{item[1]}</strong>
            <small>{item[2]}</small>
          </article>
        ))}
      </section>

      <section className="grid">
        <Chart title={`Forecast versus actual (${granularity})`}>
          <ResponsiveContainer>
            <LineChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis unit=" MW" />
              <Tooltip />
              <Line dataKey="forecast" name="Forecast" stroke="#1c9a9a" dot={false} />
              <Line dataKey="actual" name="Actual" stroke="#1e3048" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Chart>
        <Chart title={`Interval forecast error (${granularity})`}>
          <ResponsiveContainer>
            <BarChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis unit=" MW" />
              <Tooltip />
              <Bar dataKey="errorValue" name="Forecast − actual" fill="#e1a34d" />
            </BarChart>
          </ResponsiveContainer>
        </Chart>
      </section>

      <section className="grid lower">
        <article className="panel">
          <div className="panel-head">
            <div>
              <label>INTERVAL EXPLORER ({granularity.toUpperCase()})</label>
              <h2>{day}</h2>
            </div>
            <input
              type="date"
              min="2026-01-01"
              max="2026-01-31"
              value={day}
              onChange={event => setDay(event.target.value)}
            />
          </div>
          <div className="table">
            <table>
              <thead>
                <tr>
                  <th>Delivery Interval (UTC)</th>
                  <th>Forecast</th>
                  <th>Actual</th>
                  <th>Error</th>
                  <th>Published Vintage</th>
                </tr>
              </thead>
              <tbody>
                {points.slice(0, 12).map(point => (
                  <tr key={point.startTime}>
                    <td>{formatDeliveryInterval(point.startTime, granularity)}</td>
                    <td>{mw(point.forecast)}</td>
                    <td>{mw(point.actual)}</td>
                    <td>{mw(point.error)}</td>
                    <td>
                      {point.publishTime
                        ? new Date(point.publishTime).toLocaleString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                          })
                        : 'Missing'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <aside className="panel quality">
          <label>DATA QUALITY AUDIT</label>
          <h2>Coverage you can audit</h2>
          {[
            ['Evaluation granularity', granularity === 'hourly' ? 'Hourly delivery periods' : 'Half-hourly exact match'],
            ['Matched intervals', quality.matchedRows],
            ['Forecast coverage', `${metrics.forecastCoveragePct}%`],
            ['Raw FUELHH actuals', quality.rawActualObservations],
            ['Incomplete actual periods', quality.incompleteActualPeriods],
            ['Missing forecast intervals', quality.missingForecast],
            ['Duplicate records', quality.duplicateActuals + quality.duplicateForecasts],
            ['Invalid rows', quality.invalidRows]
          ].map(item => (
            <div className="qrow" key={item[0]}>
              <span>{item[0]}</span>
              <b>{item[1]}</b>
            </div>
          ))}
          <p>{overview.sourceNote}</p>
        </aside>
      </section>

      {comparison && (
        <section className="comparison-card">
          <label>METHODOLOGY AUDIT & BENCHMARK</label>
          <h2>Granularity comparison (January 2026 outturns)</h2>
          <div className="table">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Methodology</th>
                  <th>Actual Observations</th>
                  <th>Forecast Observations</th>
                  <th>Matched Intervals</th>
                  <th>Missing Forecasts</th>
                  <th>Coverage</th>
                  <th>MAE</th>
                  <th>RMSE</th>
                  <th>Mean Bias</th>
                </tr>
              </thead>
              <tbody>
                <tr className={granularity === 'hourly' ? 'active-method' : ''}>
                  <td>
                    <strong>Hourly Delivery Aggregation</strong>
                    <br />
                    <small>Averages two 30-min actuals ((HH1 + HH2)/2) to match 1h forecast</small>
                  </td>
                  <td>{comparison.hourly.quality.actualRows} (from {comparison.hourly.quality.rawActualObservations} raw)</td>
                  <td>{comparison.hourly.quality.forecastRows}</td>
                  <td className="highlight">{comparison.hourly.quality.matchedRows}</td>
                  <td>{comparison.hourly.quality.missingForecast}</td>
                  <td className="highlight">{comparison.hourly.metrics.forecastCoveragePct}%</td>
                  <td>{mw(comparison.hourly.metrics.mae)}</td>
                  <td>{mw(comparison.hourly.metrics.rmse)}</td>
                  <td>{mw(comparison.hourly.metrics.bias)}</td>
                </tr>
                <tr className={granularity === 'half-hourly' ? 'active-method' : ''}>
                  <td>
                    <strong>Half-Hourly Exact Match (Legacy)</strong>
                    <br />
                    <small>Exact timestamp match; misses all :30 intervals due to 1h forecast</small>
                  </td>
                  <td>{comparison.halfHourly.quality.actualRows}</td>
                  <td>{comparison.halfHourly.quality.forecastRows}</td>
                  <td>{comparison.halfHourly.quality.matchedRows}</td>
                  <td>{comparison.halfHourly.quality.missingForecast}</td>
                  <td>{comparison.halfHourly.metrics.forecastCoveragePct}%</td>
                  <td>{mw(comparison.halfHourly.metrics.mae)}</td>
                  <td>{mw(comparison.halfHourly.metrics.rmse)}</td>
                  <td>{mw(comparison.halfHourly.metrics.bias)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="method">
        <div>
          <label>METHODOLOGY</label>
          <h2>Decision-time, not hindsight.</h2>
        </div>
        <div>
          <p>
            For every delivery interval, WindLens isolates the latest WINDFOR record whose <code>publishTime</code> is
            on or before {overview.cutoffLabel}. It maps that forecast to FUELHH WIND actual generation.
          </p>
          <p style={{ marginTop: '12px' }}>
            <strong>Why delivery-period aggregation is justified:</strong> Elexon BMRS documentation confirms that
            WINDFOR publishes national forecasts as average MW over 1-hour delivery periods [T, T+1h), whereas FUELHH
            records average MW over 30-minute settlement intervals [T, T+30m) and [T+30m, T+1h). Averaging the two
            half-hourly actuals ((HH1 + HH2) / 2) accurately reflects the physical delivery period, preserving MW power
            dimensions and raising genuine forecast coverage from 50% to 100% without imputing missing values or
            introducing look-ahead bias.
          </p>
          <p style={{ marginTop: '12px' }}>
            The cutoff is a configurable analytical assumption informed by GB day-ahead auction timings, not a
            universal procurement deadline. These metrics quantify wind uncertainty only—they do not estimate total
            procurement requirements without demand and portfolio data.
          </p>
        </div>
      </section>

      <footer>
        WindLens · Elexon BMRS FUELHH + WINDFOR · <a href={`${API}/docs`}>API docs</a>
      </footer>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
