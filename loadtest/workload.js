// Repeatable workload. Usage:  LOAD=low|high k6 run loadtest/workload.js
// low  = 10 virtual users, high = 100 virtual users, same request mix each time.
import http from 'k6/http';
import { check, sleep } from 'k6';

const LEVELS = { low: 10, high: 100 };
const load = __ENV.LOAD || 'low';
const base = __ENV.BASE_URL || 'http://localhost:8000';

export const options = {
  vus: LEVELS[load],
  duration: __ENV.DURATION || '60s',
};

export default function () {
  // 80% light requests, 20% heavy requests (fixed pattern => repeatable)
  const r = (__ITER % 5 === 0)
    ? http.get(`${base}/heavy?ms=50&mb=5`)
    : http.get(`${base}/light`);
  check(r, { 'status is 200': (res) => res.status === 200 });
  sleep(0.1);
}
