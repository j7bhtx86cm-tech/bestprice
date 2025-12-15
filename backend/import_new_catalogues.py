import pandas as pd
import requests
from io import BytesIO
import json
from pymongo import MongoClient
import os
from datetime import datetime, timezone

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = MongoClient(MONGO_URL)
db = client['bestprice']

# Download and process Excel files
catalogues = {
    'Айфрут': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/bjvh1y8b_%D0%90%D0%B8%CC%86%D1%84%D1%80%D1%83%D1%82-2.xlsx',
    'Алиди': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/coufww7q_%D0%90%D0%BB%D0%B8%D0%B4%D0%B8-3.xlsx',
    'Восток-Запад': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/2442oi0r_%D0%92%D0%BE%D1%81%D1%82%D0%BE%D0%BA-%D0%97%D0%B0%D0%BF%D0%B0%D0%B4.xlsx',
    'Интегрита': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/rq6d8ihy_%D0%98%D0%BD%D1%82%D0%B5%D0%B3%D1%80%D0%B8%D1%82%D0%B0-3.xlsx',
    'Нордико': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/van2n8wi_%D0%9D%D0%BE%D1%80%D0%B4%D0%B8%D0%BA%D0%BE.xlsx',
    'ПраймФудс': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/vtuc5uf2_%D0%9F%D1%80%D0%B0%D0%B8%CC%86%D0%BC%D0%A4%D1%83%D0%B4%D1%81-3.xlsx',
    'РБД': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/dpo9ci7q_%D0%A0%D0%91%D0%94.xlsx'
}

print("=" * 80)
print("ANALYZING ALL CATALOGUE FILES")
print("=" * 80)

for supplier_name, url in catalogues.items():
    print(f"\n📁 Processing: {supplier_name}")
    print(f"URL: {url}")
    
    try:
        # Download the file
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Read Excel file
        df = pd.read_excel(BytesIO(response.content))
        
        print(f"✅ Successfully loaded")
        print(f"   Rows: {len(df)}")
        print(f"   Columns: {list(df.columns)}")
        print(f"\n   First 3 rows:")
        print(df.head(3).to_string())
        print("\n" + "-" * 80)
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("-" * 80)

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
