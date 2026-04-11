import requests
import os
from datetime import datetime, timedelta


class CalendlyClient:
    """Cliente opcional para consultar agendamentos via Calendly API."""

    BASE_URL = "https://api.calendly.com"

    def __init__(self):
        self.api_key = os.getenv("CALENDLY_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get_user_uri(self) -> str | None:
        resp = requests.get(f"{self.BASE_URL}/users/me", headers=self.headers)
        if resp.ok:
            return resp.json()["resource"]["uri"]
        return None

    def get_scheduled_events(self, days_ahead: int = 7) -> list:
        """Retorna eventos agendados nos próximos N dias."""
        user_uri = self.get_user_uri()
        if not user_uri:
            return []

        now = datetime.utcnow().isoformat() + "Z"
        future = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

        params = {
            "user": user_uri,
            "min_start_time": now,
            "max_start_time": future,
            "status": "active",
        }

        resp = requests.get(
            f"{self.BASE_URL}/scheduled_events",
            headers=self.headers,
            params=params,
        )

        if resp.ok:
            return resp.json().get("collection", [])
        return []

    def count_scheduled(self, days_ahead: int = 7) -> int:
        return len(self.get_scheduled_events(days_ahead))
