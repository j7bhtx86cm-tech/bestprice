#!/usr/bin/env node
/**
 * Force accept: создаёт/обновляет допуск ресторана у тестового поставщика.
 * Данные зашиты: inn 7707083893, email info@supplier1.ru, restaurant1@example.com
 */
import { MongoClient } from 'mongodb';
import { config } from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: join(__dirname, '..', '.env') });

const MONGO_URL = process.env.MONGO_URL || 'mongodb://localhost:27017';
const DB_NAME = process.env.DB_NAME || 'test_database';

const SUPPLIER_INN = '7707083893';
const SUPPLIER_EMAIL = 'info@supplier1.ru';
const RESTAURANT_USER_EMAIL = 'restaurant1@example.com';

async function main() {
  const client = new MongoClient(MONGO_URL);
  await client.connect();
  const db = client.db(DB_NAME);

  const supplier = await db.collection('companies').findOne({
    $or: [
      { inn: SUPPLIER_INN },
      { email: SUPPLIER_EMAIL },
    ],
    type: 'supplier',
  });

  if (!supplier) {
    console.error('Supplier not found (inn=7707083893 or email=info@supplier1.ru)');
    process.exit(1);
  }

  const user = await db.collection('users').findOne({ email: RESTAURANT_USER_EMAIL });
  if (!user) {
    console.error('Restaurant user not found (email=restaurant1@example.com)');
    process.exit(1);
  }

  const restaurant = await db.collection('companies').findOne({
    userId: user.id,
    type: 'customer',
  });

  if (!restaurant) {
    console.error('Restaurant company not found for user restaurant1@example.com');
    process.exit(1);
  }

  const supplier_id = supplier.id;
  const restaurant_id = restaurant.id;
  const status = 'ACCEPTED';
  const now = new Date();

  await db.collection('supplier_restaurant_settings').updateOne(
    {
      supplierId: supplier_id,
      restaurantId: restaurant_id,
    },
    {
      $set: {
        supplierId: supplier_id,
        restaurantId: restaurant_id,
        contract_accepted: true,
        is_paused: false,
        status,
        updated_at: now,
        updatedAt: now.toISOString(),
      },
      $setOnInsert: {
        created_at: now,
      },
    },
    { upsert: true }
  );

  console.log('LINK CREATED OR UPDATED');
  console.log('supplier_id', supplier_id);
  console.log('restaurant_id', restaurant_id);
  console.log('status', status);

  await client.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
