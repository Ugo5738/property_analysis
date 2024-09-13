# from django.contrib.postgres.fields import JSONField
# from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _

# replace models.JSONField with postgres JSONField


class Property(models.Model):
    url = models.URLField(unique=True)
    overall_condition = models.JSONField(null=True, blank=True)
    detailed_analysis = models.JSONField(null=True, blank=True)
    failed_downloads = models.JSONField(default=list)
    image_urls = models.JSONField(default=list)
    overall_analysis = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Property")
        verbose_name_plural = _("Properties")


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='property_images/')
    original_url = models.URLField()
    main_category = models.CharField(max_length=100)  # e.g., "internal", "external", "floor plan"
    sub_category = models.CharField(max_length=100)  # e.g., "living_spaces", "kitchen", "bedroom"
    room_type = models.CharField(max_length=100, blank=True)  # e.g., "living room", "master bedroom"
    condition_label = models.CharField(max_length=100, blank=True)
    reasoning = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Property Image")
        verbose_name_plural = _("Property Images")


class GroupedImages(models.Model):
    property = models.ForeignKey(Property, related_name='grouped_images', on_delete=models.CASCADE)
    main_category = models.CharField(max_length=100)
    sub_category = models.CharField(max_length=100)
    images = models.ManyToManyField(PropertyImage)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Grouped Images")
        verbose_name_plural = _("Grouped Images")
        unique_together = ('property', 'main_category', 'sub_category')


class MergedPropertyImage(models.Model):
    property = models.ForeignKey(Property, related_name='merged_images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='merged_property_images/')
    main_category = models.CharField(max_length=100)  # e.g., "internal_living_spaces"
    sub_category = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Merged Property Image")
        verbose_name_plural = _("Merged Property Images")
        # unique_together = ('property', 'main_category', 'sub_category')


class SampleImage(models.Model):
    category = models.CharField(max_length=100)  # e.g., "internal"
    subcategory = models.CharField(max_length=100)  # e.g., "living_spaces"
    condition = models.CharField(max_length=100)  # e.g., "excellent"
    image = models.ImageField(upload_to='sample_images/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Sample Image")
        verbose_name_plural = _("Sample Images")
        # unique_together = ('category', 'subcategory', 'condition')


class MergedSampleImage(models.Model):
    category = models.CharField(max_length=100)  # e.g., "internal"
    subcategory = models.CharField(max_length=100)  # e.g., "living_spaces"
    condition = models.CharField(max_length=100)  # e.g., "excellent"
    image = models.ImageField(upload_to='merged_sample_images/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Merged Sample Image")
        verbose_name_plural = _("Merged Sample Images")
        # unique_together = ('category', 'subcategory', 'condition')


class AnalysisTask(models.Model):
    property = models.ForeignKey(Property, related_name='analysis_tasks', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='PENDING')
    progress = models.FloatField(default=0.0)
    stage = models.CharField(max_length=50, default='')
    stage_progress = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Analysis Task")
        verbose_name_plural = _("Analysis Tasks")
