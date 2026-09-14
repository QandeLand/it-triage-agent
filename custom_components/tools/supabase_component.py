import os
import requests

from langflow.custom import Component
from langflow.io import MessageTextInput, Output
from langflow.schema import Data


class SupabaseIncidentHistoryTool(Component):
    display_name = "Supabase Incident History"
    description = (
        "Searches Supabase for historical IT incidents matching a service."
    )
    icon = "Database"
    name = "SupabaseIncidentHistoryTool"

    inputs = [
        MessageTextInput(
            name="service",
            display_name="Service",
            info="Service name to search for in historical incidents.",
            tool_mode=True,
        ),
    ]

    outputs = [
        Output(
            name="history",
            display_name="History",
            method="search_history",
        ),
    ]

    def search_history(self) -> Data:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url:
            raise RuntimeError("SUPABASE_URL is not configured.")

        if not supabase_key:
            raise RuntimeError(
                "SUPABASE_SERVICE_ROLE_KEY is not configured."
            )

        service = str(self.service).strip()

        if not service:
            raise ValueError("Service name cannot be empty.")

        response = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/incidents",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Accept": "application/json",
            },
            params={
                "service_name": f"eq.{service}",
                "order": "incident_timestamp.desc",
                "limit": "10",
            },
            timeout=20,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Supabase query failed: "
                f"HTTP {response.status_code} - {response.text}"
            )

        incidents = response.json()

        return Data(
            data={
                "success": True,
                "service": service,
                "incident_count": len(incidents),
                "incidents": incidents,
            }
        )
