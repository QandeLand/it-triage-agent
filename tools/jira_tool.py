import os
import base64
import requests


def create_jira_ticket(
    summary: str,
    description: str,
    priority: str = "Medium",
):
    """
    Create a Jira issue for the IT Triage Agent.

    Args:
        summary: Short title for the incident.
        description: Detailed incident description.
        priority: Jira priority, e.g. Highest, High, Medium, Low.

    Returns:
        Dictionary containing the Jira ticket information.
    """

    jira_url = os.environ["JIRA_URL"].rstrip("/")
    jira_email = os.environ["JIRA_EMAIL"].strip()
    jira_token = os.environ["JIRA_API_TOKEN"].strip()

    # Jira Cloud authentication: email + API token
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
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            },
            "issuetype": {
                "name": "Task"
            },
            "priority": {
                "name": priority
            }
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

    return {
        "success": True,
        "ticket_key": data["key"],
        "ticket_id": data["id"],
        "url": f"{jira_url}/browse/{data['key']}",
    }