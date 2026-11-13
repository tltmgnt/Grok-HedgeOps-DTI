"""Offline tests for read-only stock discovery (no network or credentials)."""
import io
import json
import unittest
from urllib.error import HTTPError

from stock_discovery import build_report, evaluate, fetch_bars, markdown


def sample_bars(n=45, step=0.4, volume=100):
    return [
        {"t": f"2026-08-{(i // 28) + 1:02d}T{i:02d}:00:00Z",
         "c": 100 + i * step, "v": volume * (3 if i == n - 1 else 1)}
        for i in range(n)
    ]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *args):
        return False


class DiscoveryTests(unittest.TestCase):
    def test_ranks_observed_momentum(self):
        positive = evaluate("AAA", sample_bars(step=0.4))
        negative = evaluate("BBB", sample_bars(step=-0.2))
        self.assertGreater(positive["score"], negative["score"])
        self.assertGreater(positive["relative_volume_1d"], 2)
        self.assertTrue(positive["above_ma20"])

    def test_rejects_insufficient_or_bad_data(self):
        self.assertIsNone(evaluate("AAA", sample_bars(n=20)))
        bad = sample_bars()
        for bar in bad:
            bar["v"] = 0
        self.assertIsNone(evaluate("AAA", bad))

    def test_report_top_ten_and_disclaimer(self):
        symbols = [f"S{i:02d}" for i in range(12)]
        bars = {symbol: sample_bars(step=0.1 + i * 0.02)
                for i, symbol in enumerate(symbols)}
        report = build_report(symbols, bars, generated_at="2026-11-04T00:00:00Z")
        self.assertEqual(len(report["candidates"]), 10)
        self.assertIn("not financial advice", report["disclaimer"])
        self.assertIn("No orders were submitted", markdown(report))

    def test_get_only_iex_and_pagination(self):
        seen = []
        def opener(request, timeout):
            seen.append(request)
            if len(seen) == 1:
                return FakeResponse({"bars": {"SPY": sample_bars(31)}, "next_page_token": "next"})
            return FakeResponse({"bars": {"SPY": sample_bars(2)}, "next_page_token": None})
        bars = fetch_bars(["SPY"], "test-key", "test-secret", opener=opener)
        self.assertEqual(len(bars["SPY"]), 33)
        self.assertTrue(all(r.get_method() == "GET" for r in seen))
        self.assertTrue(all("feed=iex" in r.full_url for r in seen))
        self.assertTrue(all("/v2/stocks/bars?" in r.full_url for r in seen))
        self.assertIn("page_token=next", seen[1].full_url)
        self.assertNotIn("test-secret", seen[0].full_url)

    def test_missing_credentials_fails_closed(self):
        with self.assertRaises(ValueError):
            fetch_bars(["SPY"], "", "")

    def test_http_401_provides_safe_remediation(self):
        def fail(request, timeout):
            raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)
        with self.assertRaisesRegex(RuntimeError, "HTTP 401: credentials rejected") as context:
            fetch_bars(["SPY"], "private-key", "private-secret", opener=fail)
        message = str(context.exception)
        self.assertIn("ALPACA_API_KEY", message)
        self.assertIn("ALPACA_API_SECRET", message)
        self.assertNotIn("private-key", message)
        self.assertNotIn("private-secret", message)

    def test_http_error_does_not_expose_credentials(self):
        def fail(request, timeout):
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403") as context:
            fetch_bars(["SPY"], "key", "private-secret", opener=fail)
        self.assertNotIn("private-secret", str(context.exception))


if __name__ == "__main__":
    unittest.main()
