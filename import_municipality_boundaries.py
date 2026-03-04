#!/usr/bin/env python3
"""
Import municipality boundaries from GitHub repo
Run: flask shell -c "exec(open('app/scripts/import_municipality_boundaries.py').read())"
"""

import json
import os
from app import create_app, db
from app.models import MunicipalityBoundary
from geoalchemy2.shape import from_shape
from shapely.geometry import shape

app = create_app()
with app.app_context():
    print("🗺️ Importing municipality boundaries...")
    
    # Clear existing data
    MunicipalityBoundary.query.delete()
    db.session.commit()
    print("✅ Cleared existing boundaries")
    
    # Path to the cloned repo
    repo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                             'philippines-json-maps', 'geojson')
    
    # Use medium resolution for good balance
    geojson_file = os.path.join(repo_path, 'philippines_province_city_municipality_medium.geojson')
    
    if not os.path.exists(geojson_file):
        print(f"❌ File not found: {geojson_file}")
        print("Please make sure you've cloned the repo correctly")
        exit(1)
    
    print(f"📂 Reading {geojson_file}")
    
    with open(geojson_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    count = 0
    laguna_count = 0
    
    for feature in data['features']:
        props = feature['properties']
        geometry = feature['geometry']
        
        # Only import municipalities (not provinces, regions)
        if geometry['type'] not in ['Polygon', 'MultiPolygon']:
            continue
        
        # Get name - adjust field names based on actual data
        name = props.get('name') or props.get('NAME_2') or props.get('municipality')
        province = props.get('province') or props.get('NAME_1') or props.get('ADM1_EN')
        region = props.get('region') or props.get('REGION')
        psgc = props.get('psgc') or props.get('ID_2') or props.get('code')
        
        if not name:
            continue
        
        # Convert to Shapely geometry
        geom = shape(geometry)
        
        # Create boundary record
        boundary = MunicipalityBoundary(
            name=name.strip(),
            province=province.strip() if province else None,
            region=region.strip() if region else None,
            psgc_code=str(psgc) if psgc else None,
            boundary=from_shape(geom, srid=4326)
        )
        
        db.session.add(boundary)
        count += 1
        
        # Track Laguna municipalities
        if province and 'laguna' in province.lower():
            laguna_count += 1
            print(f"  ✅ Laguna: {name}")
    
    db.session.commit()
    print(f"\n✅ Imported {count} total municipalities")
    print(f"✅ Found {laguna_count} municipalities in Laguna")
    
    # Verify adjacency for Laguna
    print("\n🔍 Testing adjacency for Laguna municipalities:")
    from app.laguna_addresses import get_municipalities
    
    laguna_munis = get_municipalities()
    for muni in laguna_munis[:5]:  # Test first 5
        adjacent = MunicipalityBoundary.get_adjacent_municipalities(muni)
        if adjacent:
            print(f"  {muni} touches: {', '.join(adjacent[:3])}...")