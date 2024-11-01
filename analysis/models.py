import hashlib

from django.db import models
from django.utils.translation import gettext_lazy as _


class Property(models.Model):
    url = models.URLField(unique=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bedrooms = models.IntegerField(null=True, blank=True)
    bathrooms = models.IntegerField(null=True, blank=True)
    size = models.CharField(max_length=100, null=True, blank=True)
    house_type = models.CharField(max_length=100, null=True, blank=True)
    agent = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    floorplan_urls = models.JSONField(default=list, blank=True)
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
    property = models.ForeignKey(
        Property, related_name="images", on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to="property_images/")
    original_url = models.URLField()
    main_category = models.CharField(
        max_length=100
    )  # e.g., "internal", "external", "floor plan"
    sub_category = models.CharField(
        max_length=100
    )  # e.g., "living_spaces", "kitchen", "bedroom"
    room_type = models.CharField(
        max_length=100, blank=True
    )  # e.g., "living room", "master bedroom"
    condition_label = models.CharField(max_length=100, blank=True)
    condition_score = models.IntegerField(null=True, blank=True)
    reasoning = models.TextField(blank=True)
    embedding = models.JSONField(null=True, editable=False)
    similarity_scores = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Property Image")
        verbose_name_plural = _("Property Images")


class GroupedImages(models.Model):
    property = models.ForeignKey(
        Property, related_name="grouped_images", on_delete=models.CASCADE
    )
    main_category = models.CharField(max_length=100)
    sub_category = models.CharField(max_length=100)
    images = models.ManyToManyField(PropertyImage)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Grouped Images")
        verbose_name_plural = _("Grouped Images")
        unique_together = ("property", "main_category", "sub_category")


class MergedPropertyImage(models.Model):
    property = models.ForeignKey(
        Property, related_name="merged_images", on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to="merged_property_images/")
    main_category = models.CharField(max_length=100)  # e.g., "internal_living_spaces"
    sub_category = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    images = models.ManyToManyField(PropertyImage)

    class Meta:
        verbose_name = _("Merged Property Image")
        verbose_name_plural = _("Merged Property Images")
        # unique_together = ('property', 'main_category', 'sub_category')


class SampleImage(models.Model):
    category = models.CharField(max_length=100)  # e.g., "internal"
    subcategory = models.CharField(max_length=100)  # e.g., "living_spaces"
    condition = models.CharField(max_length=100)  # e.g., "excellent"
    image = models.ImageField(upload_to="sample_images/")
    image_hash = models.CharField(max_length=32, unique=True, editable=False)
    embedding = models.JSONField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Sample Image")
        verbose_name_plural = _("Sample Images")
        # unique_together = ('category', 'subcategory', 'condition')

    def save(self, *args, **kwargs):
        if not self.image_hash:
            self.image_hash = self.compute_image_hash()
        super().save(*args, **kwargs)

    def compute_image_hash(self):
        """Compute the MD5 hash of the image file."""
        hasher = hashlib.md5()
        if self.image and hasattr(self.image, "path"):
            with open(self.image.path, "rb") as img_file:
                # Read the image in chunks to handle large files efficiently
                for chunk in iter(lambda: img_file.read(4096), b""):
                    hasher.update(chunk)
        return hasher.hexdigest()

    def __str__(self):
        return f"{self.category}/{self.subcategory}/{self.condition}/{self.image.name}"


class MergedSampleImage(models.Model):
    category = models.CharField(max_length=100)  # e.g., "internal"
    subcategory = models.CharField(max_length=100)  # e.g., "living_spaces"
    condition = models.CharField(max_length=100)  # e.g., "excellent"
    image = models.ImageField(upload_to="merged_sample_images/")
    quadrant_mapping = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Merged Sample Image")
        verbose_name_plural = _("Merged Sample Images")
        # unique_together = ('category', 'subcategory', 'condition')


class AnalysisTask(models.Model):
    property = models.ForeignKey(
        Property, related_name="analysis_tasks", on_delete=models.CASCADE
    )
    status = models.CharField(max_length=20, default="PENDING")
    progress = models.FloatField(default=0.0)
    stage = models.CharField(max_length=50, default="")
    stage_progress = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Analysis Task")
        verbose_name_plural = _("Analysis Tasks")
