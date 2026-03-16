import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// ─────────────────────────────────────────
// Custom metrics
// ─────────────────────────────────────────
const errorRate      = new Rate('error_rate');
const shortenTrend   = new Trend('shorten_duration',  true);
const redirectTrend  = new Trend('redirect_duration', true);
const feedbackTrend  = new Trend('feedback_duration', true);

// ─────────────────────────────────────────
// Smoke test config — 50 VUs, 1 minute
// ─────────────────────────────────────────
export const options = {
    vus:      50,
    duration: '1m',

    thresholds: {
        // Overall error rate must stay below 1%
        'error_rate':                     ['rate<0.01'],

        // 95th percentile latency per endpoint
        'shorten_duration':               ['p(95)<800'],
        'redirect_duration':              ['p(95)<500'],
        // feedback_duration has no threshold — only 1 VU hits it (rate limit safe)

        // Built-in k6 metrics
        'http_req_failed':                ['rate<0.01'],
        'http_req_duration':              ['p(95)<1000'],
    },
};

// ─────────────────────────────────────────
// Config
// ─────────────────────────────────────────
const BASE_URL = 'https://treecom.site';

// Sample URLs to shorten — VUs cycle through these
// so we don't hammer DB with identical inserts
const SAMPLE_URLS = [
    'https://github.com/ayush729874/jenkins-build',
    'https://github.com/ayush729874/k8s_builds',
    'https://kubernetes.io/docs/concepts/',
    'https://docs.docker.com/get-started/',
    'https://grafana.com/docs/loki/latest/',
    'https://argoproj.github.io/argo-cd/',
    'https://fastapi.tiangolo.com/',
    'https://www.jenkins.io/doc/book/pipeline/',
];

const FEEDBACK_MESSAGES = [
    'Great tool!',
    'Works perfectly.',
    'Very fast!',
    'Love the UI.',
    'Handy shortener.',
];

// ─────────────────────────────────────────
// Shared state — short codes generated
// in shorten test are reused in redirect test
// ─────────────────────────────────────────
let capturedShortCode = null;

// ─────────────────────────────────────────
// Main VU loop
// ─────────────────────────────────────────
export default function () {

    // Pick a URL based on VU index so requests are varied
    const urlIndex      = (__VU - 1) % SAMPLE_URLS.length;
    const feedbackIndex = (__VU - 1) % FEEDBACK_MESSAGES.length;

    // ── Group 1: Shorten a URL ──────────────
    group('POST /api/shorten', () => {
        const payload = JSON.stringify({
            url: SAMPLE_URLS[urlIndex],
        });

        const res = http.post(
            `${BASE_URL}/api/shorten`,
            payload,
            {
                headers: { 'Content-Type': 'application/json' },
                tags:    { endpoint: 'shorten' },
            }
        );

        shortenTrend.add(res.timings.duration);

        const ok = check(res, {
            'shorten → status 200':        (r) => r.status === 200,
            'shorten → has short_url':     (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.short_url !== undefined && body.short_url !== '';
                } catch (_) { return false; }
            },
            'shorten → short_url has host': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.short_url.includes('treecom.site');
                } catch (_) { return false; }
            },
        });

        errorRate.add(!ok);

        // Capture the short code for use in redirect test
        if (ok) {
            try {
                const body      = JSON.parse(res.body);
                // short_url format: https://treecom.site/s/abc123
                const parts     = body.short_url.split('/');
                capturedShortCode = parts[parts.length - 1];
            } catch (_) {
                capturedShortCode = null;
            }
        }
    });

    sleep(0.5);

    // ── Group 2: Follow the short link ──────
    group('GET /s/{code}', () => {
        // Use captured code if available, fallback to a dummy
        const code = capturedShortCode || 'healthcheck';

        const res = http.get(
            `${BASE_URL}/s/${code}`,
            {
                redirects: 0,           // Don't follow — we just check the redirect response
                tags: { endpoint: 'redirect' },
            }
        );

        redirectTrend.add(res.timings.duration);

        const ok = check(res, {
            // Expect 301/302 redirect, or 404 if code was invalid — NOT a 500
            'redirect → not a server error': (r) => r.status < 500,
            'redirect → responds fast':      (r) => r.timings.duration < 500,
        });

        errorRate.add(!ok);
    });

    sleep(0.5);

    // ── Group 3: Submit feedback ─────────────
    // Only VU #1 runs this — avoids 429 rate limit errors from 50 VUs
    // hammering the same endpoint. Goal is just "is it alive?" not perf testing it.
    if (__VU === 1) {
        group('POST /feedback', () => {
            const payload = JSON.stringify({
                message: FEEDBACK_MESSAGES[feedbackIndex],
            });

            const res = http.post(
                `${BASE_URL}/feedback`,
                payload,
                {
                    headers: { 'Content-Type': 'application/json' },
                    tags:    { endpoint: 'feedback' },
                }
            );

            feedbackTrend.add(res.timings.duration);

            const ok = check(res, {
                // 200/201 = success, 429 = rate limited (server working fine), both are OK
                'feedback → endpoint alive':    (r) => r.status === 200 || r.status === 201 || r.status === 429,
                'feedback → no server error':   (r) => r.status < 500,
            });

            if (res.status === 429) {
                console.log('ℹ️  /feedback rate limited (429) — endpoint is alive, limit is working correctly');
            }

            errorRate.add(!ok);
        });
    }

    sleep(1);
}

// ─────────────────────────────────────────
// End-of-test summary
// ─────────────────────────────────────────
export function handleSummary(data) {
    const pass = data.metrics.error_rate.values.rate < 0.01;

    const summary = `
╔══════════════════════════════════════════════════════╗
║           TREECOM SMOKE TEST — SUMMARY               ║
╠══════════════════════════════════════════════════════╣
║  Result        : ${pass ? '✅ PASSED' : '❌ FAILED'}                          
║  VUs           : 50                                  
║  Duration      : 1 minute                            
╠══════════════════════════════════════════════════════╣
║  LATENCY (p95)                                       
║  Shorten    : ${String(data.metrics.shorten_duration  ? data.metrics.shorten_duration.values['p(95)'].toFixed(0)  + ' ms' : 'N/A').padEnd(10)}                          
║  Redirect   : ${String(data.metrics.redirect_duration ? data.metrics.redirect_duration.values['p(95)'].toFixed(0) + ' ms' : 'N/A').padEnd(10)}                          
║  Feedback   : ${String(data.metrics.feedback_duration ? data.metrics.feedback_duration.values['p(95)'].toFixed(0) + ' ms' : 'N/A').padEnd(10)}                          
╠══════════════════════════════════════════════════════╣
║  Error Rate    : ${String((data.metrics.error_rate.values.rate * 100).toFixed(2) + '%').padEnd(10)}                        
║  Total Reqs    : ${String(data.metrics.http_reqs.values.count).padEnd(10)}                        
╚══════════════════════════════════════════════════════╝
`;

    console.log(summary);

    // Return JSON for potential CI parsing
    return {
        'stdout': summary,
        'smoke-test-result.json': JSON.stringify({
            passed:      pass,
            error_rate:  data.metrics.error_rate.values.rate,
            total_reqs:  data.metrics.http_reqs.values.count,
            p95_shorten:  data.metrics.shorten_duration  ? data.metrics.shorten_duration.values['p(95)']  : null,
            p95_redirect: data.metrics.redirect_duration ? data.metrics.redirect_duration.values['p(95)'] : null,
            p95_feedback: data.metrics.feedback_duration ? data.metrics.feedback_duration.values['p(95)'] : null,
        }, null, 2),
    };
}
