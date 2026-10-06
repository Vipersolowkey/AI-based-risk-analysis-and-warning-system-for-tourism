// Run with Node 20+ against local backend :8000 and frontend :5173.
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');

async function main() {
  const api = 'http://127.0.0.1:8000';
  const registration = await fetch(`${api}/api/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: `receipt-qa-${Date.now()}@example.com`, password: 'LocalQaOnly123!' }) });
  assert.equal(registration.status, 200);
  const auth = await registration.json();
  const headers = { Authorization: `Bearer ${auth.token}`, 'Content-Type': 'application/json' };
  const response = await fetch(`${api}/trip?destination=Da%20Lat&lat=10.77&lon=106.69`, { headers });
  assert.equal(response.status, 200);
  const trip = await response.json();
  assert.ok(trip.history_id, 'trip must be saved');
  const issued = await fetch(`${api}/api/receipts/trips/${trip.history_id}`, { method: 'POST', headers });
  assert.equal(issued.status, 200);
  const receipt = await issued.json();
  assert.equal(createHash('sha256').update(receipt.canonical).digest('hex'), receipt.sha256);
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    const failures = [];
    page.on('pageerror', error => failures.push(error.message));
    await page.addInitScript(({ auth, trip }) => {
      sessionStorage.setItem('va_logged_in_session', 'true');
      localStorage.setItem('va_session', JSON.stringify({ user: { email: auth.user.email, token: auth.token }, ts: Date.now() }));
      localStorage.setItem('vtra_trip_context_v2', JSON.stringify({ savedAt: Date.now(), tripRes: trip, tripCheckedAt: Date.now(), destination: 'Đà Lạt', forecastData: [], routeCoords: [] }));
    }, { auth, trip });
    await page.goto('http://127.0.0.1:5173/result');
    await page.getByRole('button', { name: 'Tải / xác minh lại', exact: true }).click();
    await page.getByText(`SHA-256: ${receipt.sha256}`, { exact: true }).waitFor();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Tải bằng chứng JSON' }).click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), `travelshield-${receipt.id}.json`);
    await page.getByRole('button', { name: 'Ghi bằng chứng lên Solana devnet' }).click();
    await page.getByText('Hãy dùng trình duyệt có ví Solana (Phantom), rồi thử lại.', { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile must not overflow');
    await page.goto('http://127.0.0.1:5173/history');
    await page.locator('summary').filter({ hasText: 'Da Lat' }).first().click();
    await page.getByRole('button', { name: 'Tải / xác minh lại', exact: true }).first().click();
    await page.getByText(`SHA-256: ${receipt.sha256}`, { exact: true }).waitFor();
    assert.deepEqual(failures, []);
    console.log(JSON.stringify({ ui: 'passed', download: 'passed', mobile: 'passed', history: 'passed', trip_id: trip.history_id, weather: trip.weather?.detection_method, news_status: trip.risk?.data_status, receipt: receipt.id }, null, 2));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
