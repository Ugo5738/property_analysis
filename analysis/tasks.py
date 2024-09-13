from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from analysis.models import AnalysisTask, Property, PropertyImage, GroupedImages, MergedPropertyImage
from utils.image_processing import download_images
from utils.property_analysis import process_property


@shared_task
def analyze_property(property_id, task_id, user_id):
    async_to_sync(analyze_property_async)(property_id, task_id, user_id)

async def analyze_property_async(property_id, task_id, user_id):
    channel_layer = get_channel_layer()
    property_instance = await Property.objects.aget(id=property_id)
    task_instance = await AnalysisTask.objects.aget(id=task_id)

    async def update_progress(stage, message, progress):
        task_instance.status = stage
        task_instance.progress = progress
        task_instance.stage = stage
        task_instance.stage_progress[stage] = progress
        await task_instance.asave()
        await channel_layer.group_send(
            f"analysis_{user_id}",
            {
                'type': 'analysis_progress',
                'message': {
                    'stage': stage,
                    'message': message,
                    'progress': progress
                }
            }
        )

    try:
        # Download images
        await update_progress('download', 'Downloading images', 0)
        image_ids, failed_downloads = await download_images(property_instance, update_progress)
        property_instance.failed_downloads = failed_downloads
        await property_instance.asave()

        # Process property
        result = await process_property(property_instance.url, image_ids, update_progress)

        # Update property with results
        property_instance.overall_condition = result['Condition']
        property_instance.detailed_analysis = result['Detailed Analysis']
        property_instance.overall_analysis = result['Overall Analysis']
        await property_instance.asave()

        task_instance.status = 'COMPLETED'
        task_instance.progress = 100.0
        await task_instance.asave()

        await update_progress('complete', 'Analysis completed successfully', 100.0)
    except Exception as e:
        await update_progress('error', f'Error during analysis: {str(e)}', 0.0)
        task_instance.status = 'ERROR'
        await task_instance.asave()
        property_instance.overall_condition = {'error': str(e)}
        await property_instance.asave()


def clear_property_data(property_instance):
    # Delete associated PropertyImage objects
    PropertyImage.objects.filter(property=property_instance).delete()

    # Delete associated GroupedImages objects
    GroupedImages.objects.filter(property=property_instance).delete()

    # Delete associated MergedPropertyImage objects
    MergedPropertyImage.objects.filter(property=property_instance).delete()

    # Delete associated AnalysisTask objects
    AnalysisTask.objects.filter(property=property_instance).delete()

    # Clear analysis results and reset fields
    property_instance.overall_condition = None
    property_instance.detailed_analysis = None
    property_instance.failed_downloads = []
    property_instance.image_urls = []
    property_instance.save()
