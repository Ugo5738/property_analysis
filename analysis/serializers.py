from rest_framework import serializers

from analysis.models import AnalysisTask, Prompt, Property, PropertyImage


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = [
            "id",
            "image",
            "original_url",
            "main_category",
            "sub_category",
            "room_type",
            "condition_label",
            "reasoning",
        ]


class PropertySerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = [
            "id",
            "url",
            "address",
            "price",
            "bedrooms",
            "bathrooms",
            "size",
            "house_type",
            "agent",
            "description",
            "reviewed_description",
            "listing_type",
            "time_on_market",
            "floorplan_urls",
            "overall_condition",
            "detailed_analysis",
            "failed_downloads",
            "image_urls",
            "overall_analysis",
            "created_at",
            "updated_at",
            "images",
        ]


class AnalysisTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisTask
        fields = [
            "id",
            "property",
            "status",
            "progress",
            "stage",
            "stage_progress",
            "created_at",
            "updated_at",
        ]


class PromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prompt
        fields = ["name", "content"]  # , "spaces"]


class PromptUpdateSerializer(serializers.Serializer):
    name = serializers.CharField()
    content = serializers.CharField()
    # spaces = serializers.ListField(child=serializers.CharField(), required=False)
