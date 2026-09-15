import random
import time

from flask import Flask, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# Metrics definitions

# Counter: only ever goes up. Tracks total requests received.
REQUEST_COUNT = Counter(
    "app_requests_total",
    "Total number of requests received",
    ["endpoint"]
)

# Counter: tracks total errors, separately from total requests.
ERROR_COUNT = Counter(
    "app_errors_total",
    "Total number of errors returned",
    ["endpoint"]
)

# Histogram: tracks how long requests take, in seconds.
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"]
)


# Simulated "real" service endpoints. These endpoints are instrumented with Prometheus metrics to track request counts, errors, and latency.

@app.route("/")
def home():
    endpoint = "home"
    start_time = time.time()

    REQUEST_COUNT.labels(endpoint=endpoint).inc()

    # Simulate occasional slowness (10% chance of a slow response)
    if random.random() < 0.1:
        time.sleep(random.uniform(0.5, 2.0))

    # Simulate occasional errors (5% chance of failure)
    if random.random() < 0.05:
        ERROR_COUNT.labels(endpoint=endpoint).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
        return "Internal error", 500

    REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
    return "OK - payment-service is healthy"


@app.route("/checkout")
def checkout():
    endpoint = "checkout"
    start_time = time.time()

    REQUEST_COUNT.labels(endpoint=endpoint).inc()

    # This endpoint simulates a higher error rate, useful for triggering
    # your IT triage agent's P1/P2 logic on purpose during testing.
    if random.random() < 0.15:
        time.sleep(random.uniform(0.3, 1.5))

    if random.random() < 0.1:
        ERROR_COUNT.labels(endpoint=endpoint).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
        return "Checkout failed", 500

    REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
    return "Checkout successful"


# Prometheus scrape endpoint

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)