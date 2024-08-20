from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from analysis.models import AnalysisTask, Property, PropertyImage
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
        print("This is the stage: ", stage)
        print("This is the message: ", message)
        print("This is the progress: ", progress)
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
        print("I am here 4")
        # Update property with results
        property_instance.overall_condition = result['Condition']
        property_instance.detailed_analysis = result['Detailed Analysis']
        await property_instance.asave()

        # # Update individual image analysis results
        # async for image in PropertyImage.objects.filter(id__in=result['Image_Analysis'].keys()):
        #     analysis = result['Image_Analysis'][str(image.id)]
        #     image.category = analysis['category']
        #     image.analysis_result = analysis['result']
        #     await image.asave()

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
