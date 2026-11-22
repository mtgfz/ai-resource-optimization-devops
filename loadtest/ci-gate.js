// Small, fast load test used by the CI "performance gate".
// If a threshold is broken, k6 exits with a non-zero code and the pipeline fails.
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '25s',
  thresholds: {
    http_req_failed: ['rate<0.01'],      // less than 1% errors
    http_req_duration: ['p(95)<500'],    // 95% of requests under 500 ms
    checks: ['rate>0.99'],               // more than 99% of checks pass
  },
};

const base = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  const r = (__ITER % 5 === 0)
    ? http.get(`${base}/heavy?ms=50&mb=5`)
    : http.get(`${base}/light`);
  check(r, { 'status is 200': (res) => res.status === 200 });
  sleep(0.1);
}
