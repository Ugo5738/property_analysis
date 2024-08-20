from django.urls import include, path
from rest_framework.routers import DefaultRouter

from analysis.views import PropertyImageViewSet, PropertyViewSet

router = DefaultRouter()
router.register(r'properties', PropertyViewSet)
router.register(r'property-images', PropertyImageViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
