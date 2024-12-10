from django.urls import include, path
from rest_framework.routers import DefaultRouter

from analysis import views

router = DefaultRouter()
router.register(r"properties", views.PropertyViewSet)
router.register(r"property-images", views.PropertyImageViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "scraping-callback/",
        views.ScrapingCallbackView.as_view(),
        name="scraping-callback",
    ),
    path("update-prompt/", views.PromptUpdateView.as_view(), name="update-prompt"),
    path("get-prompt/", views.GetPromptView.as_view(), name="get-prompt"),
]
