#!/usr/bin/env node
/**
 * Добавляет тестовый ресторан (restaurant1@example.com) в список ресторанов
 * тестового поставщика (supplier1@example.com) на странице /supplier/restaurants.
 *
 * Источник данных: supplier_restaurant_settings
 * Query: { supplierId: <supplier_company_id>, contract_accepted: true }
 */
import { MongoClient } from 'mongodb';
import { config } from 'dotenv';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: join(__dirname, '..', '.env') });

const MONGO_URL = process.env.MONGO_URL || 'mongodb://localhost:27017';
const DB_NAME = process.env.DB_NAME || 'test_database';

const RESTAURANT_USER_EMAIL = 'restaurant1@example.com';
const SUPPLIER_USER_EMAIL = 'supplier1@example.com';
const SUPPLIER_COMPANY_EMAIL = 'info@supplier1.ru';
const COLLECTION = 'supplier_restaurant_settings';

async function main() {
  const client = new MongoClient(MONGO_URL);
  await client.connect();
  const db = client.db(DB_NAME);

  // 2) Найти тестовый ресторан
  const restaurantUser = await db.collection('users').findOne({ email: RESTAURANT_USER_EMAIL });
  if (!restaurantUser) {
    console.error('Restaurant user not found (email=restaurant1@example.com)');
    process.exit(1);
  }
  const restaurantCompany = await db.collection('companies').findOne({
    userId: restaurantUser.id,
    type: 'customer',
  });
  if (!restaurantCompany) {
    console.error('Restaurant company not found for user restaurant1@example.com');
    process.exit(1);
  }
  const restaurant_company_id = restaurantCompany.id;

  // 3) Найти тестового поставщика
  let supplierUser = await db.collection('users').findOne({ email: SUPPLIER_USER_EMAIL });
  if (!supplierUser) {
    const supComp = await db.collection('companies').findOne({ email: SUPPLIER_COMPANY_EMAIL, type: 'supplier' });
    if (supComp) supplierUser = await db.collection('users').findOne({ id: supComp.userId });
  }
  if (!supplierUser) {
    supplierUser = await db.collection('users').findOne({ role: 'supplier' });
  }
  if (!supplierUser) {
    console.error('Supplier user not found');
    process.exit(1);
  }
  const supplierCompany = await db.collection('companies').findOne({
    userId: supplierUser.id,
    type: 'supplier',
  });
  if (!supplierCompany) {
    console.error('Supplier company not found');
    process.exit(1);
  }
  const supplier_company_id = supplierCompany.id;

  // 4) Upsert в supplier_restaurant_settings (источник supplier/restaurants)
  const now = new Date();
  const filter = { supplierId: supplier_company_id, restaurantId: restaurant_company_id };
  const update = {
    $set: {
      supplierId: supplier_company_id,
      restaurantId: restaurant_company_id,
      contract_accepted: true,
      is_paused: false,
      ordersEnabled: true,
      updatedAt: now.toISOString(),
    },
    $setOnInsert: {
      id: randomUUID(),
      createdAt: now.toISOString(),
    },
  };

  const result = await db.collection(COLLECTION).updateOne(filter, update, { upsert: true });

  const doc = await db.collection(COLLECTION).findOne(filter);

  // 5) Вывод
  console.log('supplier_company_id', supplier_company_id);
  console.log('restaurant_company_id', restaurant_company_id);
  console.log('collection', COLLECTION);
  console.log('result:', {
    supplierId: doc?.supplierId,
    restaurantId: doc?.restaurantId,
    contract_accepted: doc?.contract_accepted,
    is_paused: doc?.is_paused,
    ordersEnabled: doc?.ordersEnabled,
    matched: result.matchedCount,
    modified: result.modifiedCount,
    upserted: result.upsertedCount,
  });

  await client.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
