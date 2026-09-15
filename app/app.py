import os
import random
import time
import json
import logging

from flask import Flask, Response, request, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)

REQUEST_COUNT = Counter(
    "app_requests_total",
    "Total number of requests received",
    ["endpoint", "method", "status"],
)
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
ERROR_COUNT = Counter(
    "app_errors_total",
    "Total number of 5xx responses",
    ["endpoint"],
)


def _record(endpoint, method, status, start):
    REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=str(status)).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start)
    if 500 <= status < 600:
        ERROR_COUNT.labels(endpoint=endpoint).inc()


@app.route("/")
def home():
    start = time.time()
    if random.random() < 0.1:
        time.sleep(random.uniform(0.5, 2.0))
    if random.random() < 0.05:
        _record("home", request.method, 500, start)
        return "Internal error", 500
    _record("home", request.method, 200, start)
    return "OK - payment-service is healthy"


@app.route("/checkout")
def checkout():
    start = time.time()
    if random.random() < 0.15:
        time.sleep(random.uniform(0.3, 1.5))
    if random.random() < 0.10:
        _record("checkout", request.method, 500, start)
        return "Checkout failed", 500
    _record("checkout", request.method, 200, start)
    return "Checkout successful"


@app.route("/health")
def health():
    return jsonify(status="ok"), 200


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    log.info("ALERT_WEBHOOK %s", json.dumps(payload))
    return jsonify(received=True, alerts=len(payload.get("alerts", []))), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
