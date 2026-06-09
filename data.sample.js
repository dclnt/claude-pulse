// SAMPLE DATA — for visual development only.
// Matches the NEW PULSE_DATA shape (LLM Overwatch pivot + composite report + status).
// The page shows "SAMPLE DATA" when this is active.
// The real data.js is written by fetch_overwatch.py from the live feed.

(function () {
  if (window.PULSE_DATA) return;  // real data.js already loaded

  // Rough ms range: ~10s (fast, off-peak) to ~42s (slow, peak)
  function hourAvgMs(hour) {
    // UTC hours: peak roughly 8-15 UTC (business hours NA/EU overlap)
    if (hour >= 8 && hour <= 15) return 40000 + (hour - 8) * 300;
    if (hour >= 0 && hour <= 2)  return 13500;
    return 16500 + Math.sin((hour / 24) * Math.PI) * 2000;
  }

  var hourly = [];
  for (var h = 0; h < 24; h++) {
    var avg = Math.round(hourAvgMs(h));
    hourly.push({
      hour: h,
      average_ms: avg,
      dataCount: 3000 + h * 200,
      isPeak: h >= 8 && h <= 10,
    });
  }

  var trend24h = [];
  for (var h = 0; h < 24; h++) {
    trend24h.push({
      hour: h,
      average_ms: h < 14 ? Math.round(hourAvgMs(h) * 1.6) : null,
      dataCount: h < 14 ? 80 + h * 5 : 0,
      dataType: h < 14 ? 'real' : 'historical',
    });
  }

  // 7 days: day 0 = today (partial), day 6 = 6 days ago
  var week = [];
  for (var d = 0; d < 7; d++) {
    var byHour = [];
    for (var h = 0; h < 24; h++) {
      byHour.push({
        hour: h,
        average_ms: d === 0 && h > 13 ? null : Math.round(hourAvgMs(h) * (1 + d * 0.05)),
        dataCount: d === 0 && h > 13 ? 0 : 100 + h * 3,
        dataType: d === 0 ? (h <= 13 ? 'real' : 'historical') : 'historical',
      });
    }
    week.push({
      dayIndex: d,
      average_ms: Math.round(22000 + d * 1000),
      byHourData: byHour,
    });
  }

  var models = [
    { name: 'anthropic-claude-3-7-sonnet-thinking', status: 'unknown',
      metrics: { last15MinAverage: 55000, allTimeAverage: 42000, performanceDiff: 13000, dataCount: 28, lastUpdated: new Date(Date.now() - 4 * 60 * 1000).toISOString() },
      byHourData: hourly.map(function(e) { return { hour: e.hour, average_ms: e.average_ms * 2, dataCount: 80 }; }) },
    { name: 'anthropic-claude-haiku-3.5', status: 'unknown',
      metrics: { last15MinAverage: 11000, allTimeAverage: 10500, performanceDiff: 500, dataCount: 120, lastUpdated: new Date(Date.now() - 4 * 60 * 1000).toISOString() },
      byHourData: hourly.map(function(e) { return { hour: e.hour, average_ms: Math.round(e.average_ms * 0.65), dataCount: 350 }; }) },
    { name: 'anthropic-claude-sonnet-4-5', status: 'unknown',
      metrics: { last15MinAverage: 26000, allTimeAverage: 17000, performanceDiff: 9000, dataCount: 65, lastUpdated: new Date(Date.now() - 4 * 60 * 1000).toISOString() },
      byHourData: hourly.map(function(e) { return { hour: e.hour, average_ms: e.average_ms, dataCount: 200 }; }) },
  ];

  // Sample: LATENCY_DIVERGENCE state — official says operational but latency is 57% above normal
  // Flip the comment blocks below to test other states (ALL_CLEAR, OFFICIAL_INCIDENT, DEGRADED_BOTH)

  var sampleReport = {
    model_scope: 'all',
    current_ms: 26100,
    baseline_ms: 16625,
    deviation_pct: 57.0,
    verdict: 'SLOW',
    confidence: {
      score: 0.85,
      level: 'HIGH',
      sample_count: 142,
      reason: 'good sample coverage',
    },
    inputs: {
      last15MinAverage: 26203,
      lastHourAverage: 25800,
      peakHourExpected: 40600,
      allTimeAverage: 16625,
    },
  };

  var sampleStatus = {
    fetch_ok: true,
    official: {
      indicator: 'none',
      description: 'All Systems Operational',
      last_updated: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
      components: [
        { name: 'API', status: 'operational' },
        { name: 'API Streaming Responses', status: 'operational' },
        { name: 'claude.ai', status: 'operational' },
        { name: 'Console', status: 'operational' },
        { name: 'Bedrock', status: 'operational' },
        { name: 'Vertex', status: 'operational' },
      ],
    },
    active_incidents: [],
    recent_incidents: [
      {
        id: 'abc123',
        name: 'Elevated API Error Rates',
        impact: 'major',
        started_at: new Date(Date.now() - 26 * 60 * 60 * 1000).toISOString(),
        resolved_at: new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString(),
        duration_min: 180,
        hours_ago: 23,
      },
      {
        id: 'def456',
        name: 'Increased Latency — claude.ai',
        impact: 'minor',
        started_at: new Date(Date.now() - 52 * 60 * 60 * 1000).toISOString(),
        resolved_at: new Date(Date.now() - 50 * 60 * 60 * 1000).toISOString(),
        duration_min: 95,
        hours_ago: 50,
      },
    ],
    reconciliation: {
      state: 'LATENCY_DIVERGENCE',
      message: 'Operational, but latency is 57% above normal',
      latency_deviation_pct: 57.0,
    },
  };

  window.PULSE_DATA = {
    _sample: true,
    source: 'LLM Overwatch',
    sourceUrl: 'https://llmoverwatch.com',
    fetchedAt: new Date().toISOString(),
    feedGeneratedAt: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    sourceTz: 'UTC',
    hourlyDialNote: 'peakHours hours 0-23 are UTC hour-of-day',
    verdict: {
      status: 'operational',
      last15MinAverage_ms: 26203,
      allTimeAverage_ms: 16625,
      performanceDiff_ms: 9578,
      lastUpdated: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    },
    report: sampleReport,
    status: sampleStatus,
    hourly: hourly,
    trend24h: trend24h,
    trend24hAverage_ms: 32427,
    week: week,
    weekAverage_ms: 29550,
    models: models,
    incidents: {
      summary: {
        total_last_24h: 1,
        total_last_7d: 10,
        total_last_30d: 42,
      }
    },
  };
})();
