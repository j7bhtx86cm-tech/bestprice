from pymongo import MongoClient
import os

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
client = MongoClient(MONGO_URL)
db = client[DB_NAME]

print("=" * 80)
print("Updating Test Accounts with Full Details")
print("=" * 80)

# Update Staff account
staff_update = db.users.update_one(
    {"email": "staff@bestprice.ru"},
    {"$set": {
        "name": "Мария Соколова",
        "phone": "+7 (999) 555-11-22"
    }}
)

if staff_update.matched_count > 0:
    print("\n✅ Staff account updated:")
    print("   Name: Мария Соколова")
    print("   Phone: +7 (999) 555-11-22")
    print("   Email: staff@bestprice.ru")
else:
    print("\n❌ Staff account not found")

# Update Chef account
chef_update = db.users.update_one(
    {"email": "chef@bestprice.ru"},
    {"$set": {
        "name": "Алексей Петров",
        "phone": "+7 (999) 777-33-44"
    }}
)

if chef_update.matched_count > 0:
    print("\n✅ Chef account updated:")
    print("   Name: Алексей Петров")
    print("   Phone: +7 (999) 777-33-44")
    print("   Email: chef@bestprice.ru")
else:
    print("\n❌ Chef account not found")

print("\n" + "=" * 80)
print("✅ Test accounts updated with full details!")
print("=" * 80)
