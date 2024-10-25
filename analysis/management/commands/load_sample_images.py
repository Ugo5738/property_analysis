import asyncio
import hashlib
import os

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Count

from analysis.models import MergedSampleImage, SampleImage
from utils.image_processing import compute_embedding, merge_images


def compute_image_hash(image_path):
    hasher = hashlib.md5()
    with open(image_path, "rb") as img_file:
        buf = img_file.read()
        hasher.update(buf)
    return hasher.hexdigest()


class Command(BaseCommand):
    help = "Load sample images from the categories folder into the database and create merged images"

    def handle(self, *args, **options):
        SampleImage.objects.all().delete()
        MergedSampleImage.objects.all().delete()
        self.stdout.write(
            self.style.WARNING(f"Sample images and Merged Sample image deleted")
        )

        base_path = "utils/categories"

        for category in ["external", "internal"]:
            category_path = os.path.join(base_path, category)
            for subcategory in os.listdir(category_path):
                subcategory_path = os.path.join(category_path, subcategory)
                if os.path.isdir(subcategory_path):
                    for condition in [
                        "above_average",
                        "below_average",
                        "excellent",
                        "poor",
                    ]:
                        condition_path = os.path.join(subcategory_path, condition)
                        if os.path.isdir(condition_path):
                            quadrant_mapping = {}
                            images_to_merge = []
                            for i in range(1, 5):  # Assuming 4 images per condition
                                image_filename = f"{i}.png"
                                image_path = os.path.join(
                                    condition_path, image_filename
                                )
                                if os.path.exists(image_path):
                                    with open(image_path, "rb") as img_file:
                                        image_hash = compute_image_hash(image_path)
                                        existing_image = SampleImage.objects.filter(
                                            image_hash=image_hash
                                        ).first()

                                        if existing_image:
                                            self.stdout.write(
                                                self.style.WARNING(
                                                    f"Image already exists: Category={category}, Subcategory={subcategory}, Condition={condition}, Filename={image_filename}"
                                                )
                                            )
                                            images_to_merge.append(existing_image)
                                        else:
                                            # Compute embedding
                                            embedding = compute_embedding(image_path)
                                            # Save the embedding as a list of floats
                                            embedding_data = embedding.tolist()

                                            with open(image_path, "rb") as img_file:
                                                sample_image = (
                                                    SampleImage.objects.create(
                                                        category=category,
                                                        subcategory=subcategory,
                                                        condition=condition,
                                                        image=File(
                                                            img_file,
                                                            name=image_filename,
                                                        ),
                                                        image_hash=image_hash,
                                                        embedding=embedding_data,
                                                    )
                                                )
                                            images_to_merge.append(sample_image)
                                            self.stdout.write(
                                                self.style.SUCCESS(
                                                    f"Successfully added image: {category}/{subcategory}/{condition}/{image_filename}"
                                                )
                                            )
                                        # Map quadrant to sample image ID
                                        quadrant_number = i  # Assuming images are named 1.png, 2.png, etc.
                                        quadrant_mapping[str(quadrant_number)] = (
                                            sample_image.id
                                        )
                                else:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f"Image not found: {image_path}"
                                        )
                                    )

                            # Merge images if we have 4
                            if len(images_to_merge) == 4:
                                merged_image_content = asyncio.run(
                                    merge_images(images_to_merge, condition)
                                )

                                # Create or update MergedSampleImage
                                merged_image, created = (
                                    MergedSampleImage.objects.get_or_create(
                                        category=category,
                                        subcategory=subcategory,
                                        condition=condition,
                                    )
                                )

                                # Save the merged image
                                merged_image.image.save(
                                    f"{category}_{subcategory}_{condition}_merged.jpg",
                                    ContentFile(merged_image_content),
                                    save=True,
                                )

                                # Save the quadrant mapping
                                merged_image.quadrant_mapping = quadrant_mapping
                                merged_image.save()

                                action = "Created" if created else "Updated"
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"{action} merged image for {category}/{subcategory}/{condition}"
                                    )
                                )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"Not enough images to merge for {category}/{subcategory}/{condition}. Found {len(images_to_merge)}, need 4."
                                    )
                                )

        self.stdout.write(
            self.style.SUCCESS("Sample image loading and merging completed")
        )
