from django.urls import path

from analysis import consumers

websocket_urlpatterns = [
    path("ws/analysis-progress/", consumers.AnalysisProgressConsumer.as_asgi()),
]
