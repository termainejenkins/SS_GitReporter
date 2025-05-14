import requests
import logging
from typing import Optional

class DiscordClient:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.logger = logging.getLogger(__name__)

    def send_message(self, content: str) -> bool:
        try:
            response = requests.post(
                self.webhook_url,
                json={"content": content}
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to send Discord message: {str(e)}")
            return False 