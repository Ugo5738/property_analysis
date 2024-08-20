from rest_framework import serializers

from analysis.models import AnalysisTask, Property, PropertyImage


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ['id', 'image', 'category', 'analysis_result']

class PropertySerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = ['id', 'url', 'overall_condition', 'detailed_analysis', 'images']

class AnalysisTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisTask
        fields = ['id', 'property', 'status', 'progress', 'created_at', 'updated_at']
