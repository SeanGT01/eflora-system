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
from .validators import (
    parse_and_validate_birthday,
    normalize_full_name,
    compose_full_name,
)
from app.cost_helpers import (
    get_realistic_margin_rate,
    calculate_realistic_cost,
)

__all__ = [
    'should_use_cloudinary',
    'delete_from_cloudinary',
    'upload_to_cloudinary',
    'upload_product_image',
    'upload_variant_image',
    'get_optimized_url',
    'parse_and_validate_birthday',
    'normalize_full_name',
    'compose_full_name',
    'get_realistic_margin_rate',
    'calculate_realistic_cost',
]