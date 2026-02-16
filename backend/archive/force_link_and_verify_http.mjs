#!/usr/bin/env node
/**
 * Жёсткий автотест-фикс: связка supplier↔restaurant и строгая проверка,
 * что restaurant1@example.com появляется в GET /api/supplier/restaurants.
 * IDs берутся ТОЛЬКО из API (как UI), не из Mongo.
 * Exit(1) при любой ошибке верификации.
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
const BASE_URL = (process.env.BACKEND_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const TEST_SUPPLIER_EMAIL = process.env.TEST_SUPPLIER_EMAIL || 'supplier1@example.com';
const TEST_SUPPLIER_PASSWORD = process.env.TEST_SUPPLIER_PASSWORD || 'password123';
const TEST_RESTAURANT_EMAIL = process.env.TEST_RESTAURANT_EMAIL || 'restaurant1@example.com';
const COLLECTION = 'supplier_restaurant_settings';

async function login(email, password) {
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Login failed ${res.status}: ${t?.slice(0, 300)}`);
  }
  const data = await res.json();
  return data.access_token;
}

async function authMe(token) {
  const res = await fetch(`${BASE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`/auth/me failed ${res.status}`);
  const data = await res.json();
  const companyId = data.companyId;
  if (!companyId) throw new Error(`/auth/me returned no companyId for ${data.email}`);
  return companyId;
}

async function getSupplierRestaurants(token) {
  const res = await fetch(`${BASE_URL}/api/supplier/restaurants`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET /api/supplier/restaurants failed ${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}

function fail(msg, extra = {}) {
  console.error('VERIFY FAILED:', msg);
  Object.entries(extra).forEach(([k, v]) => console.error(k + ':', typeof v === 'object' ? JSON.stringify(v, null, 2) : v));
  process.exit(1);
}

async function main() {
  // A) Supplier login + /auth/me → supplier_company_id (только из API)
  const supplierToken = await login(TEST_SUPPLIER_EMAIL, TEST_SUPPLIER_PASSWORD);
  const supplier_company_id = await authMe(supplierToken);

  // B) Restaurant (customer) login + /auth/me → restaurant_company_id (только из API)
  const restaurantToken = await login(TEST_RESTAURANT_EMAIL, TEST_SUPPLIER_PASSWORD);
  const restaurant_company_id = await authMe(restaurantToken);

  // Verify-0: BEFORE (до upsert)
  const BEFORE = await getSupplierRestaurants(supplierToken);
  const beforeIds = BEFORE.map((r) => r.id);
  const beforeInns = BEFORE.map((r) => r.inn).filter(Boolean);
  const alreadyHad = beforeIds.includes(restaurant_company_id) || beforeInns.some((inn) => {
    const r = BEFORE.find((x) => x.inn === inn);
    return r && r.id === restaurant_company_id;
  });

  // C) Mongo: upsert link + подтянуть поля коллекции
  const client = new MongoClient(MONGO_URL);
  await client.connect();
  const db = client.db(DB_NAME);

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
  await db.collection(COLLECTION).updateOne(filter, update, { upsert: true });

  // D) Если company ресторана без name/inn/type — заполнить тестовыми
  const restaurantCompany = await db.collection('companies').findOne({ id: restaurant_company_id });
  if (restaurantCompany) {
    const needs = [];
    if (!restaurantCompany.companyName && !restaurantCompany.name) needs.push('companyName');
    if (!restaurantCompany.inn) needs.push('inn');
    if (!restaurantCompany.type) needs.push('type');
    if (needs.length) {
      const patch = {};
      if (needs.includes('companyName')) patch.companyName = 'ООО Ресторан Тест';
      if (needs.includes('inn')) patch.inn = '7700000000';
      if (needs.includes('type')) patch.type = 'customer';
      patch.updatedAt = now.toISOString();
      await db.collection('companies').updateOne({ id: restaurant_company_id }, { $set: patch });
    }
  }

  // Verify-1: Mongo — документ с restaurantId есть
  const mongoFilter = { supplierId: supplier_company_id, contract_accepted: true };
  const links = await db.collection(COLLECTION).find(mongoFilter).limit(50).toArray();
  const hasLink = links.some((l) => (l.restaurantId || l.restaurant_id) === restaurant_company_id);
  if (!hasLink) {
    await client.close();
    fail('Verify-1: document with restaurantId not found in Mongo', {
      mongoFilter,
      restaurant_company_id,
      'links_sample (20)': links.slice(0, 20).map((l) => ({
        supplierId: l.supplierId ?? l.supplier_id,
        restaurantId: l.restaurantId ?? l.restaurant_id,
        contract_accepted: l.contract_accepted,
      })),
    });
  }

  await client.close();

  // Verify-2: HTTP после upsert
  const AFTER = await getSupplierRestaurants(supplierToken);

  const found = AFTER.find((r) => r.id === restaurant_company_id);
  const cond1 = !!found;
  const cond2 = alreadyHad || AFTER.length === BEFORE.length + 1;
  const cond3 = found && (found.name && found.name !== 'N/A') && (found.inn != null && found.inn !== '');

  if (!cond1) {
    fail('Verify-2(1): restaurant_company_id not in API response', {
      restaurant_company_id,
      before_count: BEFORE.length,
      after_count: AFTER.length,
      after_ids: AFTER.map((r) => r.id),
      full_after: JSON.stringify(AFTER, null, 2),
    });
  }
  if (!cond2) {
    fail('Verify-2(2): count mismatch (expected BEFORE+1 or already existed)', {
      before_count: BEFORE.length,
      after_count: AFTER.length,
      alreadyHad,
      full_before: JSON.stringify(BEFORE, null, 2),
      full_after: JSON.stringify(AFTER, null, 2),
    });
  }
  if (!cond3) {
    fail('Verify-2(3): restaurant object missing name or inn', {
      found: JSON.stringify(found, null, 2),
      full_after: JSON.stringify(AFTER, null, 2),
    });
  }

  const added = !alreadyHad;
  console.log('OK VERIFIED');
  console.log('supplier_company_id=' + supplier_company_id);
  console.log('restaurant_company_id=' + restaurant_company_id);
  console.log('before_count=' + BEFORE.length);
  console.log('after_count=' + AFTER.length);
  console.log('added=' + added);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
