import os
import base64
import requests

from langflow.custom import Component
from langflow.io import MessageTextInput, Output
from langflow.schema import Data


class JiraTicketTool(Component):
    display_name = "Jira Ticket Tool"
    description = "Creates a Jira Task in the SCRUM project."
    icon = "Ticket"
    name = "JiraTicketTool"

    inputs = [
        MessageTextInput(
            name="summary",
            display_name="Summary",
            tool_mode=True,
        ),
        MessageTextInput(
            name="description",
            display_name="Description",
            tool_mode=True,
        ),
    ]

    outputs = [
        Output(
            name="ticket",
            display_name="Ticket",
            method="create_ticket",
        ),
    ]

    def create_ticket(self) -> Data:
        jira_url = os.environ["JIRA_URL"].rstrip("/")
        jira_email = os.environ["JIRA_EMAIL"].strip()
        jira_token = os.environ["JIRA_API_TOKEN"].strip()

        credentials = f"{jira_email}:{jira_token}"

        encoded_credentials = base64.b64encode(
            credentials.encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        payload = {
            "fields": {
                "project": {
                    "key": "SCRUM"
                },
                "summary": str(self.summary).strip(),
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": str(self.description).strip(),
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {
                    "name": "Task"
                },
            }
        }

        response = requests.post(
            f"{jira_url}/rest/api/3/issue",
            headers=headers,
            json=payload,
            timeout=20,
        )

        if response.status_code != 201:
            raise RuntimeError(
                f"Jira ticket creation failed: "
                f"HTTP {response.status_code} - {response.text}"
            )

        data = response.json()

        return Data(
            data={
                "success": True,
                "ticket_key": data["key"],
                "ticket_id": data["id"],
                "url": f"{jira_url}/browse/{data['key']}",
            }
        )
