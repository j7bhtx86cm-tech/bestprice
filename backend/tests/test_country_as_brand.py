"""
Тест правила "Страна = Бренд"

Если у товара в избранном указана origin_country, то:
1. brand_critical автоматически становится True
2. brand_id заменяется на название страны
3. Поиск фильтрует кандидатов по их origin_country
"""
import os
import sys
import asyncio
import uuid
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, '/app/backend')

from pymongo import MongoClient

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

def create_test_data():
    """Create test data for Country as Brand testing"""
    
    # Test user
    test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    test_user = {
        "id": test_user_id,
        "email": "test_country_brand@test.ru",
        "password": "test123",
        "name": "Test Country Brand User",
        "role": "admin",
        "companyId": "test_company",
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    db.users.insert_one(test_user)
    print(f"✅ Created test user: {test_user_id}")
    
    # Test favorites with different scenarios
    favorites = []
    
    # Scenario 1: Товар с указанной страной (РОССИЯ)
    fav1_id = f"fav_country_russia_{uuid.uuid4().hex[:8]}"
    fav1 = {
        "id": fav1_id,
        "userId": test_user_id,
        "productName": "Говядина охлажденная",
        "reference_name": "Говядина охлажденная премиум",
        "origin_country": "РОССИЯ",  # Указана страна
        "brandMode": "ANY",  # Бренд не критичен изначально
        "unit_norm": "kg",
        "pack_size": 1.0,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    db.favorites.insert_one(fav1)
    favorites.append(fav1_id)
    print(f"✅ Created favorite with country РОССИЯ: {fav1_id}")
    
    # Scenario 2: Товар с указанной страной (АРГЕНТИНА)
    fav2_id = f"fav_country_argentina_{uuid.uuid4().hex[:8]}"
    fav2 = {
        "id": fav2_id,
        "userId": test_user_id,
        "productName": "Говядина импортная",
        "reference_name": "Говядина импортная премиум",
        "origin_country": "Аргентина",  # Указана страна (lowercase)
        "brandMode": "ANY",
        "unit_norm": "kg",
        "pack_size": 1.0,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    db.favorites.insert_one(fav2)
    favorites.append(fav2_id)
    print(f"✅ Created favorite with country Аргентина: {fav2_id}")
    
    # Scenario 3: Товар без страны (стандартная логика)
    fav3_id = f"fav_no_country_{uuid.uuid4().hex[:8]}"
    fav3 = {
        "id": fav3_id,
        "userId": test_user_id,
        "productName": "Говядина",
        "reference_name": "Говядина премиум",
        "brandMode": "ANY",  # Обычный режим
        "unit_norm": "kg",
        "pack_size": 1.0,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    db.favorites.insert_one(fav3)
    favorites.append(fav3_id)
    print(f"✅ Created favorite without country: {fav3_id}")
    
    # Scenario 4: Товар со страной И брендом
    fav4_id = f"fav_country_and_brand_{uuid.uuid4().hex[:8]}"
    fav4 = {
        "id": fav4_id,
        "userId": test_user_id,
        "productName": "Молоко из России",
        "reference_name": "Молоко 3.2%",
        "origin_country": "РОССИЯ",
        "brand_id": "ПРОСТОКВАШИНО",  # Бренд указан
        "brandMode": "STRICT",  # Бренд критичен
        "unit_norm": "l",
        "pack_size": 1.0,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    db.favorites.insert_one(fav4)
    favorites.append(fav4_id)
    print(f"✅ Created favorite with country AND brand: {fav4_id}")
    
    return test_user_id, favorites


def check_supplier_items_with_countries():
    """Check what countries exist in supplier_items"""
    pipeline = [
        {"$match": {"active": True, "origin_country": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$origin_country", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 20}
    ]
    
    results = list(db.supplier_items.aggregate(pipeline))
    print("\n📊 Страны в supplier_items (active):")
    for r in results:
        print(f"   {r['_id']}: {r['count']} товаров")
    
    return results


def cleanup_test_data(test_user_id: str, favorites: list):
    """Remove test data"""
    db.users.delete_one({"id": test_user_id})
    for fav_id in favorites:
        db.favorites.delete_one({"id": fav_id})
    print(f"\n🗑️ Cleaned up test data")


if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТ: Правило 'Страна = Бренд'")
    print("=" * 60)
    
    # Check existing countries
    countries = check_supplier_items_with_countries()
    
    if not countries:
        print("\n⚠️ В базе нет товаров с указанной страной!")
        print("   Тест может не дать результатов")
    
    # Create test data
    print("\n" + "=" * 60)
    test_user_id, favorites = create_test_data()
    
    print("\n" + "=" * 60)
    print("📝 Тестовые данные созданы. Используйте API для тестирования:")
    print(f"   User ID: {test_user_id}")
    print(f"   Favorites: {favorites}")
    print("\nОжидаемое поведение:")
    print("1. Favorite с country='РОССИЯ' → brand_critical=True, фильтр по стране")
    print("2. Favorite с country='Аргентина' → brand_critical=True, фильтр по стране (UPPERCASE)")
    print("3. Favorite без страны → стандартная логика бренда")
    print("4. Favorite со страной И брендом → страна переопределяет бренд!")
    
    # Cleanup prompt
    print("\n" + "=" * 60)
    cleanup = input("Удалить тестовые данные? (y/n): ")
    if cleanup.lower() == 'y':
        cleanup_test_data(test_user_id, favorites)
