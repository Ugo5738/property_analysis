from django.contrib import admin
from django.db import transaction
from django.db.models import Max
from django.utils.html import format_html

from analysis.models import (
    AnalysisTask,
    GroupedImages,
    MergedPropertyImage,
    MergedSampleImage,
    Prompt,
    Property,
    PropertyImage,
    SampleImage,
)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        "url",
        "created_at",
        "updated_at",
        "failed_downloads_count",
    )
    list_filter = ("created_at", "updated_at")
    search_fields = ("url",)
    readonly_fields = ("created_at", "updated_at")

    def failed_downloads_count(self, obj):
        return len(obj.failed_downloads)

    failed_downloads_count.short_description = "Failed Downloads"


@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "property",
        "image_preview",
        "original_url",
        "main_category",
        "sub_category",
        "room_type",
        "condition_label",
        "created_at",
    )
    list_filter = (
        "created_at",
        "property",
        "main_category",
        "sub_category",
        "room_type",
        "condition_label",
    )
    search_fields = (
        "property__url",
        "original_url",
        "main_category",
        "sub_category",
        "room_type",
        "condition_label",
    )
    readonly_fields = ("created_at",)

    def image_preview(self, obj):
        return format_html('<img src="{}" width="100" height="100" />', obj.image.url)

    image_preview.short_description = "Image Preview"


@admin.register(GroupedImages)
class GroupedImagesAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "main_category",
        "sub_category",
        "image_count",
        "created_at",
    )
    list_filter = ("created_at", "property", "main_category", "sub_category")
    search_fields = ("property__url", "main_category", "sub_category")
    readonly_fields = ("created_at",)

    def image_count(self, obj):
        return obj.images.count()

    image_count.short_description = "Number of Images"


@admin.register(MergedPropertyImage)
class MergedPropertyImageAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "image_preview",
        "main_category",
        "sub_category",
        "created_at",
    )
    list_filter = ("created_at", "property", "main_category", "sub_category")
    search_fields = ("property__url", "main_category", "sub_category")
    readonly_fields = ("created_at",)

    def image_preview(self, obj):
        return format_html('<img src="{}" width="100" height="100" />', obj.image.url)

    image_preview.short_description = "Image Preview"


@admin.register(SampleImage)
class SampleImageAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "subcategory",
        "condition",
        "image_preview",
        "created_at",
    )
    list_filter = ("created_at", "category", "subcategory", "condition")
    search_fields = ("category", "subcategory", "condition")
    readonly_fields = ("created_at",)

    def image_preview(self, obj):
        return format_html('<img src="{}" width="100" height="100" />', obj.image.url)

    image_preview.short_description = "Image Preview"


@admin.register(MergedSampleImage)
class MergedSampleImageAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "subcategory",
        "condition",
        "quadrant_mapping",
        "image_preview",
        "created_at",
    )
    list_filter = ("created_at", "category", "subcategory", "condition")
    search_fields = ("category", "subcategory", "condition")
    readonly_fields = ("created_at",)

    def image_preview(self, obj):
        return format_html('<img src="{}" width="100" height="100" />', obj.image.url)

    image_preview.short_description = "Image Preview"


@admin.register(AnalysisTask)
class AnalysisTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "property",
        "status",
        "progress",
        "stage",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "stage", "created_at", "updated_at")
    search_fields = ("property__url", "stage")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("property", "status", "progress", "stage")}),
        (
            "Stage Progress",
            {
                "fields": ("stage_progress",),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def stage_progress_display(self, obj):
        if obj.stage_progress:
            return ", ".join(f"{k}: {v}" for k, v in obj.stage_progress.items())
        return "N/A"

    stage_progress_display.short_description = "Stage Progress"


def revert_to_version(modeladmin, request, queryset):
    # For each selected prompt, make that version active and deactivate others of the same name
    for prompt in queryset:
        Prompt.objects.filter(name=prompt.name).update(is_active=False)
        prompt.is_active = True
        prompt.save()


revert_to_version.short_description = "Revert selected prompts to this version"


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    actions = [revert_to_version]

    list_display = ("name", "version", "is_active", "updated_at")
    list_filter = ("name", "is_active")
    search_fields = ("name", "content")
    readonly_fields = ("version", "updated_at")

    def get_queryset(self, request):
        # Show all versions, or only active ones if desired.
        qs = super().get_queryset(request)
        return qs

    def save_model(self, request, obj, form, change):
        """
        Override save_model to implement versioning logic:
        - If it's a new object, just save it.
        - If it's an update to an existing prompt, deactivate all versions and create a new version.
        """
        if obj.pk:
            old_prompt = Prompt.objects.get(pk=obj.pk)

            # Check if content or name changed
            if old_prompt.content != obj.content or old_prompt.name != obj.name:
                with transaction.atomic():
                    # Deactivate all versions of this prompt name
                    Prompt.objects.filter(name=old_prompt.name).update(is_active=False)

                    # Find the highest version number currently in the database for this prompt name
                    max_version = (
                        Prompt.objects.filter(name=old_prompt.name).aggregate(
                            Max("version")
                        )["version__max"]
                        or 0
                    )

                    # Create a new version that is greater than any existing version number
                    obj.pk = None
                    obj.version = max_version + 1
                    obj.is_active = True
                    super().save_model(request, obj, form, False)
                return

        # If it's a new object or nothing changed, just save normally
        super().save_model(request, obj, form, change)
