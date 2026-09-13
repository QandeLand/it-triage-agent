import os
import requests

from langflow.custom import Component
from langflow.io import MessageTextInput, Output
from langflow.schema import Data


class SlackNotificationTool(Component):
    display_name = "Slack Notification"
    description = "Send a message to Slack using an Incoming Webhook."
    icon = "MessageSquare"
    name = "SlackNotificationTool"

    inputs = [
        MessageTextInput(
            name="message",
            display_name="Message",
            info="Message to send to Slack.",
            tool_mode=True,
        ),
    ]

    outputs = [
        Output(
            name="result",
            display_name="Result",
            method="send_message",
        ),
    ]

    def send_message(self) -> Data:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")

        if not webhook_url:
            raise RuntimeError("SLACK_WEBHOOK_URL is not configured.")

        response = requests.post(
            webhook_url,
            json={"text": self.message},
            timeout=20,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Slack webhook failed: HTTP {response.status_code} - {response.text}"
            )

        return Data(
            data={
                "success": True,
                "message": self.message,
            }
        )
