from geoalchemy2.functions import ST_Contains, ST_Distance, ST_GeomFromText, ST_SetSRID
from geoalchemy2.shape import to_shape, from_shape
from sqlalchemy import func
import math

def is_within_delivery_area(lat, lng, store_id):
    """
    Check if a point is within store's delivery area polygon
    """
    from app.models import db, Store
    
    point = f'POINT({lng} {lat})'
    
    # Using PostGIS ST_Contains function
    result = db.session.query(
        Store.id
    ).filter(
        Store.id == store_id,
        ST_Contains(
            Store.delivery_area,
            ST_GeomFromText(point, 4326)
        )
    ).first()
    
    return result is not None

def calculate_distance(lat1, lng1, lat2, lng2):
    """
    Calculate distance between two points in kilometers
    Using Haversine formula
    """
    # Convert degrees to radians
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of earth in kilometers
    
    return c * r

def get_nearby_stores(lat, lng, radius_km=10, limit=20):
    """
    Get stores within a certain radius of a point
    """
    from app.models import db, Store
    
    point = f'POINT({lng} {lat})'
    
    # Using PostGIS ST_Distance function
    stores = db.session.query(
        Store,
        (ST_Distance(
            Store.location,
            ST_GeomFromText(point, 4326)
        ) / 1000).label('distance_km')  # Convert meters to km
    ).filter(
        Store.status == 'active',
        ST_Distance(
            Store.location,
            ST_GeomFromText(point, 4326)
        ) <= (radius_km * 1000)  # Convert km to meters
    ).order_by('distance_km').limit(limit).all()
    
    return stores

def create_delivery_polygon(center_lat, center_lng, radius_km):
    """
    Create a circular polygon for delivery area
    Returns WKT polygon string
    """
    # Generate points in a circle around center
    points = []
    num_points = 32  # Number of points to approximate circle
    
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        # Calculate point at given distance and angle
        dx = radius_km * math.cos(angle) / 111.32  # 1 degree latitude ≈ 111.32 km
        dy = radius_km * math.sin(angle) / (111.32 * math.cos(math.radians(center_lat)))
        
        point_lat = center_lat + dx
        point_lng = center_lng + dy
        points.append(f"{point_lng} {point_lat}")
    
    # Close the polygon
    points.append(points[0])
    
    polygon_wkt = f"POLYGON(({', '.join(points)}))"
    return polygon_wkt