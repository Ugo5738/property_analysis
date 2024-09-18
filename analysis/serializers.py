from rest_framework import serializers

from analysis.models import AnalysisTask, Property, PropertyImage


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        # fields = ['id', 'image', 'category', 'analysis_result']
        fields = ['id', 'image', 'original_url', 'main_category', 'sub_category', 'room_type', 'condition_label', 'reasoning']

class PropertySerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        # fields = ['id', 'url', 'overall_condition', 'detailed_analysis', 'images']
        fields = ['id', 'url', 'overall_condition', 'detailed_analysis', 'failed_downloads', 'image_urls', 'overall_analysis', 'images', 'created_at', 'updated_at']


class AnalysisTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisTask
        # fields = ['id', 'property', 'status', 'progress', 'created_at', 'updated_at']
        fields = ['id', 'property', 'status', 'progress', 'stage', 'stage_progress', 'created_at', 'updated_at']
