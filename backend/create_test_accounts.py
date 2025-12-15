from pymongo import MongoClient
import os
import bcrypt
from uuid import uuid4
from datetime import datetime, timezone

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
client = MongoClient(MONGO_URL)
db = client[DB_NAME]

print("=" * 80)
print("Creating Test Accounts for Staff and Chef")
print("=" * 80)

# Get the customer company (restaurant)
customer_company = db.companies.find_one({"companyType": "customer"}, {"_id": 0})
if not customer_company:
    print("❌ No customer company found. Please create a customer account first.")
    exit(1)

print(f"\n✓ Found restaurant: {customer_company.get('name', customer_company['id'])}")

# Get or create a test matrix
matrix = db.matrices.find_one({"restaurantCompanyId": customer_company['id']}, {"_id": 0})
if not matrix:
    # Create a test matrix
    matrix = {
        "id": str(uuid4()),
        "name": "Основное меню",
        "restaurantCompanyId": customer_company['id'],
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    db.matrices.insert_one(matrix)
    print(f"✓ Created matrix: {matrix['name']} (ID: {matrix['id']})")
else:
    print(f"✓ Using existing matrix: {matrix['name']} (ID: {matrix['id']})")

matrix_id = matrix['id']

# Create Staff account
staff_email = "staff@bestprice.ru"
existing_staff = db.users.find_one({"email": staff_email})

if existing_staff:
    # Update existing staff account with matrix
    db.users.update_one(
        {"email": staff_email},
        {"$set": {"matrixId": matrix_id}}
    )
    print(f"\n✓ Updated existing Staff account: {staff_email}")
else:
    # Create new staff account
    hashed_pw = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt())
    staff_user = {
        "id": str(uuid4()),
        "email": staff_email,
        "passwordHash": hashed_pw.decode('utf-8'),
        "role": "responsible",
        "companyId": customer_company['id'],
        "matrixId": matrix_id,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    db.users.insert_one(staff_user)
    print(f"\n✓ Created Staff account: {staff_email}")

# Create Chef account
chef_email = "chef@bestprice.ru"
existing_chef = db.users.find_one({"email": chef_email})

if existing_chef:
    # Update existing chef account with matrix
    db.users.update_one(
        {"email": chef_email},
        {"$set": {"matrixId": matrix_id}}
    )
    print(f"✓ Updated existing Chef account: {chef_email}")
else:
    # Create new chef account
    hashed_pw = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt())
    chef_user = {
        "id": str(uuid4()),
        "email": chef_email,
        "passwordHash": hashed_pw.decode('utf-8'),
        "role": "chef",
        "companyId": customer_company['id'],
        "matrixId": matrix_id,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    db.users.insert_one(chef_user)
    print(f"✓ Created Chef account: {chef_email}")

# Add some sample products to the matrix for testing
print(f"\n📦 Adding sample products to matrix...")
existing_matrix_products = db.matrix_products.count_documents({"matrixId": matrix_id})

if existing_matrix_products == 0:
    # Get some products to add to matrix
    products = list(db.products.find({}, {"_id": 0}).limit(10))
    
    for idx, product in enumerate(products, 1):
        # Get pricelist info
        pricelist = db.pricelists.find_one({"productId": product['id']}, {"_id": 0})
        
        matrix_product = {
            "id": str(uuid4()),
            "matrixId": matrix_id,
            "rowNumber": idx,
            "productId": product['id'],
            "productName": product['name'],
            "productCode": pricelist.get('supplierItemCode', '') if pricelist else '',
            "unit": product['unit'],
            "lastOrderQuantity": None,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        db.matrix_products.insert_one(matrix_product)
    
    print(f"✓ Added {len(products)} products to matrix")
else:
    print(f"✓ Matrix already has {existing_matrix_products} products")

print("\n" + "=" * 80)
print("✅ TEST ACCOUNTS CREATED SUCCESSFULLY")
print("=" * 80)
print("\n📋 Login Credentials:\n")
print("1. STAFF Account:")
print(f"   Email: staff@bestprice.ru")
print(f"   Password: password123")
print(f"   Role: Staff (responsible)")
print(f"   Matrix: {matrix['name']}")
print()
print("2. CHEF Account:")
print(f"   Email: chef@bestprice.ru")
print(f"   Password: password123")
print(f"   Role: Chef")
print(f"   Matrix: {matrix['name']}")
print()
print("Note: Both accounts have IDENTICAL permissions:")
print("  - View assigned matrix")
print("  - Add products to matrix")
print("  - Create orders using row numbers")
print()
print("Login URL: /app/login (for mobile dashboard)")
print("=" * 80)
