# import_laguna_municipalities.py
import json
import os
import sys
from app import create_app, db
from app.models import MunicipalityBoundary
from geoalchemy2.shape import from_shape
from shapely.geometry import shape, Polygon, MultiPolygon

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def ensure_multipolygon(geom):
    """Convert Polygon to MultiPolygon if needed"""
    if geom.geom_type == 'Polygon':
        return MultiPolygon([geom])
    return geom

app = create_app()
with app.app_context():
    print("🗺️ Importing Laguna municipality boundaries...")
    
    # Clear existing data
    MunicipalityBoundary.query.delete()
    db.session.commit()
    print("✅ Cleared existing boundaries")
    
    # Path to the medium resolution GeoJSON file
    geojson_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'philippines-json-maps', '2011', 'geojson', 'municties', 'medres',
        'municities-province-40-laguna.0.01.json'
    )
    
    # If medres doesn't exist, try lowres
    if not os.path.exists(geojson_file):
        geojson_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'philippines-json-maps', '2011', 'geojson', 'municties', 'lowres',
            'municities-province-40-laguna.0.001.json'
        )
    
    if not os.path.exists(geojson_file):
        print(f"❌ File not found: {geojson_file}")
        exit(1)
    
    print(f"📂 Reading {geojson_file}")
    
    with open(geojson_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    count = 0
    municipalities = []
    
    # Process each feature
    for feature in data['features']:
        props = feature.get('properties', {})
        geometry = feature.get('geometry', {})
        
        # Skip if not a polygon/multipolygon
        if geometry.get('type') not in ['Polygon', 'MultiPolygon']:
            continue
        
        # Extract municipality name
        name = (props.get('NAME_2') or props.get('name') or 
                props.get('municipality') or 'Unknown')
        
        # All features in this file are from Laguna province
        province = "Laguna"
        
        try:
            # Convert to Shapely geometry
            geom = shape(geometry)
            
            # Convert to MultiPolygon if it's a Polygon
            geom = ensure_multipolygon(geom)
            
            # Calculate bounding box
            bounds = geom.bounds  # (minx, miny, maxx, maxy)
            
            # Create boundary record
            boundary = MunicipalityBoundary(
                name=name.strip(),
                province=province,
                boundary=from_shape(geom, srid=4326),
                min_lat=bounds[1],
                max_lat=bounds[3],
                min_lng=bounds[0],
                max_lng=bounds[2]
            )
            
            db.session.add(boundary)
            count += 1
            municipalities.append(name)
            print(f"  ✅ {name}")
            
        except Exception as e:
            print(f"  ⚠️ Error processing {name}: {e}")
    
    db.session.commit()
    print(f"\n✅ Imported {count} municipalities in Laguna")
    print(f"\n📋 Municipalities imported:")
    for muni in sorted(municipalities):
        print(f"   - {muni}")
    
    # Verify the import
    total_in_db = MunicipalityBoundary.query.count()
    laguna_in_db = MunicipalityBoundary.query.filter(
        MunicipalityBoundary.province.ilike('%laguna%')
    ).count()
    
    print(f"\n📊 Verification:")
    print(f"   Total in database: {total_in_db}")
    print(f"   Laguna in database: {laguna_in_db}")