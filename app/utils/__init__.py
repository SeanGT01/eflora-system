# app/utils/__init__.py
# This file makes the utils directory a Python package
from .cloudinary_helper import (
    should_use_cloudinary,
    delete_from_cloudinary,
    upload_to_cloudinary,
    upload_product_image,
    upload_variant_image,
    get_optimized_url
)

__all__ = [
    'should_use_cloudinary',
    'delete_from_cloudinary',
    'upload_to_cloudinary',
    'upload_product_image',
    'upload_variant_image',
    'get_optimized_url'
]