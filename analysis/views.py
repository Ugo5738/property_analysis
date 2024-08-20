import json
from venv import logger

from asgiref.sync import sync_to_async
from celery.exceptions import OperationalError
from channels.db import database_sync_to_async
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from analysis.models import AnalysisTask, Property, PropertyImage
from analysis.serializers import (
    AnalysisTaskSerializer,
    PropertyImageSerializer,
    PropertySerializer,
)
from analysis.tasks import analyze_property
from property_analysis.config.logging_config import configure_logger
from utils.image_processing import get_image_urls

logger = configure_logger(__name__)


class PropertyViewSet(viewsets.ModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer

    @action(detail=False, methods=['get', 'post'])
    def analyze(self, request):
        url = request.data.get('url')

        if not url:
            return Response({'error': 'URL is required'}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'GET':
            url = request.query_params.get('url')
            property_instance = Property.objects.filter(url=url).first()
            if property_instance:
                serializer = self.get_serializer(property_instance)
                return Response(serializer.data)
            return Response({'detail': 'Property not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            property_instance, created = Property.objects.get_or_create(url=url)

            # Get and store image URLs
            image_urls = get_image_urls(url)
            property_instance.image_urls = image_urls
            property_instance.save()

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        task = AnalysisTask.objects.create(property=property_instance)
        try:
            analyze_property.delay(property_instance.id, task.id, request.user.id)
        except OperationalError as e:
            logger.error(f"Celery operational error: {str(e)}")
            return Response({'error': 'Task queueing failed. Please try again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({'task_id': task.id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['get'])
    def analysis_status(self, request, pk=None):
        property = self.get_object()
        task = property.analysis_tasks.latest('created_at')
        serializer = AnalysisTaskSerializer(task)
        return Response(serializer.data)


class PropertyImageViewSet(viewsets.ModelViewSet):
    queryset = PropertyImage.objects.all()
    serializer_class = PropertyImageSerializer

    def create(self, request, *args, **kwargs):
        property_id = request.data.get('property')
        property = get_object_or_404(Property, id=property_id)

        images = request.FILES.getlist('images')
        created_images = []

        for image in images:
            property_image = PropertyImage.objects.create(property=property, image=image)
            created_images.append(property_image)

        serializer = self.get_serializer(created_images, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


