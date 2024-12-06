from django.urls import path, re_path

from analysis import consumers

websocket_urlpatterns = [
    re_path(
        r"ws/analysis-progress/$",
        consumers.AnalysisProgressConsumer.as_asgi(),
    ),
]
