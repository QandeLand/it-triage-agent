import os
import requests

from langflow.custom import Component
from langflow.io import MessageTextInput, Output
from langflow.schema import Data


class PrometheusQueryTool(Component):
    display_name = "Prometheus Query"
    description = "Queries Prometheus for a live metric value using PromQL."
    icon = "Activity"
    name = "PrometheusQueryTool"

    inputs = [
        MessageTextInput(
            name="query",
            display_name="PromQL Query",
            info="e.g. app_requests_total or rate(app_errors_total[5m])",
            tool_mode=True,
        ),
    ]

    outputs = [
        Output(
            name="result",
            display_name="Result",
            method="run_query",
        ),
    ]

    def run_query(self) -> Data:
        prometheus_url = os.getenv("PROMETHEUS_URL", "http://host.docker.internal:9090")

        query = str(self.query).strip()

        if not query:
            raise ValueError("Query cannot be empty.")

        response = requests.get(
            f"{prometheus_url.rstrip('/')}/api/v1/query",
            params={"query": query},
            timeout=20,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Prometheus query failed: "
                f"HTTP {response.status_code} - {response.text}"
            )

        data = response.json()

        return Data(
            data={
                "success": True,
                "query": query,
                "result": data.get("data", {}).get("result", []),
            }
        )