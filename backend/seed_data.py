"""
Seed data script for BestPrice platform
Creates test data: 2 suppliers, 2 restaurants, 10 products
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path
import bcrypt
from datetime import datetime, timezone
import uuid

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

async def seed_data():
    print("🌱 Starting seed data creation...")
    
    # Clear existing data
    print("Clearing existing data...")
    await db.users.delete_many({})
    await db.companies.delete_many({})
    await db.supplier_settings.delete_many({})
    await db.price_lists.delete_many({})
    await db.orders.delete_many({})
    await db.documents.delete_many({})
    
    # Create Supplier 1
    print("Creating Supplier 1: ООО Поставщик Продуктов...")
    supplier1_id = str(uuid.uuid4())
    supplier1_user = {
        "id": supplier1_id,
        "email": "supplier1@example.com",
        "passwordHash": hash_password("password123"),
        "role": "supplier",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(supplier1_user)
    
    supplier1_company_id = str(uuid.uuid4())
    supplier1_company = {
        "id": supplier1_company_id,
        "type": "supplier",
        "userId": supplier1_id,
        "inn": "7707083893",
        "ogrn": "1027700132195",
        "companyName": "ООО Поставщик Продуктов",
        "legalAddress": "г. Москва, ул. Ленина, д. 10",
        "actualAddress": "г. Москва, ул. Ленина, д. 10",
        "phone": "+7 (495) 123-45-67",
        "email": "info@supplier1.ru",
        "contactPersonName": "Иванов Иван Иванович",
        "contactPersonPosition": "Директор",
        "contactPersonPhone": "+7 (495) 123-45-68",
        "deliveryAddresses": [],
        "contractAccepted": True,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.companies.insert_one(supplier1_company)
    
    # Supplier 1 Settings
    supplier1_settings = {
        "id": str(uuid.uuid4()),
        "supplierCompanyId": supplier1_company_id,
        "minOrderAmount": 5000.0,
        "deliveryDays": ["Понедельник", "Среда", "Пятница"],
        "deliveryTime": "10:00 - 18:00",
        "orderReceiveDeadline": "16:00 предыдущего дня",
        "logisticsType": "own",
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.supplier_settings.insert_one(supplier1_settings)
    
    # Create Supplier 2
    print("Creating Supplier 2: ООО Свежие Продукты...")
    supplier2_id = str(uuid.uuid4())
    supplier2_user = {
        "id": supplier2_id,
        "email": "supplier2@example.com",
        "passwordHash": hash_password("password123"),
        "role": "supplier",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(supplier2_user)
    
    supplier2_company_id = str(uuid.uuid4())
    supplier2_company = {
        "id": supplier2_company_id,
        "type": "supplier",
        "userId": supplier2_id,
        "inn": "7702345678",
        "ogrn": "1027702345678",
        "companyName": "ООО Свежие Продукты",
        "legalAddress": "г. Москва, ул. Тверская, д. 5",
        "actualAddress": "г. Москва, ул. Тверская, д. 5",
        "phone": "+7 (495) 234-56-78",
        "email": "info@fresh-products.ru",
        "contactPersonName": "Петров Петр Петрович",
        "contactPersonPosition": "Коммерческий директор",
        "contactPersonPhone": "+7 (495) 234-56-79",
        "deliveryAddresses": [],
        "contractAccepted": True,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.companies.insert_one(supplier2_company)
    
    # Supplier 2 Settings
    supplier2_settings = {
        "id": str(uuid.uuid4()),
        "supplierCompanyId": supplier2_company_id,
        "minOrderAmount": 3000.0,
        "deliveryDays": ["Вторник", "Четверг", "Суббота"],
        "deliveryTime": "09:00 - 17:00",
        "orderReceiveDeadline": "18:00 предыдущего дня",
        "logisticsType": "transport company",
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.supplier_settings.insert_one(supplier2_settings)
    
    # Create Customer 1 (Restaurant)
    print("Creating Customer 1: ООО Ресторан Вкусно...")
    customer1_id = str(uuid.uuid4())
    customer1_user = {
        "id": customer1_id,
        "email": "restaurant1@example.com",
        "passwordHash": hash_password("password123"),
        "role": "customer",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(customer1_user)
    
    customer1_company_id = str(uuid.uuid4())
    customer1_company = {
        "id": customer1_company_id,
        "type": "customer",
        "userId": customer1_id,
        "inn": "7701234567",
        "ogrn": "1027701234567",
        "companyName": "ООО Ресторан Вкусно",
        "legalAddress": "г. Москва, ул. Пушкина, д. 20",
        "actualAddress": "г. Москва, ул. Пушкина, д. 20",
        "phone": "+7 (495) 345-67-89",
        "email": "info@vkusno-restaurant.ru",
        "contactPersonName": "Сидоров Сидор Сидорович",
        "contactPersonPosition": "Управляющий",
        "contactPersonPhone": "+7 (495) 345-67-90",
        "deliveryAddresses": ["г. Москва, ул. Пушкина, д. 20"],
        "contractAccepted": True,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.companies.insert_one(customer1_company)
    
    # Create Customer 2 (Restaurant)
    print("Creating Customer 2: ООО Кафе Столовая...")
    customer2_id = str(uuid.uuid4())
    customer2_user = {
        "id": customer2_id,
        "email": "restaurant2@example.com",
        "passwordHash": hash_password("password123"),
        "role": "customer",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(customer2_user)
    
    customer2_company_id = str(uuid.uuid4())
    customer2_company = {
        "id": customer2_company_id,
        "type": "customer",
        "userId": customer2_id,
        "inn": "7703456789",
        "ogrn": "1027703456789",
        "companyName": "ООО Кафе Столовая",
        "legalAddress": "г. Москва, ул. Арбат, д. 15",
        "actualAddress": "г. Москва, ул. Арбат, д. 15",
        "phone": "+7 (495) 456-78-90",
        "email": "info@stolovaya-cafe.ru",
        "contactPersonName": "Федоров Федор Федорович",
        "contactPersonPosition": "Директор",
        "contactPersonPhone": "+7 (495) 456-78-91",
        "deliveryAddresses": ["г. Москва, ул. Арбат, д. 15", "г. Москва, ул. Тверская, д. 30"],
        "contractAccepted": True,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    await db.companies.insert_one(customer2_company)
    
    # Create 10 products for Supplier 1
    print("Creating products for Supplier 1...")
    products_supplier1 = [
        {"productName": "Картофель", "article": "PROD-001", "price": 45.50, "unit": "кг"},
        {"productName": "Морковь", "article": "PROD-002", "price": 38.00, "unit": "кг"},
        {"productName": "Лук репчатый", "article": "PROD-003", "price": 32.00, "unit": "кг"},
        {"productName": "Капуста белокочанная", "article": "PROD-004", "price": 28.50, "unit": "кг"},
        {"productName": "Помидоры", "article": "PROD-005", "price": 120.00, "unit": "кг"},
    ]
    
    for product in products_supplier1:
        price_list = {
            "id": str(uuid.uuid4()),
            "supplierCompanyId": supplier1_company_id,
            "productName": product["productName"],
            "article": product["article"],
            "price": product["price"],
            "unit": product["unit"],
            "availability": True,
            "active": True,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }
        await db.price_lists.insert_one(price_list)
    
    # Create 5 products for Supplier 2
    print("Creating products for Supplier 2...")
    products_supplier2 = [
        {"productName": "Огурцы свежие", "article": "FRESH-001", "price": 95.00, "unit": "кг"},
        {"productName": "Перец болгарский", "article": "FRESH-002", "price": 150.00, "unit": "кг"},
        {"productName": "Салат листовой", "article": "FRESH-003", "price": 180.00, "unit": "кг"},
        {"productName": "Зелень укроп", "article": "FRESH-004", "price": 200.00, "unit": "кг"},
        {"productName": "Зелень петрушка", "article": "FRESH-005", "price": 210.00, "unit": "кг"},
    ]
    
    for product in products_supplier2:
        price_list = {
            "id": str(uuid.uuid4()),
            "supplierCompanyId": supplier2_company_id,
            "productName": product["productName"],
            "article": product["article"],
            "price": product["price"],
            "unit": product["unit"],
            "availability": True,
            "active": True,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }
        await db.price_lists.insert_one(price_list)
    
    # Create sample orders
    print("Creating sample orders...")
    order1 = {
        "id": str(uuid.uuid4()),
        "customerCompanyId": customer1_company_id,
        "supplierCompanyId": supplier1_company_id,
        "orderDate": datetime.now(timezone.utc).isoformat(),
        "amount": 5420.00,
        "status": "confirmed",
        "orderDetails": [
            {"productName": "Картофель", "article": "PROD-001", "quantity": 50, "price": 45.50, "unit": "кг"},
            {"productName": "Морковь", "article": "PROD-002", "quantity": 30, "price": 38.00, "unit": "кг"},
            {"productName": "Помидоры", "article": "PROD-005", "quantity": 20, "price": 120.00, "unit": "кг"}
        ],
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    await db.orders.insert_one(order1)
    
    order2 = {
        "id": str(uuid.uuid4()),
        "customerCompanyId": customer2_company_id,
        "supplierCompanyId": supplier2_company_id,
        "orderDate": datetime.now(timezone.utc).isoformat(),
        "amount": 3250.00,
        "status": "new",
        "orderDetails": [
            {"productName": "Огурцы свежие", "article": "FRESH-001", "quantity": 15, "price": 95.00, "unit": "кг"},
            {"productName": "Перец болгарский", "article": "FRESH-002", "quantity": 10, "price": 150.00, "unit": "кг"},
            {"productName": "Салат листовой", "article": "FRESH-003", "quantity": 5, "price": 180.00, "unit": "кг"}
        ],
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    await db.orders.insert_one(order2)
    
    print("✅ Seed data created successfully!")
    print("\n📝 Test Credentials:")
    print("=" * 50)
    print("Supplier 1:")
    print("  Email: supplier1@example.com")
    print("  Password: password123")
    print("\nSupplier 2:")
    print("  Email: supplier2@example.com")
    print("  Password: password123")
    print("\nRestaurant 1:")
    print("  Email: restaurant1@example.com")
    print("  Password: password123")
    print("\nRestaurant 2:")
    print("  Email: restaurant2@example.com")
    print("  Password: password123")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(seed_data())
