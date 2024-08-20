import json
from typing import Any, Dict
from uuid import uuid4

from channels.generic.websocket import AsyncWebsocketConsumer

from property_analysis.config.logging_config import configure_logger

logger = configure_logger(__name__)

class AnalysisProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            self.analysis_group_name = f"analysis_{self.user.id}"

            await self.channel_layer.group_add(
                self.analysis_group_name,
                self.channel_name
            )

            await self.accept()
            self.session_data: Dict[str, Any] = {}
            logger.info(f"WebSocket connected for user: {self.user.email}")
        else:
            logger.warning("Anonymous user, closing connection")
            await self.close()

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected for user: {self.user_id}. Close code: {close_code}")

        await self.channel_layer.group_discard(
            self.analysis_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']

        logger.info(f"=== MESSAGE RECEIVED FROM USER: {self.user.email} ===")

        # Echo the message back to the WebSocket
        await self.send(text_data=json.dumps({
            'message': message
        }))

    async def analysis_progress(self, event):
        message = event['message']

        await self.send(text_data=json.dumps(message))
