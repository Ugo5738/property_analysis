import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from decouple import config
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.models import AnalysisTask, Property, PropertyImage
from analysis.serializers import (
    AnalysisTaskSerializer,
    PropertyImageSerializer,
    PropertySerializer,
)
from analysis.tasks import analyze_property, clear_property_data
from property_analysis.config.logging_config import configure_logger
from utils.openai_analysis import get_openai_chat_response

logger = configure_logger(__name__)


class PropertyViewSet(viewsets.ModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer

    @action(detail=False, methods=["get", "post"])
    def analyze(self, request):
        url = request.data.get("url")
        property_id = request.data.get("property_id")
        user_phone_number = request.data.get("user_phone_number")

        if not url:
            instruction = "Your task is to extract the url from the text. Example format is 'https://rightmove.com/<property_id>/'"
            message = url
            prompt_format = {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
                "additionalProperties": False,
            }
            url = async_to_sync(get_openai_chat_response)(
                instruction, message, prompt_format
            )

        if not property_id and not user_phone_number:
            return Response(
                {"error": "property_id or user phone number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine the source from the URL
        if "rightmove" in url:
            source = "rightmove"
        elif "onthemarket" in url:
            source = "onthemarket"
        else:
            return Response(
                {"error": "Unsupported URL source."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if property_id:
            try:
                property_instance = Property.objects.get(
                    id=property_id, user_phone_number=user_phone_number
                )
                url = property_instance.url
            except Property.DoesNotExist:
                return Response(
                    {"error": "Property not found"}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            property_instance, created = Property.objects.get_or_create(
                url=url, user_phone_number=user_phone_number
            )

        # Clear existing data
        clear_property_data(property_instance)

        task = AnalysisTask.objects.create(
            property=property_instance, user_phone_number=user_phone_number
        )

        # Send HTTP request to scraper app to start scraping
        try:
            if config("DJANGO_SETTINGS_MODULE") == "property_analysis.settings.staging":
                # Prepare callback URL
                callback_url = f"{settings.MY_DOMAIN}{reverse('scraping-callback')}"
                logger.info(f"Generated callback URL: {callback_url}")
                response = requests.post(
                    "http://analysis-scraper-app:8001/api/site-scrapers/scrape/",
                    json={
                        "url": url,
                        "source": source,
                        "callback_url": callback_url,
                        "property_id": property_instance.id,
                        "task_id": task.id,
                        "user_phone_number": user_phone_number,
                    },
                    timeout=10,
                )
            elif config("DJANGO_SETTINGS_MODULE") == "property_analysis.settings.prod":
                # Prepare callback URL
                callback_url = request.build_absolute_uri(reverse("scraping-callback"))
                logger.info(f"Generated callback URL: {callback_url}")
                response = requests.post(
                    "https://52.23.156.175/api/site-scrapers/scrape/",
                    json={
                        "url": url,
                        "source": source,
                        "callback_url": callback_url,
                        "property_id": property_instance.id,
                        "task_id": task.id,
                        "user_phone_number": user_phone_number,
                    },
                    timeout=10,
                    verify=False,
                )
                response.raise_for_status()
            job_id = response.json().get("job_id")
            task.save()
        except requests.RequestException as e:
            logger.error(f"Failed to start scraping job: {str(e)}")
            return Response(
                {"error": "Failed to start scraping job."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"task_id": task.id, "property_id": property_instance.id},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def analysis_status(self, request, pk=None):
        property = self.get_object()
        task = property.analysis_tasks.latest("created_at")
        serializer = AnalysisTaskSerializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        task = get_object_or_404(AnalysisTask, id=pk)
        property_instance = task.property

        if task.status != "complete":
            return Response(
                {
                    "status": task.status,
                    "progress": task.progress,
                    "stage": task.stage,
                    "message": "Analysis not yet complete",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        result = {
            "property_url": property_instance.url,
            "address": property_instance.address,
            "price": str(property_instance.price),
            "bedrooms": property_instance.bedrooms,
            "bathrooms": property_instance.bathrooms,
            "size": property_instance.size,
            "house_type": property_instance.house_type,
            "agent": property_instance.agent,
            "description": property_instance.description,
            "reviewed_description": property_instance.reviewed_description,
            "listing_type": property_instance.listing_type,
            "time_on_market": property_instance.time_on_market,
            "features": property_instance.features,
            "image_urls": property_instance.image_urls,
            "floorplan_urls": property_instance.floorplan_urls,
            "overall_analysis": property_instance.overall_analysis,
            # 'detailed_analysis': property_instance.detailed_analysis,
            "stages": task.stage_progress or {},
        }

        return Response(result)

    @action(detail=False, methods=["get"])
    def list_properties(self, request):
        user_phone_number = request.query_params.get("user_phone_number")
        if not user_phone_number:
            return Response(
                {"error": "User phone number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        properties = Property.objects.filter(
            user_phone_number=user_phone_number
        ).order_by("-created_at")
        serializer = self.get_serializer(properties, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        user_phone_number = request.query_params.get("user_phone_number")
        if not user_phone_number:
            return Response(
                {"error": "User phone number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        property_instance = get_object_or_404(
            Property, pk=kwargs["pk"], user_phone_number=user_phone_number
        )
        serializer = self.get_serializer(property_instance)
        return Response(serializer.data)


class ScrapingCallbackView(APIView):
    def post(self, request):
        # Check if this is a progress update
        if "progress" in request.data:
            # Handle progress update
            job_id = request.data.get("job_id")
            progress_data = request.data.get("progress")
            user_phone_number = request.data.get("user_phone_number")

            if not job_id or progress_data is None or not user_phone_number:
                return Response(
                    {"error": "Invalid progress data."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Retrieve user_id or group associated with the job
            # user_id = request.user.id if authentication is implemented

            # Send progress update via WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"analysis_{user_phone_number}",
                {
                    "type": "analysis_progress",
                    "message": progress_data,
                },
            )

            return Response(status=status.HTTP_200_OK)
        else:
            # Extract data from the callback
            job_id = request.data.get("job_id")
            property_id = request.data.get("property_id")
            task_id = request.data.get("task_id")
            user_phone_number = request.data.get("user_phone_number")

            if not job_id or not property_id or not task_id or not user_phone_number:
                return Response(
                    {"error": "Invalid callback data."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # user_id = request.user.id if authentication is implemented

            # Enqueue task to process the scraped data
            analyze_property.delay(property_id, task_id, user_phone_number, job_id)

            return Response(status=status.HTTP_200_OK)


class PropertyImageViewSet(viewsets.ModelViewSet):
    queryset = PropertyImage.objects.all()
    serializer_class = PropertyImageSerializer

    def create(self, request, *args, **kwargs):
        property_id = request.data.get("property")
        property = get_object_or_404(Property, id=property_id)

        images = request.FILES.getlist("images")
        created_images = []

        for image in images:
            property_image = PropertyImage.objects.create(
                property=property, image=image
            )
            created_images.append(property_image)

        serializer = self.get_serializer(created_images, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
