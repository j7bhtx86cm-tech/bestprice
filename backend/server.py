from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import hashlib
import secrets
import re
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any, Annotated, Union
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import pandas as pd
import io
from enum import Enum
import os

# P0: Unit normalization
from unit_normalizer import (
    parse_pack_from_text,
    calculate_packs_needed,
    format_pack_explanation,
    calculate_pack_penalty,
    UnitType,
    PackInfo,
)

# P1: Rules Validation at startup
from rules_validator import validate_all_rules, print_validation_report

# Build info for debugging
ROOT_DIR = Path(__file__).parent
BUILD_SHA = os.popen(f"cd {ROOT_DIR} && git rev-parse --short HEAD 2>/dev/null").read().strip() or "unknown"
BUILD_TIME = datetime.now(timezone.utc).isoformat()

load_dotenv(ROOT_DIR / '.env')

# MongoDB connection (env overrides .env; defaults for local dev only)
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'bestprice_local')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# JWT Configuration
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
SKIP_RULES_VALIDATION = os.environ.get('BESTPRICE_SKIP_RULES_VALIDATION', '').strip().lower() in {'1', 'true', 'yes', 'on'}

# Create the main app
app = FastAPI(title="BestPrice API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer()

# File upload directory
UPLOAD_DIR = ROOT_DIR / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

# ==================== ENUMS ====================
class UserRole(str, Enum):
    supplier = "supplier"
    customer = "customer"
    admin = "admin"
    responsible = "responsible"
    chef = "chef"

class CompanyType(str, Enum):
    supplier = "supplier"
    customer = "customer"

class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    verified = "verified"
    rejected = "rejected"

class OrderStatus(str, Enum):
    new = "new"
    confirmed = "confirmed"
    declined = "declined"
    partial = "partial"

# ==================== MATRIX MODELS ====================

# Matrix Mode Enum
class MatrixMode(str, Enum):
    EXACT = "exact"  # Fixed supplier product
    CHEAPEST = "cheapest"  # Auto-select cheapest from all suppliers

class Matrix(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    restaurantCompanyId: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MatrixCreate(BaseModel):
    name: str
    restaurantCompanyId: str

class MatrixProduct(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    matrixId: str
    rowNumber: int
    productId: str
    productName: str  # Can be customized locally
    productCode: str
    unit: str
    mode: str = "exact"  # "exact" or "cheapest"
    # Product Intent fields (for CHEAPEST mode)
    productType: Optional[str] = None
    baseUnit: Optional[str] = None
    keyAttributes: Optional[Dict[str, Any]] = None
    brand: Optional[str] = None
    strictBrand: bool = False
    lastOrderQuantity: Optional[float] = None
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MatrixProductCreate(BaseModel):
    productId: str
    productName: Optional[str] = None  # If not provided, use global product name
    productCode: Optional[str] = None
    mode: str = "exact"  # "exact" or "cheapest"

class MatrixProductUpdate(BaseModel):
    productName: Optional[str] = None
    lastOrderQuantity: Optional[float] = None

# Favorites Models
class Favorite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    userId: str
    companyId: str
    productId: str
    productName: str
    productCode: str
    unit: str
    isBranded: bool = False  # NEW: Is this a branded product?
    brandMode: str = "STRICT"  # NEW: "STRICT" or "ANY"
    brand: Optional[str] = None  # NEW: Brand name if isBranded=True
    originalSupplierId: Optional[str] = None  # Store which supplier user selected it from
    addedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FavoriteCreate(BaseModel):
    productId: str
    supplierId: Optional[str] = None  # Which supplier this was from

class FavoriteUpdateMode(BaseModel):
    mode: str  # "exact" or "cheapest"

class MatrixOrderCreate(BaseModel):
    matrixId: str
    deliveryAddressId: Optional[str] = None
    items: List[dict]  # [{"rowNumber": 1, "quantity": 5}, ...]

# Supplier-Restaurant Settings (link supplier↔restaurant, contract + pause)
class SupplierRestaurantSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    supplierId: str
    restaurantId: str
    contract_accepted: bool = False
    is_paused: bool = False
    ordersEnabled: bool = True
    unavailabilityReason: Optional[str] = None
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UpdateRestaurantAvailability(BaseModel):
    ordersEnabled: bool
    unavailabilityReason: Optional[str] = None

class RestaurantPauseBody(BaseModel):
    is_paused: bool

class LogisticsType(str, Enum):
    own = "own"
    transport_company = "transport company"

# ==================== MODELS ====================

# User Models
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    passwordHash: str
    role: UserRole
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: UserRole

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

# Delivery Address Model
class DeliveryAddress(BaseModel):
    address: str
    phone: Optional[str] = ""
    additionalPhone: Optional[str] = None

# Company Models
class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: CompanyType
    userId: str
    inn: str
    ogrn: str
    companyName: str
    legalAddress: str
    actualAddress: str
    phone: str
    email: EmailStr
    contactPersonName: Optional[str] = None
    contactPersonPosition: Optional[str] = None
    contactPersonPhone: Optional[str] = None
    deliveryAddresses: Optional[List[DeliveryAddress]] = []
    edoNumber: Optional[str] = None  # Номер ЭДО (electronic document exchange)
    guid: Optional[str] = None  # GUID for document exchange
    contractAccepted: bool = False
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CompanyCreate(BaseModel):
    type: CompanyType
    inn: str
    companyName: str
    legalAddress: str
    actualAddress: str
    phone: str
    email: EmailStr
    contactPersonName: Optional[str] = None
    contactPersonPosition: Optional[str] = None
    contactPersonPhone: Optional[str] = None
    deliveryAddresses: Optional[List[DeliveryAddress]] = []
    contractAccepted: bool = False

class CompanyUpdate(BaseModel):
    actualAddress: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    contactPersonName: Optional[str] = None
    contactPersonPhone: Optional[str] = None
    deliveryAddresses: Optional[List[DeliveryAddress]] = None
    edoNumber: Optional[str] = None
    guid: Optional[str] = None

# Document Models
class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    companyId: str
    type: str
    fileUrl: str
    status: DocumentStatus = DocumentStatus.uploaded
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# SupplierSettings Models
class SupplierSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    supplierCompanyId: str
    minOrderAmount: float = 0
    deliveryDays: List[str] = []
    deliveryTime: str = ""
    orderReceiveDeadline: str = ""
    logisticsType: LogisticsType = LogisticsType.own
    is_paused: bool = False
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SupplierSettingsUpdate(BaseModel):
    minOrderAmount: Optional[float] = None
    deliveryDays: Optional[List[str]] = None
    deliveryTime: Optional[str] = None
    orderReceiveDeadline: Optional[str] = None
    logisticsType: Optional[LogisticsType] = None
    is_paused: Optional[bool] = None

class SupplierPauseBody(BaseModel):
    is_paused: bool


class BulkDeleteBody(BaseModel):
    ids: List[str]

# PriceList Models
class PriceList(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    supplierCompanyId: str
    productName: str
    article: str
    price: float
    unit: str
    minQuantity: Optional[int] = 1
    availability: bool = True
    active: bool = True
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PriceListCreate(BaseModel):
    productName: str
    article: Optional[str] = ""
    price: float
    unit: str
    minQuantity: Optional[int] = 1
    pack_quantity: Optional[int] = 1
    availability: bool = True
    active: bool = True

class PriceListUpdate(BaseModel):
    article: Optional[str] = None
    name: Optional[str] = None
    unit: Optional[str] = None
    pack_quantity: Optional[int] = None
    min_order: Optional[int] = None
    unit_price: Optional[float] = None
    price: Optional[float] = None  # legacy, maps to unit_price
    availability: Optional[bool] = None
    active: Optional[bool] = None

# Restaurant Position Catalog Models
class RestaurantPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurantCompanyId: str
    positionNumber: str
    productId: str
    productName: str
    unit: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Order Models
class OrderItem(BaseModel):
    productName: str
    article: Optional[str] = ""
    quantity: float
    price: float
    unit: str

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customerCompanyId: str
    supplierCompanyId: str
    orderDate: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    amount: float
    status: OrderStatus = OrderStatus.new
    orderDetails: List[OrderItem] = []
    deliveryAddress: Optional[DeliveryAddress] = None
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCreate(BaseModel):
    supplierCompanyId: str
    amount: float
    orderDetails: List[OrderItem]
    deliveryAddress: Optional[DeliveryAddress] = None

# Registration Models
class SupplierRegistration(BaseModel):
    email: EmailStr
    password: str
    inn: str
    companyName: str
    legalAddress: str
    ogrn: str
    actualAddress: str
    phone: str
    companyEmail: EmailStr
    contactPersonName: str
    contactPersonPosition: str
    contactPersonPhone: str
    dataProcessingConsent: bool

class CustomerRegistration(BaseModel):
    email: EmailStr
    password: str
    inn: str
    companyName: str
    legalAddress: str
    ogrn: str
    actualAddress: str
    phone: str
    companyEmail: EmailStr
    contactPersonName: str
    contactPersonPosition: str
    contactPersonPhone: str
    deliveryAddresses: List[DeliveryAddress]
    dataProcessingConsent: bool

# ==================== HELPER FUNCTIONS ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    payload = decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

# Mock INN lookup data
MOCK_INN_DATA = {
    "7707083893": {
        "companyName": "ООО Поставщик Продуктов",
        "legalAddress": "г. Москва, ул. Ленина, д. 10",
        "ogrn": "1027700132195"
    },
    "7701234567": {
        "companyName": "ООО Ресторан Вкусно",
        "legalAddress": "г. Москва, ул. Пушкина, д. 20",
        "ogrn": "1027701234567"
    },
    "7702345678": {
        "companyName": "ООО Свежие Продукты",
        "legalAddress": "г. Москва, ул. Тверская, д. 5",
        "ogrn": "1027702345678"
    },
    "7703456789": {
        "companyName": "ООО Кафе Столовая",
        "legalAddress": "г. Москва, ул. Арбат, д. 15",
        "ogrn": "1027703456789"
    }
}

# ==================== DEBUG/VERSION ROUTES ====================

@api_router.get("/debug/version")
async def get_version():
    """Debug endpoint: deployment version info"""
    
    # Check if v12 master file exists
    v12_file = ROOT_DIR / 'BESTPRICE_IDEAL_MASTER_v12_PATCH_FULL.xlsx'
    sot_file = v12_file.name if v12_file.exists() else "NOT_FOUND"
    
    # Check guards enabled
    try:
        from p0_hotfix_stabilization import REQUIRED_ANCHORS, NEGATIVE_KEYWORDS
        guards_enabled = len(REQUIRED_ANCHORS) > 0 and len(NEGATIVE_KEYWORDS) > 0
    except:
        guards_enabled = False
    
    return {
        "build_sha": BUILD_SHA,
        "build_time": BUILD_TIME,
        "env": os.environ.get('ENV', 'production'),
        "db_name": os.environ.get('DB_NAME'),
        "collection_name": "supplier_items",
        "sot_file": sot_file,
        "guards_enabled": guards_enabled,
        "guards_categories": {
            "required_anchors": len(REQUIRED_ANCHORS) if guards_enabled else 0,
            "forbidden_tokens": len(NEGATIVE_KEYWORDS) if guards_enabled else 0
        }
    }


# ==================== AUTH ROUTES ====================

async def _auto_link_supplier_to_all_restaurants(supplier_company_id: str) -> None:
    """Create supplier_restaurant_settings for all restaurants (pending)."""
    restaurants = await db.companies.find({"type": "customer"}, {"_id": 0, "id": 1}).to_list(500)
    now = datetime.now(timezone.utc).isoformat()
    for r in restaurants:
        await db.supplier_restaurant_settings.update_one(
            {"supplierId": supplier_company_id, "restaurantId": r["id"]},
            {"$set": {
                "contract_accepted": False,
                "is_paused": False,
                "updatedAt": now
            }},
            upsert=True
        )


@api_router.post("/auth/register/supplier", response_model=TokenResponse)
async def register_supplier(data: SupplierRegistration):
    # Check if user exists
    existing_user = await db.users.find_one({"email": data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user = User(
        email=data.email,
        passwordHash=hash_password(data.password),
        role=UserRole.supplier
    )
    user_dict = user.model_dump()
    user_dict['createdAt'] = user_dict['createdAt'].isoformat()
    user_dict['updatedAt'] = user_dict['updatedAt'].isoformat()
    await db.users.insert_one(user_dict)
    
    # Create company
    company = Company(
        type=CompanyType.supplier,
        userId=user.id,
        inn=data.inn,
        ogrn=data.ogrn,
        companyName=data.companyName,
        legalAddress=data.legalAddress,
        actualAddress=data.actualAddress,
        phone=data.phone,
        email=data.companyEmail,
        contactPersonName=data.contactPersonName,
        contactPersonPosition=data.contactPersonPosition,
        contactPersonPhone=data.contactPersonPhone,
        contractAccepted=True
    )
    company_dict = company.model_dump()
    company_dict['createdAt'] = company_dict['createdAt'].isoformat()
    company_dict['updatedAt'] = company_dict['updatedAt'].isoformat()
    await db.companies.insert_one(company_dict)
    
    # Create default supplier settings
    settings = SupplierSettings(supplierCompanyId=company.id)
    settings_dict = settings.model_dump()
    settings_dict['updatedAt'] = settings_dict['updatedAt'].isoformat()
    await db.supplier_settings.insert_one(settings_dict)

    # Auto-link new supplier to all existing restaurants (pending)
    await _auto_link_supplier_to_all_restaurants(company.id)
    
    # Create token
    token = create_access_token({"sub": user.id, "role": user.role})
    
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "companyId": company.id
        }
    )

@api_router.post("/auth/register/customer", response_model=TokenResponse)
async def register_customer(data: CustomerRegistration):
    # Check if user exists
    existing_user = await db.users.find_one({"email": data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user = User(
        email=data.email,
        passwordHash=hash_password(data.password),
        role=UserRole.customer
    )
    user_dict = user.model_dump()
    user_dict['createdAt'] = user_dict['createdAt'].isoformat()
    user_dict['updatedAt'] = user_dict['updatedAt'].isoformat()
    await db.users.insert_one(user_dict)
    
    # Create company
    company = Company(
        type=CompanyType.customer,
        userId=user.id,
        inn=data.inn,
        ogrn=data.ogrn,
        companyName=data.companyName,
        legalAddress=data.legalAddress,
        actualAddress=data.actualAddress,
        phone=data.phone,
        email=data.companyEmail,
        contactPersonName=data.contactPersonName,
        contactPersonPosition=data.contactPersonPosition,
        contactPersonPhone=data.contactPersonPhone,
        deliveryAddresses=data.deliveryAddresses,
        contractAccepted=True
    )
    company_dict = company.model_dump()
    company_dict['createdAt'] = company_dict['createdAt'].isoformat()
    company_dict['updatedAt'] = company_dict['updatedAt'].isoformat()
    await db.companies.insert_one(company_dict)
    
    # Create token
    token = create_access_token({"sub": user.id, "role": user.role})
    
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "companyId": company.id
        }
    )

# ==================== DEV AUTH BYPASS ====================
DEV_AUTH_BYPASS = os.environ.get("DEV_AUTH_BYPASS", "").strip() == "1"

class DevLoginRequest(BaseModel):
    role: str  # "supplier" | "customer"
    email: Optional[str] = None
    phone: Optional[str] = None

DEV_EVIDENCE_ENABLED = os.environ.get("BESTPRICE_DEV_EVIDENCE", "1").strip().lower() not in ("0", "false", "off")


@api_router.post("/dev/evidence")
async def dev_evidence(payload: dict):
    """DEV-only: save UI evidence (e.g. price upload last attempt) to evidence/PRICE_UPLOAD_UI_LAST.json. Disabled in prod (set BESTPRICE_DEV_EVIDENCE=0)."""
    if not DEV_EVIDENCE_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")
    evidence_dir = ROOT_DIR.parent / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / "PRICE_UPLOAD_UI_LAST.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            import json
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to write dev evidence: %s", e)
        raise HTTPException(status_code=500, detail="Failed to write evidence file")
    return {"ok": True, "path": str(path)}


@api_router.post("/dev/login", response_model=TokenResponse)
async def dev_login(data: DevLoginRequest):
    """DEV-only: login without password. Returns 404 when DEV_AUTH_BYPASS != 1."""
    if not DEV_AUTH_BYPASS:
        raise HTTPException(status_code=404, detail="Not Found")
    role = (data.role or "supplier").strip().lower()
    if role not in ("supplier", "customer"):
        raise HTTPException(status_code=400, detail="role must be supplier or customer")
    user = None
    company_id = None
    if data.email:
        user = await db.users.find_one({"email": data.email.strip(), "role": role}, {"_id": 0})
    if not user and data.phone:
        phone_norm = "".join(c for c in str(data.phone) if c.isdigit())[-10:]
        async for c in db.companies.find({"type": role}, {"_id": 0, "id": 1, "userId": 1, "phone": 1, "contactPersonPhone": 1}):
            cp = (c.get("phone") or c.get("contactPersonPhone") or "")
            if phone_norm in "".join(x for x in cp if x.isdigit()):
                user = await db.users.find_one({"id": c["userId"]}, {"_id": 0})
                company_id = c["id"]
                break
    if not user:
        user = await db.users.find_one({"role": role}, {"_id": 0})
    if user:
        if not company_id and user.get("role") != "responsible":
            company = await db.companies.find_one({"userId": user["id"]}, {"_id": 0, "id": 1})
            company_id = company["id"] if company else None
        token = create_access_token({"sub": user["id"], "role": user["role"]})
        return TokenResponse(
            access_token=token,
            user={"id": user["id"], "email": user.get("email", ""), "role": user["role"], "companyId": company_id}
        )
    user_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    email = data.email or f"dev-{role}@local.dev"
    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "id": user_id, "email": email, "passwordHash": hash_password("dev-no-password"),
        "role": role, "createdAt": now, "updatedAt": now
    }
    company_doc = {
        "id": company_id, "type": role, "userId": user_id,
        "inn": "0000000000", "ogrn": "0000000000000",
        "companyName": f"DEV {role.title()}",
        "legalAddress": "DEV", "actualAddress": "DEV", "phone": "+70000000000",
        "email": email, "contractAccepted": True, "createdAt": now, "updatedAt": now
    }
    await db.users.insert_one(user_doc)
    await db.companies.insert_one(company_doc)
    if role == "supplier":
        await db.supplier_settings.insert_one({
            "id": str(uuid.uuid4()), "supplierCompanyId": company_id,
            "minOrderAmount": 0, "deliveryDays": [], "deliveryTime": "", "orderReceiveDeadline": "",
            "logisticsType": "own", "updatedAt": now
        })
        await _auto_link_supplier_to_all_restaurants(company_id)
    token = create_access_token({"sub": user_id, "role": role})
    return TokenResponse(
        access_token=token,
        user={"id": user_id, "email": email, "role": role, "companyId": company_id}
    )


@api_router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not verify_password(data.password, user['passwordHash']):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Get company
    if user['role'] == 'responsible':
        # Responsible users have companyId directly in user document
        company_id = user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    token = create_access_token({"sub": user['id'], "role": user['role']})
    
    return TokenResponse(
        access_token=token,
        user={
            "id": user['id'],
            "email": user['email'],
            "role": user['role'],
            "companyId": company_id
        }
    )



@api_router.get("/auth/inn/{inn}")
async def lookup_inn(inn: str):
    if inn in MOCK_INN_DATA:
        return MOCK_INN_DATA[inn]

    return {
        "companyName": "",
        "legalAddress": "",
        "ogrn": ""
    }


# ==================== PASSWORD RECOVERY ====================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    role: str = "supplier"

class ResetPasswordRequest(BaseModel):
    token: str
    newPassword: str

PASSWORD_RESET_EXPIRE_MINUTES = 30
PASSWORD_RESET_COLLECTION = "password_reset_tokens"

def _send_reset_email(to_email: str, reset_link: str) -> bool:
    smtp_host = os.environ.get('SMTP_HOST', '').strip()
    smtp_user = os.environ.get('SMTP_USER', '').strip()
    smtp_pass = os.environ.get('SMTP_PASSWORD', '').strip()
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    from_email = os.environ.get('SMTP_FROM', smtp_user or 'noreply@bestprice.local')
    if not smtp_host or not smtp_user or not smtp_pass:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "BestPrice: восстановление пароля"
        msg['From'] = from_email
        msg['To'] = to_email
        text = f"Перейдите по ссылке для сброса пароля:\n{reset_link}\n\nСсылка действительна 30 минут."
        msg.attach(MIMEText(text, 'plain', 'utf-8'))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.warning(f"Failed to send reset email: {e}")
        return False


@api_router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    role = (data.role or "supplier").strip().lower()
    if role != "supplier":
        return {"message": "If email exists, we sent a reset link."}
    frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    user = await db.users.find_one({"email": data.email, "role": "supplier"}, {"_id": 0, "id": 1})
    if user:
        user_id = user["id"]
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_reset_token(raw_token)
        expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)
        await db[PASSWORD_RESET_COLLECTION].delete_many({"user_id": user_id, "used_at": None})
        await db[PASSWORD_RESET_COLLECTION].insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "used_at": None,
            "created_at": datetime.utcnow(),
        })
        reset_link = f"{frontend_url}/supplier/reset-password?token={raw_token}"
        print(f"RESET LINK: {reset_link}")
        _send_reset_email(data.email, reset_link)
    return {"message": "If email exists, we sent a reset link."}


@api_router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordRequest):
    token_hash = hash_reset_token(data.token)
    rec = await db[PASSWORD_RESET_COLLECTION].find_one(
        {"token_hash": token_hash},
        {"_id": 0, "user_id": 1, "expires_at": 1, "used_at": 1}
    )
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if rec.get("used_at"):
        raise HTTPException(status_code=400, detail="Token already used")

    now = datetime.utcnow()
    expires = rec["expires_at"]
    if expires is not None and hasattr(expires, 'tzinfo') and expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    if expires is not None and now > expires:
        raise HTTPException(status_code=400, detail="Token expired")

    new_hash = hash_password(data.newPassword)
    await db.users.update_one(
        {"id": rec["user_id"]},
        {"$set": {"passwordHash": new_hash, "updatedAt": datetime.utcnow().isoformat()}}
    )
    await db[PASSWORD_RESET_COLLECTION].update_one(
        {"token_hash": token_hash},
        {"$set": {"used_at": datetime.utcnow()}}
    )
    return {"message": "Password updated."}


# ==================== PHONE OTP ====================

def _normalize_phone(phone: str) -> str:
    s = re.sub(r'\D', '', str(phone).strip())
    if not s:
        return ""
    if s.startswith('8') and len(s) == 11:
        s = '7' + s[1:]
    elif len(s) == 10:
        s = '7' + s
    elif s.startswith('7') and len(s) != 11:
        pass
    return '+' + s

def _phone_matches(company_phone: str, normalized: str) -> bool:
    n2 = _normalize_phone(company_phone or '')
    return n2 == normalized and bool(normalized)

PHONE_OTP_COLLECTION = "phone_otp"
PHONE_OTP_EXPIRE_MINUTES = 5
PHONE_OTP_MAX_ATTEMPTS = 5
PHONE_REQUEST_COOLDOWN_SEC = 60

def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode('utf-8')).hexdigest()

def _send_sms(phone: str, text: str, otp: str = "") -> bool:
    """
    Dev fallback: если SMS не настроен — печатает OTP в лог и возвращает True.
    Никаких return False в dev-сценариях.
    """
    def _dev_fallback(reason: str = ""):
        code = otp or text
        print(f"OTP CODE: {code} (to {phone}) {reason}".strip())
        return True

    provider = os.environ.get("SMS_PROVIDER", "").strip().lower()
    if provider != "twilio":
        return _dev_fallback("[dev: SMS_PROVIDER!=twilio]")

    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token_env = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.environ.get("TWILIO_PHONE_FROM", "").strip()

    if not (sid and token_env and from_num):
        return _dev_fallback("[dev: missing TWILIO* env]")

    try:
        from twilio.rest import Client
        client = Client(sid, token_env)
        client.messages.create(body=text, from_=from_num, to=phone)
        return True
    except Exception as e:
        return _dev_fallback(f"[dev: twilio error: {e}]")

class PhoneRequestOtpRequest(BaseModel):
    phone: str
    role: Optional[str] = "supplier"

class PhoneResetPasswordRequest(BaseModel):
    phone: str
    otp: str
    new_password: str
    role: Optional[str] = "supplier"

@api_router.post("/auth/phone/request-otp")
async def phone_request_otp(data: PhoneRequestOtpRequest):
    print("PHONE OTP: request-otp HIT")
    role = (data.role or "supplier").strip().lower()
    if role != "supplier":
        print(f"PHONE OTP: role not supplier -> {role}")
        return {"message": "If phone exists, code sent."}
    phone_norm = _normalize_phone(data.phone)
    print(f"PHONE OTP: normalized={phone_norm} raw={data.phone}")
    if not phone_norm or len(phone_norm) < 11:
        print("PHONE OTP: invalid normalized phone -> early return")
        return {"message": "If phone exists, code sent."}

    coll = db[PHONE_OTP_COLLECTION]
    existing = await coll.find_one({"phone": phone_norm, "role": "supplier"})
    if existing and existing.get("created_at"):
        created = existing["created_at"]
        if hasattr(created, "tzinfo") and created.tzinfo:
            created = created.replace(tzinfo=None)

        diff = (datetime.utcnow() - created).total_seconds()
        print(f"PHONE OTP: cooldown check diff={diff} sec")

        if diff < PHONE_REQUEST_COOLDOWN_SEC:
            print("PHONE OTP: cooldown triggered -> early return")
            return {"message": "If phone exists, code sent."}

    # проверяем что телефон реально есть среди supplier компаний
    found = False
    async for c in db.companies.find({"type": "supplier"}):
        if _phone_matches(c.get("phone") or c.get("contactPersonPhone") or "", phone_norm):
            found = True
            break
    if not found:
        print("PHONE OTP: supplier with this phone NOT FOUND -> early return")
        return {"message": "If phone exists, code sent."}

    otp = f"{secrets.randbelow(900000) + 100000}"
    print(f"DEBUG OTP GENERATED: {otp}")
    otp_hash = _hash_otp(otp)
    expires_at = datetime.utcnow() + timedelta(minutes=PHONE_OTP_EXPIRE_MINUTES)
    await coll.delete_many({"phone": phone_norm, "role": "supplier"})
    await coll.insert_one({
        "phone": phone_norm,
        "role": "supplier",
        "otp_hash": otp_hash,
        "expires_at": expires_at,
        "attempts": 0,
        "created_at": datetime.utcnow(),
    })
    print("AFTER INSERT - CALLING SEND_SMS")
    _send_sms(phone_norm, f"Your OTP is {otp}", otp=otp)
    return {"message": "If phone exists, code sent."}

@api_router.post("/auth/phone/reset-password")
async def phone_reset_password(data: PhoneResetPasswordRequest):
    role = (data.role or "supplier").strip().lower()
    if role != "supplier":
        raise HTTPException(status_code=400, detail="Invalid request")
    phone_norm = _normalize_phone(data.phone)
    coll = db[PHONE_OTP_COLLECTION]
    rec = await coll.find_one({"phone": phone_norm, "role": "supplier"}, {"_id": 0, "otp_hash": 1, "expires_at": 1, "attempts": 1})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    if rec.get("attempts", 0) >= PHONE_OTP_MAX_ATTEMPTS:
        await coll.delete_one({"phone": phone_norm, "role": "supplier"})
        raise HTTPException(status_code=400, detail="Too many attempts")
    now = datetime.utcnow()
    expires = rec.get("expires_at")
    if expires:
        if hasattr(expires, 'tzinfo') and expires.tzinfo:
            expires = expires.replace(tzinfo=None)
        if now > expires:
            await coll.delete_one({"phone": phone_norm, "role": "supplier"})
            raise HTTPException(status_code=400, detail="Code expired")
    if _hash_otp(data.otp) != rec.get("otp_hash"):
        await coll.update_one({"phone": phone_norm, "role": "supplier"}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=400, detail="Invalid code")
    user_id = None
    async for c in db.companies.find({"type": "supplier"}, {"_id": 0, "userId": 1, "phone": 1, "contactPersonPhone": 1}):
        if _phone_matches(c.get("phone") or c.get("contactPersonPhone") or "", phone_norm):
            user_id = c.get("userId")
            break
    if not user_id:
        await coll.delete_one({"phone": phone_norm, "role": "supplier"})
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    new_hash = hash_password(data.new_password)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"passwordHash": new_hash, "updatedAt": datetime.utcnow().isoformat()}}
    )
    await coll.delete_one({"phone": phone_norm, "role": "supplier"})
    return {"message": "Password updated."}


async def _supplier_is_paused(company_id: str) -> bool:
    """Check if supplier (company) is paused."""
    if not company_id:
        return False
    settings = await db.supplier_settings.find_one(
        {"supplierCompanyId": company_id},
        {"_id": 0, "is_paused": 1}
    )
    return bool(settings and settings.get("is_paused"))


@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("companyId")
    if not company_id and current_user.get("role") in ("supplier", "customer"):
        company = await db.companies.find_one({"userId": current_user["id"]}, {"_id": 0, "id": 1})
        company_id = company["id"] if company else None
    result = {
        "id": current_user.get("id"),
        "email": current_user.get("email"),
        "role": current_user.get("role"),
        "companyId": company_id,
    }
    if current_user.get("role") == UserRole.supplier and company_id:
        result["is_paused"] = await _supplier_is_paused(company_id)
    return result


# ==================== COMPANY ROUTES ====================

@api_router.get("/companies/my", response_model=Company)
async def get_my_company(current_user: dict = Depends(get_current_user)):
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

@api_router.put("/companies/my", response_model=Company)
async def update_my_company(data: CompanyUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data['updatedAt'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.companies.update_one(
        {"userId": current_user['id']},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    return company

@api_router.get("/companies/{company_id}", response_model=Company)
async def get_company(company_id: str):
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

# ==================== SUPPLIER SETTINGS ROUTES ====================

@api_router.get("/supplier-settings/my", response_model=SupplierSettings)
async def get_my_supplier_settings(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    settings = await db.supplier_settings.find_one({"supplierCompanyId": company['id']}, {"_id": 0})
    if not settings:
        # Create default settings
        settings = SupplierSettings(supplierCompanyId=company['id'])
        settings_dict = settings.model_dump()
        settings_dict['updatedAt'] = settings_dict['updatedAt'].isoformat()
        await db.supplier_settings.insert_one(settings_dict)
        return settings
    return settings

@api_router.put("/supplier-settings/my", response_model=SupplierSettings)
async def update_my_supplier_settings(data: SupplierSettingsUpdate, current_user: dict = Depends(get_current_user)):
    """Update supplier settings; create if missing (idempotent)."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    sid = company['id']
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data['updatedAt'] = datetime.now(timezone.utc).isoformat()
    existing = await db.supplier_settings.find_one({"supplierCompanyId": sid}, {"_id": 0})
    if not existing:
        settings = SupplierSettings(supplierCompanyId=sid)
        settings_dict = settings.model_dump()
        settings_dict['updatedAt'] = settings_dict['updatedAt'].isoformat()
        for k, v in update_data.items():
            if k in settings_dict:
                settings_dict[k] = v
        await db.supplier_settings.insert_one(settings_dict)
        return await db.supplier_settings.find_one({"supplierCompanyId": sid}, {"_id": 0})
    await db.supplier_settings.update_one(
        {"supplierCompanyId": sid},
        {"$set": update_data}
    )
    return await db.supplier_settings.find_one({"supplierCompanyId": sid}, {"_id": 0})


@api_router.patch("/supplier/pause")
async def supplier_pause(data: SupplierPauseBody, current_user: dict = Depends(get_current_user)):
    """Toggle supplier pause: when paused, catalog is hidden from customers and editing is disabled."""
    if current_user["role"] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company = await db.companies.find_one({"userId": current_user["id"]}, {"_id": 0, "id": 1})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    sid = company["id"]
    existing = await db.supplier_settings.find_one({"supplierCompanyId": sid}, {"_id": 0})
    update = {"is_paused": data.is_paused, "updatedAt": datetime.now(timezone.utc).isoformat()}
    if not existing:
        settings = SupplierSettings(supplierCompanyId=sid, is_paused=data.is_paused)
        settings_dict = settings.model_dump()
        settings_dict["updatedAt"] = settings_dict["updatedAt"].isoformat()
        await db.supplier_settings.insert_one(settings_dict)
    else:
        await db.supplier_settings.update_one(
            {"supplierCompanyId": sid},
            {"$set": update}
        )
    return {"is_paused": data.is_paused}


@api_router.get("/supplier/me")
async def get_supplier_me(current_user: dict = Depends(get_current_user)):
    """Supplier-specific profile with is_paused (alias for auth/me for supplier)."""
    if current_user["role"] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get("companyId")
    if not company_id:
        company = await db.companies.find_one({"userId": current_user["id"]}, {"_id": 0, "id": 1})
        company_id = company["id"] if company else None
    return {
        "id": current_user.get("id"),
        "companyId": company_id,
        "is_paused": await _supplier_is_paused(company_id) if company_id else False,
    }

# ==================== PRICE LIST ROUTES ====================

async def _require_supplier_not_paused(company_id: str):
    """Raise 403 if supplier is paused (blocks create/update/delete/import)."""
    if await _supplier_is_paused(company_id):
        raise HTTPException(status_code=403, detail="Поставщик на паузе. Редактирование отключено.")


@api_router.get("/supplier/price-list")
@api_router.get("/price-lists/my")
async def get_my_price_lists(current_user: dict = Depends(get_current_user)):
    """Return supplier's price list items from supplier_items (single source of truth)."""
    if current_user.get('role') not in (UserRole.supplier, UserRole.admin):
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get('companyId')
    if not company_id and current_user.get('role') == UserRole.supplier:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        return []
    # Match how import/create write: supplier_company_id (snake_case); fallback supplierCompanyId (camelCase)
    q = {"active": True, "$or": [{"supplier_company_id": company_id}, {"supplierCompanyId": company_id}]}
    items = await db.supplier_items.find(q, {"_id": 0}).to_list(10000)
    result = []
    for si in items:
        created = si.get("created_at") or si.get("updated_at")
        updated = si.get("updated_at") or si.get("created_at")
        result.append({
            "id": si.get("id", si.get("unique_key", "")),
            "article": si.get("supplier_item_code", ""),
            "name": si.get("name_raw", ""),
            "unit": si.get("unit_supplier", si.get("unit_norm", "шт")),
            "pack_quantity": int(si.get("pack_qty", 1)),
            "min_order": int(si.get("min_order_qty", 1)),
            "unit_price": float(si.get("price", 0)),
            "availability": bool(si.get("active", True)),
            "price": float(si.get("price", 0)),  # legacy
            "productName": si.get("name_raw", ""),
            "supplierCompanyId": si.get("supplier_company_id", company_id),
            "minQuantity": int(si.get("min_order_qty", 1)),
            "active": si.get("active", True),
            "createdAt": created.isoformat() if hasattr(created, "isoformat") else str(created),
            "updatedAt": updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
        })
    return result

@api_router.post("/price-lists", response_model=PriceList)
async def create_price_list(data: PriceListCreate, current_user: dict = Depends(get_current_user)):
    """Create one price list item: write to supplier_items + pricelists metadata (single source)."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    await _require_supplier_not_paused(company['id'])
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company_id = company['id']
    supplier_name = company.get('companyName', company.get('name', 'Unknown'))
    pricelist_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    name_raw = (data.productName or "").strip()
    name_norm = name_raw.lower().strip().replace("  ", " ") if name_raw else ""
    unit_supplier = data.unit or "шт"
    unit_norm = unit_supplier if unit_supplier in ("pcs", "kg", "l") else "pcs"
    unique_key = f"{company_id}:{name_norm}:{unit_supplier}" if not data.article else f"{company_id}:{(data.article or '').strip()}"
    now = datetime.now(timezone.utc)
    item_data = {
        "id": item_id,
        "unique_key": unique_key,
        "supplier_company_id": company_id,
        "supplierCompanyId": company_id,
        "price_list_id": pricelist_id,
        "supplier_item_code": data.article or "",
        "name_raw": name_raw,
        "name_norm": name_norm,
        "unit_supplier": unit_supplier,
        "unit_norm": unit_norm,
        "unit_type": "PIECE",
        "price": float(data.price),
        "pack_qty": max(1, int(data.pack_quantity or 1)),
        "min_order_qty": max(1, int(data.minQuantity or 1)),
        "active": getattr(data, "active", True) and getattr(data, "availability", True),
        "created_at": now,
        "updated_at": now,
    }
    await db.supplier_items.insert_one(item_data)
    pricelist_meta = {
        "id": pricelist_id,
        "supplierId": company_id,
        "supplierName": supplier_name,
        "fileName": "manual",
        "itemsCount": 1,
        "createdAt": now.isoformat(),
        "active": True,
    }
    await db.pricelists.insert_one(pricelist_meta)
    return PriceList(
        id=item_id,
        supplierCompanyId=company_id,
        productName=name_raw,
        article=data.article or "",
        price=data.price,
        unit=unit_supplier,
        minQuantity=int(data.minQuantity or 1),
        availability=getattr(data, "availability", True),
        active=True,
        createdAt=now,
        updatedAt=now,
    )

@api_router.put("/price-lists/{price_id}")
async def update_price_list(price_id: str, data: PriceListUpdate, current_user: dict = Depends(get_current_user)):
    """Update one price list item in supplier_items. Accepts article, name, unit, pack_quantity, min_order, unit_price, availability."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get('companyId')
    if not company_id and current_user.get('role') == UserRole.supplier:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    await _require_supplier_not_paused(company_id)
    set_fields = {"updated_at": datetime.now(timezone.utc)}
    price_val = data.unit_price if data.unit_price is not None else data.price
    if price_val is not None:
        set_fields["price"] = float(price_val)
    if data.article is not None:
        set_fields["supplier_item_code"] = str(data.article).strip()
    if data.name is not None:
        set_fields["name_raw"] = str(data.name).strip()
        set_fields["name_norm"] = (str(data.name).lower().strip().replace("  ", " ") or "")
    if data.unit is not None:
        set_fields["unit_supplier"] = str(data.unit).strip() or "шт"
        set_fields["unit_norm"] = set_fields["unit_supplier"] if set_fields["unit_supplier"] in ("pcs", "kg", "l") else "pcs"
    if data.pack_quantity is not None:
        set_fields["pack_qty"] = max(1, int(data.pack_quantity))
    if data.min_order is not None:
        set_fields["min_order_qty"] = max(1, int(data.min_order))
    if data.availability is not None:
        set_fields["active"] = data.availability
    if data.active is not None:
        set_fields["active"] = data.active
    match = {"id": price_id, "$or": [{"supplier_company_id": company_id}, {"supplierCompanyId": company_id}]}
    result = await db.supplier_items.update_one(match, {"$set": set_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Price list item not found")
    si = await db.supplier_items.find_one(match, {"_id": 0})
    created = si.get("created_at") or si.get("updated_at")
    updated = si.get("updated_at")
    return {
        "id": si.get("id", price_id),
        "article": si.get("supplier_item_code", ""),
        "name": si.get("name_raw", ""),
        "unit": si.get("unit_supplier", si.get("unit_norm", "шт")),
        "pack_quantity": int(si.get("pack_qty", 1)),
        "min_order": int(si.get("min_order_qty", 1)),
        "unit_price": float(si.get("price", 0)),
        "availability": bool(si.get("active", True)),
        "supplierCompanyId": si.get("supplier_company_id", company_id),
        "productName": si.get("name_raw", ""),
        "price": float(si.get("price", 0)),
        "minQuantity": int(si.get("min_order_qty", 1)),
        "active": si.get("active", True),
        "createdAt": created.isoformat() if hasattr(created, "isoformat") else str(created),
        "updatedAt": updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
    }

@api_router.delete("/price-lists/{price_id}")
async def delete_price_list(price_id: str, current_user: dict = Depends(get_current_user)):
    """Delete (deactivate) one price list item in supplier_items."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get('companyId')
    if not company_id and current_user.get('role') == UserRole.supplier:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    await _require_supplier_not_paused(company_id)
    match = {"id": price_id, "$or": [{"supplier_company_id": company_id}, {"supplierCompanyId": company_id}]}
    result = await db.supplier_items.update_one(
        match,
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Price list not found")
    return {"message": "Price list deleted"}


@api_router.post("/supplier/items/bulk-delete")
@api_router.post("/price-lists/bulk-delete")
async def bulk_delete_price_list_items(data: BulkDeleteBody, current_user: dict = Depends(get_current_user)):
    """Soft-delete multiple price list items (supplier_items)."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get('companyId')
    if not company_id and current_user.get('role') == UserRole.supplier:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    await _require_supplier_not_paused(company_id)
    ids = [x for x in (data.ids or []) if x]
    if not ids:
        return {"deletedCount": 0}
    result = await db.supplier_items.update_many(
        {
            "id": {"$in": ids},
            "$or": [{"supplier_company_id": company_id}, {"supplierCompanyId": company_id}],
        },
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"deletedCount": result.modified_count}


@api_router.post("/supplier/price-list")
@api_router.post("/price-lists/upload")
async def upload_price_list(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    await _require_supplier_not_paused(company['id'])
    
    # Read file
    try:
        contents = await file.read()
    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logger.exception(
            "Failed to read uploaded file",
            extra={
                "correlation_id": correlation_id,
                "supplier_id": company.get('id'),
                "supplier_email": company.get('companyEmail'),
                "filename": file.filename,
            },
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "file_read_error",
                "message": "Could not read uploaded file.",
                "correlation_id": correlation_id,
            },
        )
    
    correlation_id = str(uuid.uuid4())
    supplier_id = company.get("id")
    supplier_email = company.get("companyEmail") or company.get("email")
    file_size = len(contents)
    checksum = hashlib.sha256(contents).hexdigest()
    
    existing_upload = await db.price_list_uploads.find_one(
        {"supplierId": supplier_id, "checksum": checksum},
        {"_id": 0},
    )
    if existing_upload:
        logger.info(
            "Price list upload skipped (duplicate checksum)",
            extra={
                "correlation_id": correlation_id,
                "checksum": checksum,
                "supplier_id": supplier_id,
                "filename": file.filename,
                "file_size": file_size,
            },
        )
        return {
            "status": "already_uploaded",
            "message": "Identical price list already uploaded.",
            "columns": existing_upload.get("columns", []),
            "preview": existing_upload.get("preview", []),
            "total_rows": existing_upload.get("totalRows", 0),
            "checksum": checksum,
            "correlation_id": existing_upload.get("correlationId", correlation_id),
        }
    
    if file_size == 0:
        logger.warning(
            "Uploaded file is empty",
            extra={
                "correlation_id": correlation_id,
                "supplier_id": supplier_id,
                "filename": file.filename,
            },
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "empty_file",
                "message": "Uploaded file is empty.",
                "correlation_id": correlation_id,
            },
        )
    
    def parse_dataframe_sync():
        return _parse_price_list_dataframe(contents, file.filename or "")

    try:
        df = await asyncio.to_thread(parse_dataframe_sync)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to parse price list file",
            extra={
                "correlation_id": correlation_id,
                "supplier_id": supplier_id,
                "supplier_email": supplier_email,
                "filename": file.filename,
                "file_size": file_size,
            },
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "parse_failure",
                "message": "Failed to parse price list file.",
                "correlation_id": correlation_id,
            },
        )
    
    total_rows = int(df.shape[0])
    total_columns = int(df.shape[1])
    
    def validation_error(error_code: str, message: str, **extra_details):
        logger.warning(
            message,
            extra={
                "correlation_id": correlation_id,
                "supplier_id": supplier_id,
                "filename": file.filename,
                "error_code": error_code,
                **extra_details,
            },
        )
        detail = {
            "error": error_code,
            "message": message,
            "correlation_id": correlation_id,
        }
        detail.update(extra_details)
        raise HTTPException(status_code=422, detail=detail)
    
    if total_rows == 0:
        validation_error("empty_data", "Price list has no data rows.")
    
    if total_rows > 100000:
        validation_error(
            "too_many_rows",
            "Price list has too many rows.",
            total_rows=total_rows,
        )
    
    if total_columns == 0:
        validation_error("no_columns", "Price list has no columns.")
    
    if total_columns > 200:
        validation_error(
            "too_many_columns",
            "Price list has too many columns.",
            total_columns=total_columns,
        )
    
    duplicate_columns = [
        str(col)
        for col, is_dup in zip(df.columns, df.columns.duplicated())
        if is_dup
    ]
    if duplicate_columns:
        validation_error(
            "duplicate_columns",
            "Price list contains duplicate column names.",
            duplicate_columns=duplicate_columns,
        )
    
    unnamed_columns = [
        str(col)
        for col in df.columns
        if str(col).strip() == "" or str(col).lower().startswith("unnamed")
    ]
    if unnamed_columns:
        validation_error(
            "unnamed_columns",
            "Price list contains unnamed columns.",
            unnamed_columns=unnamed_columns,
        )
    
    preview_df = df.head(5).copy()
    preview_records = (
        preview_df.fillna("")
        .astype(str)
        .to_dict("records")
    )
    column_names = [str(col) for col in df.columns]
    
    logger.info(
        "Price list parsed successfully",
        extra={
            "correlation_id": correlation_id,
            "supplier_id": supplier_id,
            "supplier_email": supplier_email,
            "filename": file.filename,
            "file_size": file_size,
            "total_rows": total_rows,
            "total_columns": total_columns,
        },
    )
    
    await db.price_list_uploads.update_one(
        {"supplierId": supplier_id, "checksum": checksum},
        {
            "$set": {
                "supplierId": supplier_id,
                "supplierEmail": supplier_email,
                "checksum": checksum,
                "fileName": file.filename,
                "fileSize": file_size,
                "columns": column_names,
                "preview": preview_records,
                "totalRows": total_rows,
                "correlationId": correlation_id,
                "uploadedAt": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    
    return {
        "status": "ok",
        "columns": column_names,
        "preview": preview_records,
        "total_rows": total_rows,
        "checksum": checksum,
        "correlation_id": correlation_id,
    }

# --- Price list import: auto-detect column mapping (RU/EN) ---
# Rule for default unit when missing: use pack/фасовка text; if contains "кг" -> "кг", else "шт" (documented).

# Headers that must NOT be chosen as productName (code/supplier columns)
_NAME_EXCLUDE_HEADER_PARTS = ('код', 'артикул', 'поставщик', 'sku', 'id товара', 'код товара', 'товара поставщика')

# Column "Поставщик" (supplier name) must NEVER be used as article or name
_ARTICLE_EXCLUDE_HEADER_EXACT = ('поставщик', 'организация', 'company', 'companyname', 'supplier', 'наименование поставщика', 'код поставщика')
# Article must contain code-like keyword (so "Поставщик" alone does not match)
_ARTICLE_REQUIRE_IN_HEADER = ('код', 'артикул', 'sku', 'article')
# Headers that are supplier/company name only — exclude from article even if they substring-match an alias
_ARTICLE_EXCLUDE_HEADER_CONTAINS = ('поставщик',)  # "Поставщик" matches alias "код товара поставщика" via "c_lower in a"; exclude when header is only this

# productName: prefer "название"/"наименование"; exclude columns containing code/supplier keywords
_PRODUCT_NAME_PREFERRED = ('название', 'наименование', 'наименование товара')
_PRODUCT_NAME_ALSO = ('товар', 'позиция', 'product', 'productname', 'name')


def _price_list_column_aliases():
    return {
        'price': ['price', 'cost', 'цена', 'стоимость', 'цена за единицу', 'цена за ед'],
        'unit': ['unit', 'uom', 'ед', 'ед.', 'единица', 'единиц', 'измерение', 'ед. изм', 'единица измерения', 'ед.изм'],
        'article': ['код товара поставщика', 'код товара', 'код', 'артикул', 'sku', 'article'],
        'packQty': ['количество в упаковке', 'упаков', 'в упаковке', 'кол-во в упаковке', 'pack', 'packqty', 'pack_quantity', 'упаковка', 'фасовка', 'кратность'],
        'minOrderQty': ['минимальный заказ', 'мин', 'минимальный', 'min order', 'мин. заказ', 'мин заказ', 'minorder', 'minorderqty'],
    }


def _header_looks_like_code(col_lower: str) -> bool:
    """True if header should not be used as product name (code/supplier column)."""
    return any(part in col_lower for part in _NAME_EXCLUDE_HEADER_PARTS)


def _score_name_column(df, col: str, n_sample: int = 10) -> float:
    """Higher = better candidate for name: string-like, long text, few numeric-looking values."""
    if df is None or col not in df.columns:
        return 0.0
    import re
    numeric_re = re.compile(r'^\s*\d+(\.0)?\s*$')
    sample = df[col].dropna().head(n_sample)
    if len(sample) == 0:
        return 0.0
    lengths = [len(str(v).strip()) for v in sample]
    avg_len = sum(lengths) / len(lengths)
    num_like = sum(1 for v in sample if numeric_re.match(str(v).strip()))
    pct_numeric = num_like / len(sample)
    if pct_numeric > 0.9:
        return 0.0
    return avg_len * (1 - pct_numeric)


def _auto_detect_column_mapping(columns: List[str], df: Any = None) -> Dict[str, str]:
    """
    Match column headers to productName/price/unit/article/packQty/minOrderQty.
    productName: prefer "Название"/"Наименование", exclude code/supplier columns (Код товара поставщика, Поставщик).
    When df provided, use data heuristic for name: prefer column with long text and few numeric values.
    """
    aliases = _price_list_column_aliases()
    result = {}

    # 1) Map non-name columns by aliases
    for col in columns:
        c = str(col).strip()
        c_lower = c.lower()
        for key in ('price', 'unit', 'packQty', 'minOrderQty'):
            if key in result:
                continue
            for a in (_price_list_column_aliases()[key]):
                if a in c_lower or c_lower in a or (a.replace(' ', '') in c_lower.replace(' ', '')):
                    result[key] = col
                    break
        # article: only columns that look like code (код/артикул/sku); NEVER "Поставщик"
        # Match only when alias is contained IN column name (a in c_lower), not the reverse — else "Поставщик" would match alias "код товара поставщика"
        if 'article' not in result:
            if c_lower.strip() in _ARTICLE_EXCLUDE_HEADER_EXACT:
                continue
            if any(ex in c_lower for ex in _ARTICLE_EXCLUDE_HEADER_CONTAINS) and not any(part in c_lower for part in _ARTICLE_REQUIRE_IN_HEADER):
                continue
            if not any(part in c_lower for part in _ARTICLE_REQUIRE_IN_HEADER):
                continue
            for a in (_price_list_column_aliases()['article']):
                # Only match when alias is contained in column name (not column in alias), so "Поставщик" does not match alias "код товара поставщика"
                if a in c_lower or (a.replace(' ', '') in c_lower.replace(' ', '')):
                    result['article'] = col
                    break

    # 2) productName: only from columns that look like name AND not like code/supplier
    name_candidates = []
    for col in columns:
        c = str(col).strip()
        c_lower = c.lower()
        if _header_looks_like_code(c_lower):
            continue
        for a in _PRODUCT_NAME_PREFERRED:
            if a in c_lower or c_lower in a:
                name_candidates.append((col, 2))
                break
        else:
            for a in _PRODUCT_NAME_ALSO:
                if a in c_lower or c_lower in a:
                    name_candidates.append((col, 1))
                    break

    if name_candidates:
        if df is not None:
            scored = [(col, prio + _score_name_column(df, col) * 0.1) for col, prio in name_candidates]
            scored.sort(key=lambda x: -x[1])
            result['productName'] = scored[0][0]
        else:
            preferred = [c for c, p in name_candidates if p == 2]
            result['productName'] = preferred[0] if preferred else name_candidates[0][0]
    return result


def _parse_price_list_dataframe(contents: bytes, filename: str):
    """Parse CSV (UTF-8/cp1251, ; or ,) or Excel. Returns DataFrame."""
    fn = (filename or '').lower()
    if fn.endswith(('.xlsx', '.xls')):
        return pd.read_excel(io.BytesIO(contents))
    if fn.endswith('.csv'):
        for enc in ('utf-8', 'cp1251', 'latin1'):
            for sep in (';', ','):
                try:
                    return pd.read_csv(io.BytesIO(contents), sep=sep, encoding=enc)
                except Exception:
                    continue
        return pd.read_csv(io.BytesIO(contents))
    raise ValueError("Unsupported format")


def _normalize_price_value(price_raw: Any) -> Optional[float]:
    """Accept 2005, 2005.0, '2 005,00', '2005,00', '2005 ₽', '2005.0' etc. CSV-style numbers."""
    if price_raw is None or (isinstance(price_raw, float) and pd.isna(price_raw)):
        return None
    s = str(price_raw).strip().replace('\xa0', ' ').replace('\u202f', ' ')
    # Allow comma as decimal separator (e.g. 2005,00 or 2 005,00)
    s = s.replace(' ', '').replace(',', '.')
    s = re.sub(r'[^\d.]', '', s)
    if not s:
        return None
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


def _normalize_name_value(raw: Any) -> str:
    """Trim, collapse spaces, remove nbsp. For display as product name."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ''
    s = str(raw).strip().replace('\xa0', ' ').replace('\u202f', ' ')
    s = re.sub(r'\s+', ' ', s)
    return s


def _normalize_supplier_code(raw: Any) -> str:
    """If value is 2001.0 or '2001.0' -> '2001'. Otherwise trim string."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ''
    s = str(raw).strip()
    if re.match(r'^\d+\.0$', s):
        return s[:-2]
    if re.match(r'^\d+(\.0+)?$', s):
        return str(int(float(s)))
    return s


# Default unit rule (fixed, documented): when unit column is empty or invalid, infer from pack/фасовка
# (if text contains "кг" -> "кг"), else "шт". Normalize кг/kg, шт/pcs, л/l, г/гр.
_UNIT_NORMALIZE = {
    'шт': 'шт', 'шт.': 'шт', 'штук': 'шт', 'pcs': 'шт',
    'кг': 'кг', 'кг.': 'кг', 'kg': 'кг', 'г': 'г', 'гр': 'г',
    'л': 'л', 'л.': 'л', 'l': 'л', 'мл': 'л',
}


def _normalize_unit_value(raw: str) -> Optional[str]:
    """Return normalized unit (шт/кг/л/г) or None if invalid/empty."""
    if not raw or str(raw).strip() == '' or str(raw).lower() == 'nan':
        return None
    u = str(raw).strip().lower()
    return _UNIT_NORMALIZE.get(u, u) if u in _UNIT_NORMALIZE else u


def _default_unit_from_row(row: dict, df_columns: List[str], mapping: dict) -> str:
    """If unit column empty/invalid: use pack/фасовка (if contains 'кг' -> 'кг'), else 'шт'. Rule is fixed."""
    unit_col = mapping.get('unit')
    unit_val = ''
    if unit_col and unit_col in df_columns:
        unit_val = str(row.get(unit_col, '')).strip()
    if unit_val and unit_val != 'nan':
        normalized = _normalize_unit_value(unit_val)
        if normalized:
            return normalized
    pack_aliases = ['упаковка', 'фасовка', 'кратность', 'pack', 'packqty', 'в упаковке', 'кол-во в упаковке']
    for col in df_columns:
        col_lower = col.lower()
        if any(a in col_lower for a in pack_aliases):
            cell = str(row.get(col, '')).strip()
            if cell and 'кг' in cell.lower():
                return 'кг'
            break
    return 'шт'


@api_router.post("/price-lists/import")
async def import_price_list(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    P0-Compliant Price List Import.
    Form fields: file (required), replace (optional), column_mapping (optional).
    column_mapping is read from form so it is never required by validation; auto-detect when omitted.
    """
    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "validation_error",
                "message": "Не выбран файл. Выберите файл (xlsx или csv) и нажмите «Загрузить».",
                "endpoint": "/api/price-lists/import",
                "hint": "Отправьте multipart/form-data с полем file.",
            },
        )
    column_mapping = form.get("column_mapping")
    if column_mapping is not None and (not isinstance(column_mapping, str) or not column_mapping.strip()):
        column_mapping = None
    import json
    import unicodedata

    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")

    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    supplier_id = company['id']
    await _require_supplier_not_paused(supplier_id)
    supplier_name = company.get('companyName', company.get('name', 'Unknown'))
    correlation_id = str(uuid.uuid4())

    contents = await file.read()
    _MAX_IMPORT_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
    if len(contents) > _MAX_IMPORT_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "file_too_large",
                "message": f"Файл слишком большой (макс. {_MAX_IMPORT_FILE_BYTES // (1024*1024)} МБ). Уменьшите файл или разбейте на части.",
                "max_bytes": _MAX_IMPORT_FILE_BYTES,
                "received_bytes": len(contents),
            },
        )
    try:
        df = _parse_price_list_dataframe(contents, file.filename or '')
    except Exception as e:
        logger.warning(f"Parse price list file failed: {e}", extra={"correlation_id": correlation_id})
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")

    try:
        df_columns = [str(c).strip() for c in df.columns]

        mapping = None
        if column_mapping and column_mapping.strip():
            try:
                mapping = json.loads(column_mapping)
            except json.JSONDecodeError:
                pass
        if not mapping:
            mapping = _auto_detect_column_mapping(df_columns, df)
        if not mapping:
            mapping = {}

        # Debug/evidence: chosen mapping + preview first 5 rows (name, supplier_code)
        try:
            evidence_dir = ROOT_DIR.parent / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            name_col = mapping.get("productName")
            code_col = mapping.get("article")
            preview_rows = []
            for idx, row in df.head(5).iterrows():
                row_d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                name_val = str(row_d.get(name_col, "")).strip() if name_col else ""
                code_val = str(row_d.get(code_col, "")).strip() if code_col else ""
                preview_rows.append({"name": name_val[:80], "supplier_code": code_val[:30]})
            with open(evidence_dir / "PRICE_IMPORT_MAPPING_DEBUG.txt", "w", encoding="utf-8") as f:
                f.write(f"timestamp={datetime.now(timezone.utc).isoformat()}\n")
                f.write(f"mapping={mapping}\n")
                f.write("preview_first_5:\n")
                for i, r in enumerate(preview_rows):
                    f.write(f"  row{i}: name={r['name']!r} supplier_code={r['supplier_code']!r}\n")
        except Exception as e:
            logger.warning("Could not write import mapping evidence: %s", e)

        required_keys = ['productName', 'price', 'unit']
        missing = []
        for k in required_keys:
            col = mapping.get(k)
            if not col or str(col).strip() == '':
                missing.append(k)
            elif str(col).strip() not in df_columns:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error_code": "invalid_mapping",
                        "error": "invalid_mapping",
                        "message": f"Колонка «{col}» для «{k}» не найдена в файле.",
                        "correlation_id": correlation_id,
                        "columns": df_columns,
                    }
                )
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "missing_required_mapping",
                    "error": "missing_required_mapping",
                    "missing_fields": missing,
                    "columns": df_columns,
                    "message": "Не удалось определить колонки автоматически. Откройте «Расширенные настройки» и укажите Название/Цена/Единица.",
                    "correlation_id": correlation_id,
                }
            )

        new_pricelist_id = str(uuid.uuid4())

        # Helper functions for P0.1 unique key
        def normalize_text(text: str) -> str:
            if not text or pd.isna(text):
                return ""
            text = str(text).lower().strip()
            text = re.sub(r'\s+', ' ', text)
            text = unicodedata.normalize('NFKC', text)
            return text

        def get_unit_type(unit_str: str) -> str:
            unit_map = {
                'шт': 'PIECE', 'шт.': 'PIECE', 'штук': 'PIECE', 'pcs': 'PIECE',
                'кг': 'WEIGHT', 'кг.': 'WEIGHT', 'kg': 'WEIGHT', 'г': 'WEIGHT', 'гр': 'WEIGHT',
                'л': 'VOLUME', 'л.': 'VOLUME', 'мл': 'VOLUME', 'l': 'VOLUME', 'ml': 'VOLUME',
            }
            return unit_map.get(str(unit_str).lower().strip(), 'PIECE')

        def get_unit_norm(unit_str: str) -> str:
            norm_map = {
                'шт': 'pcs', 'шт.': 'pcs', 'штук': 'pcs', 'pcs': 'pcs',
                'кг': 'kg', 'кг.': 'kg', 'kg': 'kg', 'г': 'kg', 'гр': 'kg',
                'л': 'l', 'л.': 'l', 'мл': 'l', 'l': 'l', 'ml': 'l',
            }
            return norm_map.get(str(unit_str).lower().strip(), 'pcs')

        def generate_unique_key(article, product_name, unit_type):
            if article and str(article).strip() and str(article).strip() != 'nan':
                return f"{supplier_id}:{str(article).strip()}"
            norm_name = normalize_text(product_name)
            return f"{supplier_id}:{norm_name}:{unit_type}"

        # Import products with upsert (P0.1). Diagnostics: why rows were skipped.
        created_count = 0
        updated_count = 0
        skipped_count = 0
        skipped_reasons = {
            "empty_name": 0,
            "price_parse_failed": 0,
            "price_le_zero": 0,
            "empty_or_invalid_unit": 0,
            "other": 0,
        }
        total_rows_read = len(df)

        for _, row in df.iterrows():
            try:
                row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                col_name = mapping.get('productName')
                product_name = _normalize_name_value(row_dict.get(col_name, '')) if col_name else ''
                price_raw = row_dict.get(mapping.get('price'), 0)
                unit_str = _default_unit_from_row(row_dict, df_columns, mapping)
                article_col = mapping.get('article')
                article_raw = str(row_dict.get(article_col, '')).strip() if (article_col and article_col in df_columns) else None
                article = _normalize_supplier_code(article_raw) if article_raw and article_raw != 'nan' else None

                if not product_name or product_name == 'nan':
                    skipped_count += 1
                    skipped_reasons["empty_name"] += 1
                    continue

                price = _normalize_price_value(price_raw)
                if price is None:
                    skipped_count += 1
                    skipped_reasons["price_parse_failed"] += 1
                    continue
                if price <= 0:
                    skipped_count += 1
                    skipped_reasons["price_le_zero"] += 1
                    continue

                min_order_qty = 1
                if mapping.get('minOrderQty') and mapping['minOrderQty'] in df_columns:
                    try:
                        min_order_qty = max(1, int(float(row_dict.get(mapping['minOrderQty'], 1))))
                    except (ValueError, TypeError):
                        pass

                pack_qty = 1
                if mapping.get('packQty') and mapping['packQty'] in df_columns:
                    try:
                        pack_qty = max(1, int(float(row_dict.get(mapping['packQty'], 1))))
                    except (ValueError, TypeError):
                        pass

                unit_type = get_unit_type(unit_str)
                unit_norm = get_unit_norm(unit_str)
                if unit_norm == 'pcs':
                    unit_norm = 'шт'
                elif unit_norm == 'kg':
                    unit_norm = 'кг'
                elif unit_norm == 'l':
                    unit_norm = 'л'

                unique_key = generate_unique_key(article, product_name, unit_type)

                item_data = {
                    'unique_key': unique_key,
                    'supplier_company_id': supplier_id,
                    'supplierCompanyId': supplier_id,
                    'price_list_id': new_pricelist_id,
                    'supplier_item_code': article or '',
                    'name_raw': product_name,
                    'name_norm': normalize_text(product_name),
                    'unit_supplier': unit_str,
                    'unit_norm': unit_norm,
                    'unit_type': unit_type,
                    'price': price,
                    'pack_qty': pack_qty,
                    'min_order_qty': min_order_qty,
                    'active': True,
                    'updated_at': datetime.now(timezone.utc),
                }

                existing = await db.supplier_items.find_one({'unique_key': unique_key})
                if existing:
                    await db.supplier_items.update_one(
                        {'unique_key': unique_key},
                        {'$set': item_data}
                    )
                    updated_count += 1
                else:
                    item_data['id'] = str(uuid.uuid4())
                    item_data['created_at'] = datetime.now(timezone.utc)
                    await db.supplier_items.insert_one(item_data)
                    created_count += 1
            except Exception as e:
                logger.warning(f"Error importing row: {e}")
                skipped_count += 1
                skipped_reasons["other"] += 1

        # P0.2: Deactivate old items from this supplier (not in new pricelist)
        deactivate_result = await db.supplier_items.update_many(
            {
                'supplier_company_id': supplier_id,
                'price_list_id': {'$ne': new_pricelist_id},
                'active': True
            },
            {'$set': {'active': False, 'deactivated_at': datetime.now(timezone.utc)}}
        )
        deactivated_count = deactivate_result.modified_count

        pricelist_meta = {
            'id': new_pricelist_id,
            'supplierId': supplier_id,
            'supplierName': supplier_name,
            'fileName': file.filename,
            'itemsCount': created_count + updated_count,
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'active': True,
        }
        await db.pricelists.insert_one(pricelist_meta)

        imported_count = created_count + updated_count
        logger.info(
            "Price list import completed",
            extra={
                "correlation_id": correlation_id,
                "supplier_id": supplier_id,
                "importedCount": imported_count,
                "created": created_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "skipped_reasons": skipped_reasons,
                "deactivated": deactivated_count,
            }
        )

        if imported_count == 0:
            # User-friendly diagnostic: why rows were rejected
            parts = [
                f"Прочитано строк: {total_rows_read}.",
                f"Импортировано: 0.",
                f"Отброшено: {skipped_count} — пустое название: {skipped_reasons.get('empty_name', 0)}, не распарсилась цена: {skipped_reasons.get('price_parse_failed', 0)}, цена ≤ 0: {skipped_reasons.get('price_le_zero', 0)}, единица: {skipped_reasons.get('empty_or_invalid_unit', 0)}, прочее: {skipped_reasons.get('other', 0)}.",
            ]
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "no_rows_imported",
                    "error": "no_rows_imported",
                    "message": "Не удалось импортировать ни одной строки. Откройте «Расширенные настройки» и уточните колонки.",
                    "diagnostic_summary": " ".join(parts),
                    "rows_read": total_rows_read,
                    "rows_imported": 0,
                    "rows_skipped_total": skipped_count,
                    "skipped_reasons": skipped_reasons,
                    "importedCount": 0,
                    "total_rows_read": total_rows_read,
                    "skipped": skipped_count,
                    "correlation_id": correlation_id,
                    "columns": df_columns,
                }
            )

        return {
            "message": f"Successfully imported {imported_count} products",
            "importedCount": imported_count,
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "skipped_reasons": skipped_reasons,
            "total_rows_read": total_rows_read,
            "deactivated": deactivated_count,
            "pricelist_id": new_pricelist_id,
            "errors": [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import failed", extra={"correlation_id": correlation_id, "supplier_id": supplier_id})
        raise HTTPException(status_code=400, detail={"error": "import_failed", "message": str(e), "correlation_id": correlation_id})


# P0.6: Safe pricelist deactivation/deletion endpoints
@api_router.post("/price-lists/{pricelist_id}/deactivate")
async def deactivate_pricelist(
    pricelist_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    P0.6: Safely deactivate a pricelist and all its items.
    Does NOT delete data - just marks as inactive.
    """
    if current_user['role'] not in [UserRole.supplier, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify pricelist exists
    pricelist = await db.pricelists.find_one({'id': pricelist_id})
    if not pricelist:
        raise HTTPException(status_code=404, detail="Pricelist not found")
    
    # If supplier, verify ownership
    if current_user['role'] == UserRole.supplier:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        if not company or company['id'] != pricelist.get('supplierId'):
            raise HTTPException(status_code=403, detail="Not authorized to modify this pricelist")
    
    # Deactivate all items from this pricelist
    items_result = await db.supplier_items.update_many(
        {'price_list_id': pricelist_id, 'active': True},
        {'$set': {'active': False, 'deactivated_at': datetime.now(timezone.utc)}}
    )
    
    # Deactivate pricelist metadata
    await db.pricelists.update_one(
        {'id': pricelist_id},
        {'$set': {'active': False, 'deactivatedAt': datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "message": f"Pricelist {pricelist_id} deactivated",
        "items_deactivated": items_result.modified_count
    }


@api_router.delete("/price-lists/{pricelist_id}")
async def delete_pricelist(
    pricelist_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    P0.6: Permanently delete a pricelist and all its items.
    WARNING: This action cannot be undone!
    """
    if current_user['role'] != UserRole.admin:
        raise HTTPException(status_code=403, detail="Only admins can delete pricelists")
    
    # Verify pricelist exists
    pricelist = await db.pricelists.find_one({'id': pricelist_id})
    if not pricelist:
        raise HTTPException(status_code=404, detail="Pricelist not found")
    
    # Delete all items from this pricelist
    items_result = await db.supplier_items.delete_many({'price_list_id': pricelist_id})
    
    # Delete pricelist metadata
    await db.pricelists.delete_one({'id': pricelist_id})
    
    return {
        "message": f"Pricelist {pricelist_id} permanently deleted",
        "items_deleted": items_result.deleted_count
    }


@api_router.get("/price-lists/supplier/{supplier_id}")
async def get_supplier_pricelists(
    supplier_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all pricelists for a supplier (for management UI)"""
    pricelists = await db.pricelists.find(
        {'supplierId': supplier_id},
        {'_id': 0}
    ).sort('createdAt', -1).to_list(100)
    
    # Add item counts
    for pl in pricelists:
        active_count = await db.supplier_items.count_documents({
            'price_list_id': pl['id'],
            'active': True
        })
        total_count = await db.supplier_items.count_documents({
            'price_list_id': pl['id']
        })
        pl['activeItemsCount'] = active_count
        pl['totalItemsCount'] = total_count
    
    return pricelists

# ==================== CUSTOMER CONTRACT SUPPLIERS ====================

@api_router.get("/customer/contract-suppliers")
async def get_contract_suppliers(current_user: dict = Depends(get_current_user)):
    """List suppliers for 'Статус договоров с поставщиками'. Source = companies(type=supplier) only.
    Status from supplier_restaurant_settings. No junk — only real supplier companies."""
    if current_user['role'] != UserRole.customer:
        raise HTTPException(status_code=403, detail="Not authorized")
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
    if not company:
        return []
    restaurant_id = company['id']
    # Source: ONLY companies with type=supplier (real suppliers in system)
    suppliers = await db.companies.find(
        {"type": "supplier"},
        {"_id": 0, "id": 1, "companyName": 1, "inn": 1}
    ).to_list(500)
    links = await db.supplier_restaurant_settings.find(
        {"restaurantId": restaurant_id},
        {"_id": 0, "supplierId": 1, "contract_accepted": 1}
    ).to_list(500)
    link_map = {l['supplierId']: l for l in links}
    result = []
    for s in suppliers:
        link = link_map.get(s['id'])
        status = "accepted" if (link and link.get("contract_accepted")) else "pending"
        result.append({
            "supplierId": s['id'],
            "supplierName": s.get('companyName', s.get('name', 'N/A')),
            "inn": s.get('inn', ''),
            "contractStatus": status
        })
    return result


# ==================== DOCUMENT ROUTES ====================

@api_router.get("/documents/my", response_model=List[Document])
async def get_my_documents(current_user: dict = Depends(get_current_user)):
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    documents = await db.documents.find({"companyId": company['id']}, {"_id": 0}).to_list(1000)
    return documents

@api_router.post("/documents/upload", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    edo: Optional[str] = Form(None),
    guid: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if edo or guid:
        upd = {"updatedAt": datetime.now(timezone.utc).isoformat()}
        if edo is not None:
            upd["edoNumber"] = edo.strip() or None
        if guid is not None:
            upd["guid"] = guid.strip() or None
        if len(upd) > 1:
            await db.companies.update_one({"id": company["id"]}, {"$set": upd})
    
    # Save file
    file_id = str(uuid.uuid4())
    file_extension = file.filename.split('.')[-1]
    file_name = f"{file_id}.{file_extension}"
    file_path = UPLOAD_DIR / file_name
    
    with open(file_path, 'wb') as f:
        contents = await file.read()
        f.write(contents)
    
    # Create document record
    document = Document(
        companyId=company['id'],
        type=document_type,
        fileUrl=f"/uploads/{file_name}",
        status=DocumentStatus.uploaded
    )
    doc_dict = document.model_dump()
    doc_dict['createdAt'] = doc_dict['createdAt'].isoformat()
    await db.documents.insert_one(doc_dict)

    # Auto-accept contract (dev/local only, when flag is set)
    auto_accept = os.environ.get('AUTO_ACCEPT_CONTRACTS', '').strip() == '1' or \
                  os.environ.get('BESTPRICE_AUTO_ACCEPT_CONTRACTS', '').strip() == '1'
    env_val = os.environ.get('ENV', 'production').lower()
    is_dev = env_val in ('development', 'local', 'dev', '') or 'local' in db_name or 'test' in db_name
    if auto_accept and is_dev:
        suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0, "id": 1}).to_list(500)
        now = datetime.now(timezone.utc).isoformat()
        for s in suppliers:
            await db.supplier_restaurant_settings.update_one(
                {"supplierId": s["id"], "restaurantId": company["id"]},
                {"$set": {
                    "contract_accepted": True,
                    "is_paused": False,
                    "ordersEnabled": True,
                    "updatedAt": now
                }},
                upsert=True
            )

    return document


@api_router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download document. ACL: restaurant's own doc OR supplier linked to restaurant (supplier_restaurant_settings)."""
    doc = await db.documents.find_one({"id": document_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    restaurant_id = doc.get("companyId")
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Restaurant (customer) can download own documents
    if current_user.get("role") == UserRole.customer:
        company = await db.companies.find_one({"userId": current_user["id"]}, {"_id": 0, "id": 1})
        if company and company["id"] == restaurant_id:
            file_url = doc.get("fileUrl", "")
            if file_url.startswith("/uploads/"):
                filename = file_url.split("/")[-1]
                file_path = UPLOAD_DIR / filename
                if file_path.exists():
                    return FileResponse(path=str(file_path), filename=filename)
        raise HTTPException(status_code=403, detail="No access to this document")

    # Supplier can download only if linked to restaurant
    if current_user.get("role") == UserRole.supplier:
        supplier_id = current_user.get("companyId")
        if not supplier_id:
            company = await db.companies.find_one({"userId": current_user["id"]}, {"_id": 0, "id": 1})
            supplier_id = company["id"] if company else None
        if not supplier_id:
            raise HTTPException(status_code=403, detail="No access to this document")
        link = await db.supplier_restaurant_settings.find_one(
            {"supplierId": supplier_id, "restaurantId": restaurant_id, "contract_accepted": True},
            {"_id": 0}
        )
        if link:
            file_url = doc.get("fileUrl", "")
            if file_url.startswith("/uploads/"):
                filename = file_url.split("/")[-1]
                file_path = UPLOAD_DIR / filename
                if file_path.exists():
                    return FileResponse(path=str(file_path), filename=filename)
        raise HTTPException(status_code=403, detail="No access to this document")

    raise HTTPException(status_code=403, detail="Not authenticated")


# ==================== ORDER ROUTES ====================

@api_router.get("/orders/my", response_model=List[Order])
async def get_my_orders(current_user: dict = Depends(get_current_user)):
    # Get company ID based on user role
    if current_user['role'] in [UserRole.responsible, UserRole.chef, UserRole.supplier]:
        # These roles have companyId directly in user document
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    if current_user['role'] == UserRole.supplier:
        orders = await db.orders.find({"supplierCompanyId": company_id}, {"_id": 0}).to_list(1000)
    else:
        orders = await db.orders.find({"customerCompanyId": company_id}, {"_id": 0}).to_list(1000)
    
    return orders

@api_router.post("/orders", response_model=Order)
async def create_order(data: OrderCreate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.customer:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    if await _restaurant_is_paused(data.supplierCompanyId, company['id']):
        raise HTTPException(
            status_code=403,
            detail="Поставщик поставил ваш ресторан на паузу. Отгрузка временно недоступна."
        )
    
    order = Order(
        customerCompanyId=company['id'],
        supplierCompanyId=data.supplierCompanyId,
        amount=data.amount,
        orderDetails=data.orderDetails,
        deliveryAddress=data.deliveryAddress
    )
    order_dict = order.model_dump()
    order_dict['orderDate'] = order_dict['orderDate'].isoformat()
    order_dict['createdAt'] = order_dict['createdAt'].isoformat()
    await db.orders.insert_one(order_dict)
    
    return order

@api_router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str, current_user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get company ID based on user role
    if current_user['role'] in [UserRole.responsible, UserRole.chef, UserRole.supplier]:
        # These roles have companyId directly in user document
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Check if user has access to this order
    if order['customerCompanyId'] != company_id and order['supplierCompanyId'] != company_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return order


@api_router.get("/orders/{order_id}/details")
async def get_order_details(order_id: str, current_user: dict = Depends(get_current_user)):
    """Get order with supplier name and detailed breakdown"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get supplier name
    supplier = await db.companies.find_one({"id": order['supplierCompanyId']}, {"_id": 0})
    supplier_name = supplier.get('companyName') or supplier.get('name', 'Unknown') if supplier else 'Unknown'
    
    return {
        **order,
        "supplierName": supplier_name
    }

# ==================== ANALYTICS ROUTES ====================

@api_router.delete("/orders/{order_id}")
async def delete_order(order_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a single order"""
    # Get order first to verify ownership
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get company ID
    if current_user['role'] in [UserRole.responsible, UserRole.chef, UserRole.supplier]:
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Verify order belongs to this company
    if order['customerCompanyId'] != company_id and order['supplierCompanyId'] != company_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Delete order
    await db.orders.delete_one({"id": order_id})
    
    return {"message": "Order deleted successfully"}

@api_router.delete("/orders/all/delete")
async def delete_all_orders(current_user: dict = Depends(get_current_user)):
    """Delete all orders for current user's company"""
    # Get company ID
    if current_user['role'] in [UserRole.responsible, UserRole.chef, UserRole.supplier]:
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Delete all orders for this company (as customer or supplier)
    result = await db.orders.delete_many({
        "$or": [
            {"customerCompanyId": company_id},
            {"supplierCompanyId": company_id}
        ]
    })
    
    return {
        "message": f"Deleted {result.deleted_count} orders",
        "deleted_count": result.deleted_count
    }

# ==================== ANALYTICS ROUTES ====================

@api_router.get("/analytics/customer")
async def get_customer_analytics(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.customer:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    orders = await db.orders.find({"customerCompanyId": company['id']}, {"_id": 0}).to_list(1000)
    
    total_orders = len(orders)
    
    # Get all products and suppliers
    all_products = await db.price_lists.find({}, {"_id": 0}).to_list(10000)
    
    # Calculate CORRECT BestPrice value using MVP baseline formula
    # Baseline = 50% best supplier + 50% third supplier
    from order_optimizer import calculate_baseline_price
    
    baseline_total = 0  # What customer would pay without BestPrice
    actual_total = 0    # What customer actually paid with BestPrice
    
    for order in orders:
        for item in order.get('orderDetails', []):
            actual_item_cost = item['price'] * item['quantity']
            actual_total += actual_item_cost
            
            # Find ALL suppliers offering this product
            matching_pricelists = await db.pricelists.find(
                {"productId": item.get('productId')},
                {"_id": 0, "price": 1}
            ).to_list(100)
            
            if matching_pricelists:
                prices = [p['price'] for p in matching_pricelists]
                baseline_price = calculate_baseline_price(prices)
                baseline_item_cost = baseline_price * item['quantity']
                baseline_total += baseline_item_cost
            else:
                # Product not in catalog, use actual price as baseline
                baseline_total += actual_item_cost
    
    # Calculate savings (baseline - actual)
    savings = baseline_total - actual_total
    savings_percentage = (savings / baseline_total * 100) if baseline_total > 0 else 0
    
    # Get orders by status
    orders_by_status = {
        "new": sum(1 for o in orders if o['status'] == 'new'),
        "confirmed": sum(1 for o in orders if o['status'] == 'confirmed'),
        "declined": sum(1 for o in orders if o['status'] == 'declined'),
        "partial": sum(1 for o in orders if o['status'] == 'partial')
    }
    
    # Recent orders
    recent_orders = sorted(orders, key=lambda x: x['orderDate'], reverse=True)[:5]
    
    return {
        "totalOrders": total_orders,
        "totalAmount": actual_total,
        "savings": savings,
        "savingsPercentage": savings_percentage,
        "baselineTotal": baseline_total,
        "actualTotal": actual_total,
        "ordersByStatus": orders_by_status,
        "recentOrders": recent_orders
    }

# ==================== SUPPLIER ROUTES ====================

@api_router.get("/suppliers")
async def get_suppliers():
    # Query for suppliers with either field name
    suppliers = await db.companies.find(
        {"$or": [{"companyType": "supplier"}, {"type": "supplier"}]},
        {"_id": 0}
    ).to_list(1000)
    
    logging.info(f"Found {len(suppliers)} suppliers in database")
    
    # Map to expected frontend format
    result = []
    for s in suppliers:
        result.append({
            "id": s['id'],
            "companyName": s.get('companyName') or s.get('name', 'Unknown'),
            "type": "supplier",
            "createdAt": s.get('createdAt', datetime.now(timezone.utc).isoformat())
        })
    
    logging.info(f"Returning {len(result)} suppliers")
    return result

@api_router.get("/suppliers/{supplier_id}/price-lists")
async def get_supplier_price_lists(supplier_id: str, search: Optional[str] = None):
    """Get supplier price list items from supplier_items (catalog for customers)."""
    if await _supplier_is_paused(supplier_id):
        return []
    query = {"supplier_company_id": supplier_id, "active": True}
    items = await db.supplier_items.find(query, {"_id": 0}).to_list(10000)
    result = []
    for si in items:
        price = float(si.get("price", 0))
        if price <= 0:
            continue
        name = si.get("name_raw", "")
        if search:
            search_lower = search.lower().strip()
            name_lower = name.lower()
            if search_lower not in name_lower:
                typo_map = {
                    "ласось": "лосось", "лососс": "лосось", "лососк": "лосось", "лосос": "лосось",
                    "сибасс": "сибас", "сибаса": "сибас", "дорада": "дорадо", "креветка": "креветки", "креветк": "креветки",
                }
                replaced = name_lower
                for typo, correct in typo_map.items():
                    if typo in search_lower:
                        replaced = search_lower.replace(typo, correct)
                        break
                if replaced not in name_lower and search_lower not in name_lower:
                    continue
        created = si.get("created_at") or si.get("updated_at")
        updated = si.get("updated_at") or created
        result.append({
            "id": si.get("id", si.get("unique_key", "")),
            "productId": si.get("id", si.get("unique_key", "")),
            "supplierCompanyId": si.get("supplier_company_id", supplier_id),
            "productName": name,
            "article": si.get("supplier_item_code", ""),
            "price": price,
            "unit": si.get("unit_supplier", si.get("unit_norm", "шт")),
            "minQuantity": int(si.get("min_order_qty", 1)),
            "availability": True,
            "active": True,
            "createdAt": created.isoformat() if hasattr(created, "isoformat") else str(created),
            "updatedAt": updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
        })
    return result


# ==================== MOBILE APP ROUTES ====================

@api_router.get("/mobile/positions", response_model=List[RestaurantPosition])
async def get_restaurant_positions(current_user: dict = Depends(get_current_user)):
    """Get restaurant's position catalog for mobile ordering"""
    if current_user['role'] not in [UserRole.customer, UserRole.responsible]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get company ID from user or directly from responsible role
    if current_user['role'] == UserRole.responsible:
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    positions = await db.restaurant_positions.find(
        {"restaurantCompanyId": company_id}, 
        {"_id": 0}
    ).to_list(1000)
    
    return positions

class MobileOrderPreviewRequest(BaseModel):
    items: List[dict]  # [{"position_number": "15", "qty": 3}, ...]

@api_router.post("/mobile/orders/preview")
async def preview_mobile_order(data: MobileOrderPreviewRequest, current_user: dict = Depends(get_current_user)):
    """Preview order from position numbers"""
    if current_user['role'] not in [UserRole.customer, UserRole.responsible]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get company ID
    if current_user['role'] == UserRole.responsible:
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get all products and positions
    all_products = await db.price_lists.find({"active": True}, {"_id": 0}).to_list(10000)
    positions = await db.restaurant_positions.find(
        {"restaurantCompanyId": company_id}, 
        {"_id": 0}
    ).to_list(1000)
    
    # Build position map
    position_map = {p['positionNumber']: p for p in positions}
    
    resolved_items = []
    errors = []
    warnings = []
    total_amount = 0
    
    for item in data.items:
        pos_num = str(item.get('position_number', ''))
        qty = float(item.get('qty', 0))
        
        if not pos_num or qty <= 0:
            errors.append(f"Invalid item: position={pos_num}, qty={qty}")
            continue
        
        # Find position in restaurant catalog
        position = position_map.get(pos_num)
        if not position:
            errors.append(f"Position {pos_num} not found in catalog")
            continue
        
        # Find all suppliers offering this product
        product_offers = [p for p in all_products 
                         if p['productName'].lower() == position['productName'].lower() 
                         and p['unit'].lower() == position['unit'].lower()]
        
        if not product_offers:
            errors.append(f"Position {pos_num} ({position['productName']}) - no suppliers found")
            continue
        
        # Select cheapest supplier
        best_offer = min(product_offers, key=lambda x: x['price'])
        
        # Check minimum quantity
        min_qty = best_offer.get('minQuantity', 1)
        if qty < min_qty:
            warnings.append(f"Position {pos_num}: minimum order is {min_qty} {position['unit']}, adjusted from {qty}")
            qty = min_qty
        
        # Get supplier name
        supplier = await db.companies.find_one({"id": best_offer['supplierCompanyId']}, {"_id": 0})
        
        item_total = best_offer['price'] * qty
        total_amount += item_total
        
        resolved_items.append({
            "position_number": pos_num,
            "product_name": position['productName'],
            "qty": qty,
            "unit": position['unit'],
            "supplier_name": supplier['companyName'] if supplier else 'Unknown',
            "supplier_id": best_offer['supplierCompanyId'],
            "price_per_unit": best_offer['price'],
            "total": item_total,
            "product_id": position['productId'],
            "article": best_offer.get('article', '')
        })
    
    return {
        "positions": resolved_items,
        "total_amount": total_amount,
        "warnings": warnings,
        "errors": errors
    }

class MobileOrderConfirmRequest(BaseModel):
    items: List[dict]  # Same as preview

@api_router.post("/mobile/orders/confirm")
async def confirm_mobile_order(data: MobileOrderConfirmRequest, current_user: dict = Depends(get_current_user)):
    """Confirm and create orders from mobile app"""
    if current_user['role'] not in [UserRole.customer, UserRole.responsible]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get company ID
    if current_user['role'] == UserRole.responsible:
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Re-run preview logic to get resolved items
    preview_response = await preview_mobile_order(
        MobileOrderPreviewRequest(items=data.items),
        current_user
    )
    
    if preview_response['errors']:
        raise HTTPException(status_code=400, detail=f"Cannot create order: {preview_response['errors']}")
    
    # Group items by supplier
    items_by_supplier = {}
    for item in preview_response['positions']:
        supplier_id = item['supplier_id']
        if supplier_id not in items_by_supplier:
            items_by_supplier[supplier_id] = []
        
        items_by_supplier[supplier_id].append({
            'productName': item['product_name'],
            'article': item['article'],
            'quantity': item['qty'],
            'price': item['price_per_unit'],
            'unit': item['unit']
        })
    
    # Create orders (one per supplier)
    for supplier_id in items_by_supplier:
        if await _restaurant_is_paused(supplier_id, company_id):
            raise HTTPException(
                status_code=403,
                detail="Поставщик поставил ваш ресторан на паузу. Отгрузка временно недоступна."
            )
    created_orders = []
    
    for supplier_id, items in items_by_supplier.items():
        amount = sum(item['price'] * item['quantity'] for item in items)
        
        order = Order(
            customerCompanyId=company_id,
            supplierCompanyId=supplier_id,
            amount=amount,
            orderDetails=items,
            deliveryAddress=None  # Mobile orders don't specify delivery address initially
        )
        
        order_dict = order.model_dump()
        order_dict['orderDate'] = order_dict['orderDate'].isoformat()
        order_dict['createdAt'] = order_dict['createdAt'].isoformat()
        
        await db.orders.insert_one(order_dict)
        created_orders.append(order_dict['id'])
    
    return {
        "order_ids": created_orders,
        "total_orders": len(created_orders),
        "total_amount": preview_response['total_amount']
    }


# ==================== MATRIX ROUTES ====================

@api_router.post("/matrices", response_model=Matrix)
async def create_matrix(data: MatrixCreate, current_user: dict = Depends(get_current_user)):
    """Admin creates a new product matrix for a restaurant"""
    if current_user['role'] not in [UserRole.customer, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only admins can create matrices")
    
    # Verify the restaurant company belongs to this admin
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company or company['id'] != data.restaurantCompanyId:
        raise HTTPException(status_code=403, detail="Can only create matrices for your own restaurant")
    
    matrix = Matrix(**data.model_dump())
    matrix_dict = matrix.model_dump()
    matrix_dict['createdAt'] = matrix_dict['createdAt'].isoformat()
    matrix_dict['updatedAt'] = matrix_dict['updatedAt'].isoformat()
    await db.matrices.insert_one(matrix_dict)
    
    return matrix

@api_router.get("/matrices", response_model=List[Matrix])
async def get_matrices(current_user: dict = Depends(get_current_user)):
    """Get all matrices for current user's restaurant"""
    if current_user['role'] == UserRole.chef or current_user['role'] == UserRole.responsible:
        # Chef/Staff: Get their assigned matrix
        user = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
        if not user or not user.get('matrixId'):
            return []
        matrices = await db.matrices.find({"id": user['matrixId']}, {"_id": 0}).to_list(1)
        return matrices
    else:
        # Admin: Get all matrices for their restaurant
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        if not company:
            return []
        matrices = await db.matrices.find({"restaurantCompanyId": company['id']}, {"_id": 0}).to_list(100)
        return matrices

@api_router.get("/matrices/{matrix_id}", response_model=Matrix)
async def get_matrix(matrix_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific matrix"""
    matrix = await db.matrices.find_one({"id": matrix_id}, {"_id": 0})
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    
    # Verify access
    if current_user['role'] in [UserRole.chef, UserRole.responsible]:
        user = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
        if not user or user.get('matrixId') != matrix_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this matrix")
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        if not company or matrix['restaurantCompanyId'] != company['id']:
            raise HTTPException(status_code=403, detail="Not authorized to view this matrix")
    
    return matrix

@api_router.delete("/matrices/{matrix_id}")
async def delete_matrix(matrix_id: str, current_user: dict = Depends(get_current_user)):
    """Admin deletes a matrix"""
    if current_user['role'] not in [UserRole.customer, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only admins can delete matrices")
    
    matrix = await db.matrices.find_one({"id": matrix_id}, {"_id": 0})
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    
    # Verify ownership
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company or matrix['restaurantCompanyId'] != company['id']:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Delete matrix and all its products
    await db.matrices.delete_one({"id": matrix_id})
    await db.matrix_products.delete_many({"matrixId": matrix_id})
    
    return {"message": "Matrix deleted successfully"}

# Matrix Products Management

@api_router.get("/matrices/{matrix_id}/products")
async def get_matrix_products(matrix_id: str, current_user: dict = Depends(get_current_user)):
    """Get all products in a matrix"""
    # Verify access to matrix
    matrix = await db.matrices.find_one({"id": matrix_id}, {"_id": 0})
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    
    # Get matrix products
    matrix_products = await db.matrix_products.find(
        {"matrixId": matrix_id}, 
        {"_id": 0}
    ).sort("rowNumber", 1).to_list(1000)
    
    # Enrich with current pricing from all suppliers
    enriched_products = []
    for mp in matrix_products:
        # Get product details
        product = await db.products.find_one({"id": mp['productId']}, {"_id": 0})
        if not product:
            continue
        
        # Get all supplier prices for this product
        pricelists = await db.pricelists.find({"productId": mp['productId']}, {"_id": 0}).to_list(100)
        
        # Get supplier details
        suppliers_data = []
        for pl in pricelists:
            supplier = await db.companies.find_one({"id": pl['supplierId']}, {"_id": 0})
            if supplier:
                suppliers_data.append({
                    "supplierId": pl['supplierId'],
                    "supplierName": supplier['name'],
                    "price": pl['price'],
                    "minQuantity": pl.get('minQuantity', 1),
                    "packQuantity": pl.get('packQuantity', 1)
                })
        
        # Sort by price
        suppliers_data.sort(key=lambda x: x['price'])
        
        enriched_products.append({
            **mp,
            "globalProductName": product['name'],
            "suppliers": suppliers_data,
            "bestPrice": suppliers_data[0]['price'] if suppliers_data else None,
            "bestSupplier": suppliers_data[0]['supplierName'] if suppliers_data else None
        })
    
    return enriched_products

@api_router.post("/matrices/{matrix_id}/products", response_model=MatrixProduct)
async def add_product_to_matrix(
    matrix_id: str, 
    data: MatrixProductCreate, 
    current_user: dict = Depends(get_current_user)
):
    """Add a product to a matrix (Admin or Chef/Staff)"""
    from product_intent_parser import extract_product_intent
    
    # Verify access
    matrix = await db.matrices.find_one({"id": matrix_id}, {"_id": 0})
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    
    if current_user['role'] in [UserRole.chef, UserRole.responsible]:
        user = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
        if not user or user.get('matrixId') != matrix_id:
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        if not company or matrix['restaurantCompanyId'] != company['id']:
            raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get product details
    product = await db.products.find_one({"id": data.productId}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get next row number
    existing_products = await db.matrix_products.find(
        {"matrixId": matrix_id}, 
        {"_id": 0, "rowNumber": 1}
    ).sort("rowNumber", -1).limit(1).to_list(1)
    
    next_row = 1
    if existing_products:
        next_row = existing_products[0]['rowNumber'] + 1
    
    # Get product code from pricelist
    pricelist = await db.pricelists.find_one({"productId": data.productId}, {"_id": 0})
    product_code = pricelist.get('supplierItemCode', '') if pricelist else ''
    
    # Extract product intent (for potential CHEAPEST mode)
    intent = extract_product_intent(product['name'], product['unit'])
    
    # Create matrix product
    matrix_product = {
        "id": str(uuid.uuid4()),
        "matrixId": matrix_id,
        "rowNumber": next_row,
        "productId": data.productId,
        "productName": data.productName if data.productName else product['name'],
        "productCode": data.productCode if data.productCode else product_code,
        "unit": product['unit'],
        "mode": data.mode,  # "exact" or "cheapest"
        "productType": intent.get('productType'),
        "baseUnit": intent.get('baseUnit'),
        "keyAttributes": intent.get('keyAttributes'),
        "brand": intent.get('brand'),
        "strictBrand": False,
        "lastOrderQuantity": None,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    
    await db.matrix_products.insert_one(matrix_product)
    return matrix_product

@api_router.put("/matrices/{matrix_id}/products/{product_id}", response_model=MatrixProduct)
async def update_matrix_product(
    matrix_id: str,
    product_id: str,
    data: MatrixProductUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a product in the matrix (Admin only - for renaming)"""
    if current_user['role'] not in [UserRole.customer, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only admins can edit matrix products")
    
    # Verify access
    matrix = await db.matrices.find_one({"id": matrix_id}, {"_id": 0})
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company or matrix['restaurantCompanyId'] != company['id']:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Update
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    
    result = await db.matrix_products.update_one(
        {"id": product_id, "matrixId": matrix_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Matrix product not found")
    
    updated_product = await db.matrix_products.find_one({"id": product_id}, {"_id": 0})
    return updated_product

@api_router.delete("/matrices/{matrix_id}/products/{product_id}")
async def remove_product_from_matrix(
    matrix_id: str,
    product_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove a product from the matrix (Admin only)"""
    if current_user['role'] not in [UserRole.customer, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only admins can remove products")
    
    # Verify access
    matrix = await db.matrices.find_one({"id": matrix_id}, {"_id": 0})
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company or matrix['restaurantCompanyId'] != company['id']:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    result = await db.matrix_products.delete_one({"id": product_id, "matrixId": matrix_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Matrix product not found")
    
    return {"message": "Product removed from matrix"}

# Matrix-Based Ordering (Chef/Staff)

@api_router.post("/matrices/{matrix_id}/orders")
async def create_matrix_order(
    matrix_id: str,
    data: MatrixOrderCreate,
    current_user: dict = Depends(get_current_user)
):
    """Chef/Staff creates an order from matrix using row numbers"""
    if current_user['role'] not in [UserRole.chef, UserRole.responsible]:
        raise HTTPException(status_code=403, detail="Only Chef/Staff can create orders from matrix")
    
    # Verify access to matrix
    user = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
    if not user or user.get('matrixId') != matrix_id:
        raise HTTPException(status_code=403, detail="Not authorized to order from this matrix")
    
    matrix = await db.matrices.find_one({"id": matrix_id}, {"_id": 0})
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    
    # Get all matrix products
    matrix_products = await db.matrix_products.find({"matrixId": matrix_id}, {"_id": 0}).to_list(1000)
    row_map = {mp['rowNumber']: mp for mp in matrix_products}
    
    # Process order items
    orders_by_supplier = {}  # Group items by supplier (best price)
    
    for item in data.items:
        row_num = item.get('rowNumber')
        quantity = float(item.get('quantity', 0))
        
        if not row_num or quantity <= 0:
            continue
        
        # Find matrix product
        matrix_product = row_map.get(row_num)
        if not matrix_product:
            continue
        
        # Determine which products to consider based on mode
        if matrix_product.get('mode') == 'cheapest':
            # CHEAPEST MODE: Re-search for matching products across all suppliers
            from product_intent_parser import find_matching_products
            
            # Get all pricelists
            all_pricelists = await db.pricelists.find({}, {"_id": 0}).to_list(10000)
            
            # Enrich with product names
            for pl in all_pricelists:
                prod = await db.products.find_one({"id": pl['productId']}, {"_id": 0})
                if prod:
                    pl['productName'] = prod['name']
                    pl['unit'] = prod['unit']
            
            # Find matching products using intent
            intent = {
                "productType": matrix_product.get('productType'),
                "baseUnit": matrix_product.get('baseUnit'),
                "keyAttributes": matrix_product.get('keyAttributes'),
                "brand": matrix_product.get('brand'),
                "strictBrand": matrix_product.get('strictBrand', False)
            }
            
            matching_pls = find_matching_products(intent, all_pricelists)
            
            if not matching_pls:
                # Fallback to exact product if no matches found
                matching_pls = await db.pricelists.find(
                    {"productId": matrix_product['productId']}, 
                    {"_id": 0}
                ).to_list(100)
        else:
            # EXACT MODE: Use only this specific product
            matching_pls = await db.pricelists.find(
                {"productId": matrix_product['productId']}, 
                {"_id": 0}
            ).to_list(100)
        
        if not matching_pls:
            continue
        
        # Sort by price and get cheapest
        matching_pls.sort(key=lambda x: x['price'])
        best_pl = matching_pls[0]
        
        supplier_id = best_pl['supplierId']
        
        if supplier_id not in orders_by_supplier:
            orders_by_supplier[supplier_id] = {
                "items": [],
                "total": 0
            }
        
        item_total = quantity * best_pl['price']
        orders_by_supplier[supplier_id]["items"].append({
            "productName": matrix_product['productName'],
            "article": matrix_product['productCode'],
            "quantity": quantity,
            "price": best_pl['price'],
            "unit": matrix_product['unit'],
            "rowNumber": row_num
        })
        orders_by_supplier[supplier_id]["total"] += item_total
        
        # Update last order quantity in matrix
        await db.matrix_products.update_one(
            {"id": matrix_product['id']},
            {"$set": {"lastOrderQuantity": quantity}}
        )
    
    # Get delivery address
    delivery_address = None
    if data.deliveryAddressId:
        company = await db.companies.find_one({"id": matrix['restaurantCompanyId']}, {"_id": 0})
        if company and company.get('deliveryAddresses'):
            for addr in company['deliveryAddresses']:
                if addr.get('id') == data.deliveryAddressId:
                    delivery_address = addr
                    break
    
    # Create orders (one per supplier)
    restaurant_id = matrix['restaurantCompanyId']
    for supplier_id in orders_by_supplier:
        if await _restaurant_is_paused(supplier_id, restaurant_id):
            raise HTTPException(
                status_code=403,
                detail="Поставщик поставил ваш ресторан на паузу. Отгрузка временно недоступна."
            )
    created_orders = []
    for supplier_id, order_data in orders_by_supplier.items():
        order = Order(
            customerCompanyId=restaurant_id,
            supplierCompanyId=supplier_id,
            amount=order_data["total"],
            orderDetails=order_data["items"],
            deliveryAddress=delivery_address,
            status=OrderStatus.new
        )
        
        order_dict = order.model_dump()
        order_dict['orderDate'] = order_dict['orderDate'].isoformat()
        order_dict['createdAt'] = order_dict['createdAt'].isoformat()
        if order_dict.get('deliveryAddress'):
            order_dict['deliveryAddress'] = order_dict['deliveryAddress']
        
        await db.orders.insert_one(order_dict)
        created_orders.append({
            "orderId": order.id,
            "supplierId": supplier_id,
            "amount": order_data["total"],
            "itemCount": len(order_data["items"])
        })
    
    return {
        "message": f"Created {len(created_orders)} order(s)",
        "orders": created_orders
    }

# ==================== TEAM MANAGEMENT ROUTES ====================

@api_router.post("/team/members")
async def create_team_member(data: dict, current_user: dict = Depends(get_current_user)):
    """Admin creates a chef or staff member"""
    if current_user['role'] not in [UserRole.customer, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only admins can create team members")
    
    # Get admin's company
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Check if email already exists
    existing_user = await db.users.find_one({"email": data['email']})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already in use")
    
    # Hash password
    hashed_password = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
    
    # Create user
    user = {
        "id": str(uuid.uuid4()),
        "email": data['email'],
        "passwordHash": hashed_password.decode('utf-8'),
        "role": data['role'],  # 'chef' or 'responsible'
        "companyId": company['id'],
        "matrixId": data.get('matrixId'),
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(user)
    
    return {
        "message": "Team member created successfully",
        "user": {
            "id": user['id'],
            "email": user['email'],
            "role": user['role']
        }
    }

@api_router.get("/team/members")
async def get_team_members(current_user: dict = Depends(get_current_user)):
    """Get all team members for current company"""
    if current_user['role'] not in [UserRole.customer, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        return []
    
    # Get all chef and staff users for this company
    users = await db.users.find(
        {
            "companyId": company['id'],
            "role": {"$in": ["chef", "responsible"]}
        },
        {"_id": 0, "passwordHash": 0}
    ).to_list(100)
    
    return users

@api_router.delete("/team/members/{user_id}")
async def delete_team_member(user_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a team member"""
    if current_user['role'] not in [UserRole.customer, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only admins can delete team members")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Delete user (only if they belong to this company)
    result = await db.users.delete_one({"id": user_id, "companyId": company['id']})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "Team member deleted successfully"}

# ==================== USER PROFILE ROUTES ====================

@api_router.get("/users/my-profile")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Get current user's profile"""
    user = await db.users.find_one({"id": current_user['id']}, {"_id": 0, "passwordHash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@api_router.put("/users/my-profile")
async def update_my_profile(data: dict, current_user: dict = Depends(get_current_user)):
    """Update current user's profile (phone and email only)"""
    # Only allow updating certain fields
    allowed_updates = {}
    if 'phone' in data:
        allowed_updates['phone'] = data['phone']
    if 'email' in data:
        # Check if email is already in use by another user
        existing = await db.users.find_one({"email": data['email'], "id": {"$ne": current_user['id']}})
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        allowed_updates['email'] = data['email']
    
    if not allowed_updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    result = await db.users.update_one(
        {"id": current_user['id']},
        {"$set": allowed_updates}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = await db.users.find_one({"id": current_user['id']}, {"_id": 0, "passwordHash": 0})
    return user

# ==================== FAVORITES ROUTES ====================

@api_router.post("/favorites")
async def add_to_favorites(data: dict, current_user: dict = Depends(get_current_user)):
    """Add product to favorites with SCHEMA V2 (brand_critical + origin support)"""
    from brand_master import brand_master
    from search_engine import extract_tokens, extract_pack_value
    
    # Get user's company
    company_id = current_user.get('companyId')
    if current_user['role'] == 'customer':
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    # Get product details
    product = await db.products.find_one({"id": data['productId']}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get product code
    pricelist = await db.pricelists.find_one({"productId": data['productId']}, {"_id": 0})
    product_code = pricelist.get('supplierItemCode', '') if pricelist else ''
    
    # Check if already in favorites
    existing = await db.favorites.find_one({
        "userId": current_user['id'],
        "productId": data['productId']
    }, {"_id": 0})
    
    if existing:
        raise HTTPException(status_code=400, detail="Product already in favorites")
    
    # AUTO-DETECT brand using BRAND MASTER
    brand_id = None
    brand_name = None
    brand_strict = False
    
    if brand_master:
        brand_id, brand_strict = brand_master.detect_brand(product['name'])
        if brand_id:
            brand_info = brand_master.get_brand_info(brand_id)
            brand_name = brand_info.get('brand_en') if brand_info else None
    
    # FALLBACK: Check for common abbreviations not in brand master
    if not brand_id:
        name_upper = product['name'].upper()
        abbreviations = {
            'PRB': 'pearl river bridge',
            'SEN SOY': 'sen soy',
            'СЕН СОЙ': 'sen soy',
        }
        
        for abbr, full_brand in abbreviations.items():
            if abbr in name_upper:
                brand_id = full_brand
                brand_strict = True
                break
    
    is_branded = brand_id is not None
    
    # Extract pack_size and tokens (for schema v2)
    pack_size = extract_pack_value(product['name'], product['unit'])
    tokens_norm = list(extract_tokens(product['name']))
    
    # Normalize unit
    unit_map = {'кг': 'kg', 'л': 'l', 'шт': 'pcs', 'г': 'g', 'мл': 'ml'}
    unit_norm = unit_map.get(product['unit'].lower(), product['unit'].lower())
    
    # Extract origin (country/region/city) from pricelist or product
    # This is for non-branded items like salmon (лосось Норвегия)
    origin_country = pricelist.get('origin_country') or product.get('origin_country')
    origin_region = pricelist.get('origin_region') or product.get('origin_region')
    origin_city = pricelist.get('origin_city') or product.get('origin_city')
    
    # Try to extract from name if not in DB
    if not origin_country:
        # Extended list: countries + major Russian fishing regions/cities
        name_lower = product['name'].lower()
        
        # Countries
        countries = {
            'норвегия': 'Норвегия', 'norway': 'Норвегия',
            'чили': 'Чили', 'chile': 'Чили',
            'россия': 'Россия', 'russia': 'Россия',
            'турция': 'Турция', 'turkey': 'Турция',
            'китай': 'Китай', 'china': 'Китай',
            'испания': 'Испания', 'spain': 'Испания',
            'франция': 'Франция', 'france': 'Франция',
            'исландия': 'Исландия', 'iceland': 'Исландия'
        }
        
        # Russian fishing regions/cities (for origin_city)
        russian_regions = {
            'мурманск': ('Россия', None, 'Мурманск'),
            'владивосток': ('Россия', None, 'Владивосток'),
            'камчатка': ('Россия', 'Камчатка', None),
            'сахалин': ('Россия', 'Сахалин', None),
            'архангельск': ('Россия', None, 'Архангельск')
        }
        
        # Check for Russian regions first
        for region_key, (country, region, city) in russian_regions.items():
            if region_key in name_lower:
                origin_country = country
                origin_region = region
                origin_city = city
                break
        
        # If not found, check countries
        if not origin_country:
            for country_key, country_name in countries.items():
                if country_key in name_lower:
                    origin_country = country_name
                    break
    
    # Create favorite with SCHEMA V2
    favorite = {
        "id": str(uuid.uuid4()),
        "userId": current_user['id'],
        "companyId": company_id,
        "productId": data['productId'],
        
        # Schema v2 fields
        "reference_name": product['name'],  # Эталонное имя
        "brand_id": brand_id,               # ID бренда (может быть null)
        "brand_critical": True,             # P0 FIX: По умолчанию ON (95% threshold)
        "origin_country": origin_country,   # Страна происхождения (для лосося и т.д.)
        "origin_region": origin_region,     # Регион (опционально)
        "origin_city": origin_city,         # Город (опционально)
        "unit_norm": unit_norm,             # kg, l, pcs
        "pack_size": pack_size,             # Число в unit_norm
        "tokens_norm": tokens_norm,         # Нормализованные токены
        "schema_version": 2,                # Версия схемы
        
        # Legacy fields (для обратной совместимости)
        "productName": product['name'],
        "productCode": product_code,
        "unit": product['unit'],
        "isBranded": is_branded,
        "brandMode": "STRICT" if is_branded and brand_strict else "ANY",
        "brand": brand_name,
        "originalSupplierId": data.get('supplierId'),
        "addedAt": datetime.now(timezone.utc).isoformat(),
        "displayOrder": 0
    }
    
    await db.favorites.insert_one(favorite)
    
    return {
        "id": favorite['id'],
        "productName": favorite['productName'],
        "isBranded": favorite['isBranded'],
        "brand": favorite['brand'],
        "origin_country": origin_country,
        "schema_version": 2
    }


@api_router.put("/favorites/{favorite_id}/mode")
async def update_favorite_mode(favorite_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update mode for a favorite item"""
    mode = data.get('mode')
    if mode not in ['exact', 'cheapest']:
        raise HTTPException(status_code=400, detail="Invalid mode")
    
    result = await db.favorites.update_one(
        {"id": favorite_id, "userId": current_user['id']},
        {"$set": {"mode": mode}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    return {"message": "Mode updated", "mode": mode}


@api_router.put("/favorites/{favorite_id}/brand-mode")
async def update_favorite_brand_mode(favorite_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update brand mode (STRICT/ANY) for a favorite"""
    brand_mode = data.get('brandMode')
    if brand_mode not in ['STRICT', 'ANY']:
        raise HTTPException(status_code=400, detail="Invalid brand mode")
    
    # Update BOTH legacy brandMode AND schema v2 brand_critical
    brand_critical = (brand_mode == 'STRICT')
    
    result = await db.favorites.update_one(
        {"id": favorite_id, "userId": current_user['id']},
        {"$set": {"brandMode": brand_mode, "brand_critical": brand_critical}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    return {"message": "Brand mode updated", "brandMode": brand_mode, "brand_critical": brand_critical}


# NEW UNIVERSAL MATCHING ENGINE ENDPOINT
@api_router.get("/favorites/v2")
async def get_favorites_v2(current_user: dict = Depends(get_current_user)):
    """Get favorites with HYBRID matching engine (best of spec + simple)"""
    from matching.hybrid_matcher import find_best_match_hybrid
    
    favorites = await db.favorites.find({"userId": current_user['id']}, {"_id": 0}).sort("displayOrder", 1).to_list(500)
    
    if not favorites:
        return []
    
    # Get companies map
    all_companies = await db.companies.find({}, {"_id": 0, "id": 1, "companyName": 1, "name": 1}).to_list(100)
    companies_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in all_companies}
    
    # Load ALL supplier_items once (NEW collection with price_per_base_unit)
    all_items = await db.supplier_items.find({"active": True}, {"_id": 0}).to_list(15000)
    
    enriched = []
    
    for fav in favorites:
        mode = fav.get('mode', 'exact')
        
        # Get original product
        original_product = await db.products.find_one({"id": fav['productId']}, {"_id": 0})
        original_pl = await db.price_lists.find_one({"productId": fav['productId']}, {"_id": 0})
        original_price = fav.get('originalPrice') or (original_pl['price'] if original_pl else None)
        
        if not original_product or not original_price:
            continue
        
        if mode == 'cheapest':
            # strictBrand flag is INVERTED in UI: 
            # - UI shows "Не учитывать производителя" (ignore brand)
            # - When checked: strictBrand=true → IGNORE brand (search all brands)
            # - When unchecked: strictBrand=false → KEEP brand (search same brand only)
            ignore_brand = fav.get('strictBrand', False)
            
            # Use HYBRID matcher
            winner = find_best_match_hybrid(
                query_product_name=original_product['name'],
                original_price=original_price,
                all_items=all_items,
                strict_brand_override=not ignore_brand  # Invert: if ignore=True, strict=False
            )
            
            if winner:
                enriched.append({
                    **fav,
                    "mode": mode,
                    "originalPrice": original_price,
                    "bestPrice": winner['price'],
                    "bestPricePerBaseUnit": winner.get('price_per_base_unit'),
                    "bestSupplier": companies_map.get(winner['supplier_company_id'], 'Unknown'),
                    "productName": fav.get('productName', original_product['name']),
                    "productCode": fav.get('productCode', original_product.get('article', '')),
                    "unit": fav.get('unit', original_product.get('unit', 'шт')),
                    "foundProduct": {
                        "name": winner['name_raw'],
                        "price": winner['price'],
                        "pricePerBaseUnit": winner.get('price_per_base_unit'),
                        "baseUnit": winner.get('base_unit'),
                        "calcRoute": winner.get('calc_route')
                    },
                    "hasCheaperMatch": True,
                    "engineVersion": "v2_hybrid"
                })
            else:
                enriched.append({
                    **fav,
                    "mode": mode,
                    "bestPrice": original_price,
                    "bestSupplier": companies_map.get(fav.get('originalSupplierId', ''), 'Unknown'),
                    "productName": fav.get('productName', original_product['name']),
                    "productCode": fav.get('productCode', original_product.get('article', '')),
                    "unit": fav.get('unit', original_product.get('unit', 'шт')),
                    "fallbackMessage": "Аналоги найдены, но текущая цена уже лучшая",
                    "hasCheaperMatch": False,
                    "engineVersion": "v2_hybrid"
                })
        else:
            # EXACT MODE
            enriched.append({
                **fav,
                "mode": mode,
                "bestPrice": original_price,
                "bestSupplier": companies_map.get(fav.get('originalSupplierId', ''), 'Unknown'),
                "productName": fav.get('productName', original_product['name']),
                "productCode": fav.get('productCode', original_product.get('article', '')),
                "unit": fav.get('unit', original_product.get('unit', 'шт')),
                "engineVersion": "v2_hybrid"
            })
    
    return enriched
@api_router.get("/favorites")
async def get_favorites_simple(current_user: dict = Depends(get_current_user)):
    """Get favorites WITHOUT matching - just intentions
    
    NEW LOGIC per новая логика.docx:
    - NO prices in favorites
    - NO matching logic
    - Only product intentions with brandMode
    """
    favorites = await db.favorites.find(
        {"userId": current_user['id']}, 
        {"_id": 0}
    ).sort("displayOrder", 1).to_list(500)
    
    # Return simple data - NO matching, NO prices
    return favorites
    
    if not favorites:
        return []
    
    # Get companies map
    all_companies = await db.companies.find({}, {"_id": 0, "id": 1, "companyName": 1, "name": 1}).to_list(100)
    companies_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in all_companies}
    
    enriched = []
    
    for fav in favorites:
        mode = fav.get('mode', 'exact')
        
        # Get original product info
        original_product = await db.products.find_one({"id": fav['productId']}, {"_id": 0})
        original_pl = await db.price_lists.find_one({"productId": fav['productId']}, {"_id": 0})
        original_price = fav.get('originalPrice') or (original_pl['price'] if original_pl else None)
        
        if not original_product or not original_price:
            continue
        
        if mode == 'cheapest':
            # CHEAPEST MODE: Find products with same type AND similar weight/attributes
            original_type = extract_product_type(original_product['name'].lower())
            original_weight = extract_weight_kg(original_product['name'])
            original_caliber = extract_caliber(original_product['name'])
            
            # Find all products with same type
            all_products = await db.price_lists.find(
                {"price": {"$gt": 0}},  # Exclude 0 price items
                {"_id": 0}
            ).to_list(10000)
            
            matches = []
            for prod in all_products:
                prod_type = extract_product_type(prod['productName'].lower())
                
                # PRIMARY TYPE MUST MATCH EXACTLY
                if prod_type != original_type:
                    continue
                
                # Skip if price not cheaper
                if prod['price'] >= original_price:
                    continue
                
                # For products with CALIBER: caliber MUST match
                # Caliber represents important attributes: shrimp size, fish size, fat %, piece count
                # Examples: 16/20 (shrimp), 4/5 (salmon), 90/10 (beef fat %), 100/110 (cucumber size)
                if original_caliber:
                    prod_caliber = extract_caliber(prod['productName'])
                    # If original has caliber, found product MUST have same caliber
                    if not prod_caliber or prod_caliber != original_caliber:
                        continue
                
                # Check weight similarity (±20% tolerance)
                prod_weight = extract_weight_kg(prod['productName'])
                
                # STRICT: Both products must have weight info for comparison
                if original_weight and prod_weight:
                    weight_diff = abs(original_weight - prod_weight) / original_weight
                    # Skip if weight difference > 20%
                    if weight_diff > 0.20:
                        continue
                elif original_weight or prod_weight:
                    # One has weight, one doesn't - skip to avoid false matches
                    continue
                # If both have no weight info, allow match (rare edge case)
                
                # Get supplier info
                supplier_id = prod.get('supplierId')
                supplier_name = companies_map.get(supplier_id, 'Unknown')
                
                matches.append({
                    'productName': prod['productName'],
                    'price': prod['price'],
                    'supplierId': supplier_id,
                    'supplierName': supplier_name,
                    'productId': prod.get('productId'),
                    'article': prod.get('article'),
                    'weight': prod_weight
                })
            
            # Sort by price (cheapest first)
            matches.sort(key=lambda x: x['price'])
            
            if matches:
                best = matches[0]
                enriched.append({
                    **fav,
                    "mode": mode,
                    "originalPrice": original_price,
                    "bestPrice": best['price'],
                    "bestSupplier": best['supplierName'],
                    "productName": fav.get('productName', original_product['name']),
                    "productCode": fav.get('productCode', original_product.get('article', '')),
                    "unit": fav.get('unit', original_product.get('unit', 'шт')),
                    "foundProduct": {
                        "name": best['productName'],
                        "price": best['price'],
                        "weight": best.get('weight')
                    },
                    "hasCheaperMatch": True,
                    "matchCount": len(matches)
                })
            else:
                enriched.append({
                    **fav,
                    "mode": mode,
                    "bestPrice": original_price,
                    "bestSupplier": companies_map.get(fav.get('originalSupplierId', ''), 'Unknown'),
                    "productName": fav.get('productName', original_product['name']),
                    "productCode": fav.get('productCode', original_product.get('article', '')),
                    "unit": fav.get('unit', original_product.get('unit', 'шт')),
                    "fallbackMessage": "Аналоги найдены, но текущая цена уже лучшая",
                    "hasCheaperMatch": False
                })
        else:
            # EXACT MODE
            enriched.append({
                **fav,
                "mode": mode,
                "bestPrice": original_price,
                "bestSupplier": companies_map.get(fav.get('originalSupplierId', ''), 'Unknown'),
                "productName": fav.get('productName', original_product['name']),
                "productCode": fav.get('productCode', original_product.get('article', '')),
                "unit": fav.get('unit', original_product.get('unit', 'шт'))
            })
    
    return enriched

@api_router.put("/favorites/{favorite_id}/position")
async def update_favorite_position(favorite_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update favorite display order"""
    new_position = data.get('position', 0)
    
    result = await db.favorites.update_one(
        {"id": favorite_id, "userId": current_user['id']},
        {"$set": {"displayOrder": new_position}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    return {"message": "Position updated"}

@api_router.post("/favorites/reorder")
async def reorder_favorites(data: dict, current_user: dict = Depends(get_current_user)):
    """Bulk update favorites display order"""
    favorites = data.get('favorites', [])
    
    if not favorites:
        raise HTTPException(status_code=400, detail="No favorites provided")
    
    # Update all favorites in bulk
    for fav in favorites:
        await db.favorites.update_one(
            {"id": fav['id'], "userId": current_user['id']},
            {"$set": {"displayOrder": fav['displayOrder']}}
        )
    
    return {"message": "Favorites reordered successfully"}

@api_router.delete("/favorites/{favorite_id}")
async def remove_from_favorites(favorite_id: str, current_user: dict = Depends(get_current_user)):
    """Remove product from favorites"""
    result = await db.favorites.delete_one({"id": favorite_id, "userId": current_user['id']})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    return {"message": "Removed from favorites"}


@api_router.post("/cart/resolve-favorite")
async def resolve_favorite_price(data: dict, current_user: dict = Depends(get_current_user)):
    """AUTOMATIC best price search when adding from favorites to cart
    
    NEW LOGIC (Per user requirements):
    1. Product is used as reference (эталон)
    2. System automatically analyzes ALL supplier prices
    3. Finds products with ≥85% match using BestPrice logic
    4. Converts price to base unit (kg/l/pcs)
    5. Selects lowest price from matching products
    6. Returns OPTIMIZED product (not specific supplier's item)
    
    brandCritical parameter:
    - If TRUE: search only same brand (supplier can change)
    - If FALSE: brand is not a constraint, allow analogs, choose by max match + min price
    """
    from matching.hybrid_matcher import find_best_match_hybrid
    
    product_id = data.get('productId')
    brand_critical = data.get('brandCritical', False)  # NEW: use brandCritical instead of brandMode
    
    # Get product
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get original pricelist for reference (needed for fallback)
    original_pl = await db.pricelists.find_one({"productId": product_id}, {"_id": 0})
    if not original_pl:
        raise HTTPException(status_code=404, detail="Product not available")
    
    # ALWAYS use hybrid matcher to find best price!
    # Even for same product - different suppliers may have different prices
    all_items = await db.supplier_items.find({"active": True}, {"_id": 0}).to_list(15000)
    
    # Use matcher with strict_brand based on brandCritical flag
    winner = find_best_match_hybrid(
        query_product_name=product['name'],
        original_price=float('inf'),  # No price limit - find cheapest overall
        all_items=all_items,
        strict_brand_override=brand_critical,  # Respect brandCritical flag
        similarity_threshold=0.65  # 65% threshold as per requirements
    )
    
    if winner:
        # Found match - use winner's price and supplier
        companies = await db.companies.find({}, {"_id": 0, "id": 1, "companyName": 1, "name": 1}).to_list(100)
        companies_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in companies}
        
        supplier_name = companies_map.get(winner['supplier_company_id'], 'Unknown')
        
        return {
            "price": winner['price'],
            "supplier": supplier_name,
            "supplierId": winner['supplier_company_id'],
            "productId": winner.get('product_id', product_id),
            "productName": winner['name_raw']
        }
    else:
        # No match found - fall back to cheapest of exact same product
        pricelists = await db.pricelists.find({"productId": product_id}, {"_id": 0}).to_list(100)
        if not pricelists:
            raise HTTPException(status_code=404, detail="No suppliers found for this product")
        
        pricelists.sort(key=lambda x: x['price'])
        best_pl = pricelists[0]
        
        supplier = await db.companies.find_one({"id": best_pl['supplierId']}, {"_id": 0})
        supplier_name = supplier.get('companyName') or supplier.get('name', 'Unknown') if supplier else 'Unknown'
        
        return {
            "price": best_pl['price'],
            "supplier": supplier_name,
            "supplierId": best_pl['supplierId'],
            "productId": product_id,
            "productName": product['name']
        }


# ==================== NEW: SELECT BEST OFFER ENDPOINT ====================
class ReferenceItem(BaseModel):
    """Reference item (эталон) from favorites"""
    name_raw: str
    name_norm: Optional[str] = None
    tokens: Optional[List[str]] = None
    super_class: Optional[str] = None
    unit_norm: Optional[str] = None  # kg, l, pcs, box
    pack_value: Optional[float] = None  # Weight/volume from card (e.g., 1.8 for 1.8kg)
    pack_unit: Optional[str] = None  # kg, l, pcs
    brand_id: Optional[str] = None
    brand_critical: bool = False

class SelectOfferRequest(BaseModel):
    reference_item: ReferenceItem
    qty: int = 1
    required_volume: Optional[float] = None  # Required volume/weight (e.g., 5 for 5kg)
    match_threshold: float = 0.85

class SelectedOffer(BaseModel):
    supplier_id: str
    supplier_name: str
    supplier_item_id: str
    name_raw: str  # Actual product name
    price: float
    currency: str = "RUB"
    unit_norm: str
    pack_value: Optional[float] = None
    pack_unit: Optional[str] = None
    price_per_base_unit: Optional[float] = None
    total_cost: Optional[float] = None  # Total cost for required volume
    units_needed: Optional[float] = None  # How many units needed for required volume
    score: float
    match_percent: Optional[float] = None  # Alias for score (UI compatibility)
    # P0: New fields for unit normalization
    selected_pack_base_qty: Optional[float] = None  # e.g., 5 (in grams)
    selected_pack_unit: Optional[str] = None  # e.g., "g"
    required_base_qty: Optional[float] = None  # e.g., 1000 (in grams)
    required_unit: Optional[str] = None  # e.g., "g"
    packs_needed: Optional[int] = None  # e.g., 200
    pack_explanation: Optional[str] = None  # e.g., "200 × 5 г = 1000 г"
    # P0.5: min_order_qty support
    min_order_qty: Optional[int] = None
    actual_qty: Optional[float] = None
    stick_with_favorite: Optional[bool] = None  # P0: Indicates low match fallback

class SelectOfferResponse(BaseModel):
    selected_offer: Optional[SelectedOffer] = None
    top_candidates: Optional[List[dict]] = None
    reason: Optional[str] = None


def calculate_match_score(reference: dict, candidate: dict, brand_critical: bool) -> float:
    """Calculate match score between reference item and candidate
    
    Score components (when brand_critical=false):
    - Name similarity (with synonyms + fuzzy): 70%
    - Super class match: 15%
    - Weight/volume tolerance: 15%
    - Brand: 0% (IGNORED!)
    
    Score components (when brand_critical=true):
    - Name similarity: 60%
    - Super class match: 15%
    - Weight/volume tolerance: 15%
    - Brand match: 10%
    
    IMPORTANT: When brand_critical=false, brand is COMPLETELY NEUTRAL:
    - No filtering by brand
    - No bonus/penalty in score
    - default_strict from dictionary is IGNORED
    """
    score = 0.0
    
    # SYNONYMS - groups of equivalent terms
    SYNONYM_GROUPS = [
        {'неразделан', 'непотрош', 'целый', 'тушка', 'целик'},  # Fish state
        {'с/м', 'с/г', 'зам', 'свежеморож', 'мороженый', 'frozen', 'заморож'},  # Frozen states
        {'инд', 'индивид'},  # Individual
        {'охл', 'охлажд', 'chilled'},  # Chilled
        {'филе', 'fillet'},  # Fillet
        {'стейк', 'steak'},  # Steak
        {'сибас', 'сибасс'},  # Typo: сибас/сибасс
        {'лосось', 'лососс'},  # Typo
        {'кетчуп', 'кечуп'},  # Typo
    ]
    
    def get_canonical(token: str) -> str:
        """Get canonical form (first in group) for a token"""
        token_lower = token.lower()
        for group in SYNONYM_GROUPS:
            for syn in group:
                if syn in token_lower:
                    return list(group)[0]
        return token_lower
    
    def normalize_tokens(tokens: set) -> set:
        """Replace synonyms with canonical form"""
        result = set()
        for token in tokens:
            result.add(get_canonical(token))
        return result
    
    # Determine weights based on brand_critical
    # When brand_critical=false, brand weight is 0, redistribute to name similarity
    if brand_critical:
        name_weight = 0.60
        brand_weight = 0.10
    else:
        name_weight = 0.70  # Brand weight redistributed to name
        brand_weight = 0.0   # BRAND IS NEUTRAL!
    
    # 1. Name similarity (with synonyms)
    ref_name = reference.get('name_norm') or reference.get('name_raw', '').lower()
    cand_name = (candidate.get('name_norm') or candidate.get('name_raw', '')).lower()
    
    # Tokenize
    ref_tokens = set(ref_name.split())
    cand_tokens = set(cand_name.split())
    
    # Remove common filler words  
    fillers = {'кг', 'кг/кор.', 'кг/кор', 'гр', 'гр.', 'г', 'г.', 'л', 'л.', 'мл', 'мл.', 
               'шт', 'шт.', 'упак', 'упак.', 'пакет', 'вес', '~', 'и', 'в', 'с', 'на', 'к',
               'инд.', 'зам.', 'охл.', '%', '5%', '23-0095', 'tr', 'tr-09-0036', '(-c-)',
               '23', '0095', '09', '0036', 'инд'}
    ref_tokens = ref_tokens - fillers
    cand_tokens = cand_tokens - fillers
    
    # Normalize with synonyms
    ref_normalized = normalize_tokens(ref_tokens)
    cand_normalized = normalize_tokens(cand_tokens)
    
    if ref_normalized and cand_normalized:
        intersection = len(ref_normalized & cand_normalized)
        
        # KEY WORD BONUS: If the main product name matches (first significant word)
        main_word_bonus = 0.0
        for ref_token in ref_normalized:
            if len(ref_token) >= 4:  # Significant word
                for cand_token in cand_normalized:
                    if ref_token == cand_token:
                        main_word_bonus = 0.15
                        break
                if main_word_bonus > 0:
                    break
        
        # Coverage: what % of reference words found in candidate
        coverage = intersection / len(ref_normalized) if ref_normalized else 0
        jaccard = intersection / len(ref_normalized | cand_normalized) if (ref_normalized | cand_normalized) else 0
        
        # Blend coverage and jaccard + main word bonus
        name_score = coverage * 0.5 + jaccard * 0.2 + main_word_bonus
        score += min(name_score, name_weight)  # Cap at name_weight
    
    # 2. Super class match - 15%
    ref_class = reference.get('super_class')
    cand_class = candidate.get('super_class')
    if ref_class and cand_class:
        if ref_class == cand_class:
            score += 0.15
        elif ref_class.split('.')[0] == cand_class.split('.')[0]:
            score += 0.08
    elif not ref_class:
        score += 0.10
    
    # 3. Weight/volume tolerance (±20%) - 15%
    ref_weight = reference.get('pack_value') or reference.get('net_weight_kg')
    cand_weight = candidate.get('net_weight_kg') or candidate.get('net_volume_l')
    
    if ref_weight and cand_weight and ref_weight > 0:
        ratio = cand_weight / ref_weight
        if 0.8 <= ratio <= 1.2:  # Within 20%
            tolerance_score = 1.0 - abs(1.0 - ratio) / 0.2
            score += tolerance_score * 0.15
    elif not ref_weight:
        score += 0.10
    
    # 4. Brand match - ONLY when brand_critical=true
    if brand_weight > 0:
        ref_brand = reference.get('brand_id')
        cand_brand = candidate.get('brand_id')
        
        if ref_brand and cand_brand:
            if ref_brand.lower() == cand_brand.lower():
                score += brand_weight
        elif not ref_brand:
            score += brand_weight
    # When brand_critical=false: brand_weight=0, NO bonus/penalty for brand!
    
    return round(score, 4)



@api_router.post("/cart/select-offer", response_model=SelectOfferResponse)
async def select_best_offer(request: SelectOfferRequest, current_user: dict = Depends(get_current_user)):
    """Select best offer (cheapest matching item) from all suppliers
    
    This is the CORE endpoint for automatic best price selection.
    
    Logic:
    1. Find candidates among all products + pricelists
    2. Score each candidate (brand_weight=0 when brand_critical=false!)
    3. Apply threshold (default 0.85)
    4. If brand_critical=true: filter by brand_id
    5. Select cheapest by total_cost
    
    IMPORTANT (brand_critical rule):
    - brand_critical=false: brand is COMPLETELY NEUTRAL (no filter, no score bonus)
    - brand_critical=true: brand is required (filter + bonus)
    
    NULL-SAFE: Returns structured response, never 500 error.
    Possible statuses in 'reason' field:
    - None (success)
    - NO_MATCH_OVER_THRESHOLD
    - INSUFFICIENT_DATA
    - NOT_FOUND
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        ref = request.reference_item.model_dump()
        threshold = request.match_threshold
        brand_critical = ref.get('brand_critical', False)
        
        # NULL-SAFE: Check for required data
        ref_name = ref.get('name_raw') or ''
        if not ref_name.strip():
            logger.warning("❌ SELECT_BEST_OFFER: No name_raw provided")
            return SelectOfferResponse(
                selected_offer=None,
                reason="INSUFFICIENT_DATA"
            )
        
        # DEBUG: Log brand_critical status (null-safe)
        brand_weight = 0.10 if brand_critical else 0.0
        logger.info(f"🔍 SELECT_BEST_OFFER:")
        logger.info(f"   ref='{ref_name[:50] if ref_name else 'N/A'}'")
        logger.info(f"   brand_critical={brand_critical}, brand_weight={brand_weight}")
        logger.info(f"   brand_id filter applied: {'YES' if brand_critical else 'NO'}")
        logger.info(f"   threshold={threshold}")
        
        # Enrich reference item if needed
        from pipeline.normalizer import normalize_name
        from pipeline.enricher import extract_super_class, extract_weights
        
        if not ref.get('name_norm'):
            ref['name_norm'] = normalize_name(ref_name)
        
        if not ref.get('super_class'):
            ref['super_class'] = extract_super_class(ref.get('name_norm') or '')
        
        if not ref.get('pack_value'):
            weight_data = extract_weights(ref_name)
            ref['pack_value'] = weight_data.get('net_weight_kg')
        
        # Load company names map
        companies = await db.companies.find({}, {"_id": 0, "id": 1, "companyName": 1, "name": 1}).to_list(100)
        company_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in companies}
        
        # Load ALL products and pricelists (actual data source)
        all_products = await db.products.find({}, {"_id": 0}).to_list(10000)
        all_pricelists = await db.pricelists.find({}, {"_id": 0}).to_list(20000)
        
        if not all_products or not all_pricelists:
            logger.warning("❌ SELECT_BEST_OFFER: No products or pricelists in database")
            return SelectOfferResponse(
                selected_offer=None,
                reason="NOT_FOUND"
            )
        
        # Build product lookup
        product_map = {p['id']: p for p in all_products}
    
        # Build items list with price info (products + pricelists joined)
        all_items = []
        for pl in all_pricelists:
            product = product_map.get(pl['productId'])
            if not product:
                continue
            
            # Enrich product with pricelist data
            item = {
                'id': pl['id'],
                'product_id': product['id'],
                'name_raw': product.get('name', ''),
                'name_norm': normalize_name(product.get('name', '')),
                'price': pl['price'],
                'price_per_base_unit': pl['price'],  # Default - will be recalculated if weight found
                'supplier_company_id': pl['supplierId'],
                'unit_norm': product.get('unit', 'kg'),
                'super_class': extract_super_class(normalize_name(product.get('name', ''))),
                # USE brand_id from product (set by backfill from new brand master)
                'brand_id': product.get('brand_id'),
                'brand_strict': product.get('brand_strict', False),
            }
            
            # Extract weight for price_per_base_unit calculation
            weight_data = extract_weights(product.get('name', ''))
            net_weight = weight_data.get('net_weight_kg')
            if net_weight and net_weight > 0:
                item['net_weight_kg'] = net_weight
                item['price_per_base_unit'] = pl['price'] / net_weight
            
            all_items.append(item)
        
        logger.info(f"📊 Loaded {len(all_items)} items from products+pricelists")
        
        # DEBUG: Check barco items
        barco_items = [i for i in all_items if i.get('brand_id') == 'barco']
        logger.info(f"🏷️ DEBUG: Found {len(barco_items)} items with brand_id='barco'")
        for bi in barco_items[:3]:
            logger.info(f"   - {bi['name_raw'][:40]}: price={bi['price']}")
        
        # Filter and score candidates
        candidates = []
        debug_scores = []  # For logging
        
        for item in all_items:
            # Calculate score (brand_weight=0 when brand_critical=false!)
            score = calculate_match_score(ref, item, brand_critical)
            
            # Log high scores for debugging (include brand_id!)
            if score >= 0.5:
                debug_scores.append({
                    'name': item['name_raw'][:50],
                    'score': score,
                    'price': item['price'],
                    'brand_id': item.get('brand_id', 'none'),  # DEBUG: include brand_id
                    'supplier': company_map.get(item['supplier_company_id'], 'Unknown')
                })
            
            # Apply threshold
            if score < threshold:
                continue
            
            # Brand critical filter - ONLY when brand_critical=true!
            if brand_critical and ref.get('brand_id'):
                if not item.get('brand_id') or item['brand_id'].lower() != ref['brand_id'].lower():
                    continue
            # NOTE: When brand_critical=false, NO filtering by brand!
            
            candidates.append({
                'item': item,
                'score': score
            })
        
        # Log debug info - TOP 10 with brand_id
        if debug_scores:
            debug_scores.sort(key=lambda x: -x['score'])
            ref_name_short = (ref.get('name_raw') or '')[:30]
            logger.info(f"🎯 Top-10 candidates for '{ref_name_short}' (brand_critical={brand_critical}):")
            
            # Count unique brands in top scores
            brands_in_top = set()
            for d in debug_scores[:10]:
                brands_in_top.add(d.get('brand_id') or 'none')
                price_str = f"{d['price']:>8.2f}" if d.get('price') is not None else "     N/A"
                brand_str = str(d.get('brand_id') or 'none')[:12]
                name_str = str(d.get('name') or '')[:35]
                logger.info(f"   {d['score']:.2f} | {price_str}₽ | brand={brand_str:12} | {name_str}")
            
            logger.info(f"📊 Unique brands in top-10: {len(brands_in_top)} ({', '.join(str(b) for b in brands_in_top)})")
        
        if not candidates:
            ref_name_short = (ref.get('name_raw') or '')[:50]
            logger.warning(f"❌ NO MATCH for '{ref_name_short}' with threshold {threshold}")
            return SelectOfferResponse(
                selected_offer=None,
                reason="NO_MATCH_OVER_THRESHOLD"
            )
        
        # Get required volume from request or reference item
        required_volume = request.required_volume or ref.get('pack_value') or 1.0
        
        # Calculate total cost for each candidate
        # total_cost = how much it costs to get required_volume
        for c in candidates:
            item = c['item']
            item_volume = item.get('net_weight_kg') or item.get('net_volume_l') or 1.0
            item_price = item.get('price') or 0
            
            if item_volume > 0:
                # How many units needed to cover required volume
                units_needed = required_volume / item_volume
                # Round up if partial units
                units_needed = max(1, units_needed)
                total_cost = item_price * units_needed
            else:
                # Fallback: use item price directly
                units_needed = 1
                total_cost = item_price
            
            c['total_cost'] = total_cost
            c['units_needed'] = units_needed
            c['item_volume'] = item_volume
        
        # Sort by TOTAL COST (cheapest first), then by score (highest first)
        # This selects the best deal for the required volume, not just cheapest unit price
        candidates.sort(key=lambda x: (
            x.get('total_cost') or float('inf'),
            -x['score']
        ))
        
        winner = candidates[0]
        logger.info(f"✅ Found {len(candidates)} candidates. Winner: {winner['item']['price']:.2f}₽ x {winner['units_needed']:.1f} = {winner['total_cost']:.2f}₽ total for {required_volume} units")
        
        # Select winner
        winner_item = winner['item']
        
        selected = SelectedOffer(
            supplier_id=winner_item['supplier_company_id'],
            supplier_name=company_map.get(winner_item['supplier_company_id'], 'Unknown'),
            supplier_item_id=winner_item['id'],
            name_raw=winner_item['name_raw'],
            price=winner_item['price'],
            currency="RUB",
            unit_norm=winner_item.get('unit_norm', 'kg'),
            pack_value=winner_item.get('net_weight_kg') or winner_item.get('net_volume_l'),
            pack_unit=winner_item.get('base_unit', 'kg'),
            price_per_base_unit=winner_item.get('price_per_base_unit'),
            total_cost=winner['total_cost'],
            units_needed=winner['units_needed'],
            score=winner['score']
        )
        
        # Top candidates (max 5)
        top = []
        for c in candidates[:5]:
            top.append({
                'supplier_item_id': c['item']['id'],
                'name_raw': c['item']['name_raw'],
                'price': c['item'].get('price'),
                'pack_value': c.get('item_volume'),
                'total_cost': c.get('total_cost'),
                'units_needed': c.get('units_needed'),
                'price_per_base_unit': c['item'].get('price_per_base_unit'),
                'score': c['score'],
                'supplier': company_map.get(c['item']['supplier_company_id'], 'Unknown')
            })
        
        return SelectOfferResponse(
            selected_offer=selected,
            top_candidates=top
        )
    
    except Exception as e:
        # NULL-SAFE: Catch any unexpected errors and return structured response
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"❌ SELECT_BEST_OFFER error: {str(e)}")
        logger.error(traceback.format_exc())
        
        return SelectOfferResponse(
            selected_offer=None,
            reason=f"ERROR: {str(e)}"
        )


# ==================== ADD FROM FAVORITE TO CART ====================

class AddFromFavoriteRequest(BaseModel):
    """Request to add item from favorite to cart"""
    favorite_id: str
    qty: float = 1.0  # Requested quantity in base units (kg/l)
    
class AddFromFavoriteResponse(BaseModel):
    """Response for add-from-favorite"""
    status: str  # "ok", "not_found", "insufficient_data", "error"
    selected_offer: Optional[SelectedOffer] = None
    top_candidates: Optional[List[dict]] = None
    debug_log: Optional[dict] = None
    message: Optional[str] = None
    # P0+P1 Diagnostic fields (UI visible)
    build_sha: Optional[str] = None
    request_id: Optional[str] = None
    ref_product_core: Optional[str] = None
    selected_product_core: Optional[str] = None
    ref_unit_type: Optional[str] = None
    selected_unit_type: Optional[str] = None
    packs_needed: Optional[int] = None
    computed_total_cost: Optional[float] = None
    # P0.5: min_order_qty support
    min_order_qty: Optional[int] = None
    actual_qty: Optional[float] = None


@api_router.post("/cart/add-from-favorite", response_model=AddFromFavoriteResponse)
async def add_from_favorite_to_cart(request: AddFromFavoriteRequest, current_user: dict = Depends(get_current_user)):
    """Add item from favorites to cart with ENHANCED BEST PRICE SEARCH
    
    VERSION 4.0 (P0 Guards Fix):
    - Guards applied to CANDIDATE, not reference
    - Fixed active filter: offer_status="ACTIVE"
    - Diagnostic fields: build_sha, request_id, counts, guards_applied
    - SEARCH_SUMMARY log for tracing
    
    CRITICAL RULES:
    1. NEVER use supplier_item_id from favorite directly
    2. ALWAYS run full search
    3. Guards check CANDIDATE.name_raw (forbidden + required_anchors)
    4. brand_critical=false: brand COMPLETELY IGNORED
    5. brand_critical=true: filter by brand_id
    6. Pack must be in range: ±20% of reference
    7. Return structured response (never 500)
    """
    import logging
    import uuid
    import json
    
    logger = logging.getLogger(__name__)
    
    # Generate unique request_id for tracing
    request_id = str(uuid.uuid4())[:8]
    
    try:
        # Step 1: Get favorite from DB
        logger.info(f"🔍 ADD_FROM_FAVORITE [request_id={request_id}]: Looking for favorite_id={request.favorite_id}, userId={current_user['id']}")
        favorite = await db.favorites.find_one({"id": request.favorite_id, "userId": current_user['id']}, {"_id": 0})
        
        if not favorite:
            logger.warning(f"❌ ADD_FROM_FAVORITE: Favorite not found: {request.favorite_id}")
            # Check if favorite exists with different userId
            any_fav = await db.favorites.find_one({"id": request.favorite_id}, {"_id": 0, "userId": 1})
            if any_fav:
                logger.warning(f"   Favorite exists but with different userId: {any_fav.get('userId')}")
            return AddFromFavoriteResponse(
                status="not_found",
                message="Favorite not found"
            )
        
        # Step 2: Determine brand_critical (support both schema v1 and v2)
        brand_critical = favorite.get('brand_critical')
        
        # If brand_critical is not set or not boolean, use legacy brandMode
        if brand_critical is None or not isinstance(brand_critical, bool):
            brand_mode = favorite.get('brandMode', 'ANY')
            brand_critical = (brand_mode == 'STRICT')
        
        # Step 3: Build reference item for search
        reference_name = favorite.get('reference_name') or favorite.get('productName', '')
        brand_id = favorite.get('brand_id') or favorite.get('brandId')
        unit_norm = favorite.get('unit_norm') or favorite.get('unit', 'kg')
        pack_size = favorite.get('pack_size')  # Remove extract_pack_value call
        
        # Extract origin for non-branded items
        origin_country = favorite.get('origin_country')
        origin_region = favorite.get('origin_region')
        origin_city = favorite.get('origin_city')
        
        # P0 NEW RULE: "География = Бренд" - каскадный приоритет: Город > Регион > Страна
        # Если указан любой географический атрибут, он становится критичным фильтром
        from geography_extractor import get_geo_filter_value
        
        geo_as_brand = False
        geo_filter_value = None
        geo_filter_field = None
        geo_filter_type = None
        original_brand_id = brand_id
        
        geo_filter_value, geo_filter_field, geo_filter_type = get_geo_filter_value(favorite)
        
        if geo_filter_value:
            geo_as_brand = True
            brand_critical = True
            brand_id = geo_filter_value
            logger.info(f"   🌍 GEO_AS_BRAND: {geo_filter_type}='{geo_filter_value}' → brand_critical=True (was brand_id='{original_brand_id}')")
        
        # Legacy alias for backward compatibility
        country_as_brand = geo_as_brand and geo_filter_type == 'country'
        
        reference_item = {
            'name_raw': reference_name,
            'brand_id': brand_id,
            'origin_country': origin_country,
            'origin_region': origin_region,
            'origin_city': origin_city,
            'unit_norm': unit_norm,
            'pack': pack_size
        }
        
        logger.info(f"🎯 ADD_FROM_FAVORITE:")
        logger.info(f"   favorite_id={request.favorite_id}")
        logger.info(f"   reference_name='{reference_name[:50]}'")
        logger.info(f"   brand_critical={brand_critical}, brand_id={brand_id}")
        
        # P0: Parse reference pack using unit_normalizer
        ref_pack_info = parse_pack_from_text(reference_name)
        logger.info(f"   ref_pack: type={ref_pack_info.unit_type.value}, qty={ref_pack_info.base_qty}, conf={ref_pack_info.confidence}")
        
        if origin_country:
            origin_str = origin_country
            if origin_region:
                origin_str += f"/{origin_region}"
            if origin_city:
                origin_str += f"/{origin_city}"
            logger.info(f"   origin={origin_str}")
        logger.info(f"   unit={unit_norm}, pack={pack_size}, qty={request.qty}")
        
        # Step 4: Get all SUPPLIER_ITEMS (candidates) - ПРАВИЛЬНАЯ КОЛЛЕКЦИЯ!
        # Using {"active": True} as offer_status field is not populated yet
        supplier_items_cursor = db.supplier_items.find({"active": True}, {"_id": 0})
        supplier_items = await supplier_items_cursor.to_list(length=None)
        
        logger.info(f"   📊 Loaded {len(supplier_items)} ACTIVE supplier_items")
        
        # Build candidates from supplier_items
        candidates = []
        for si in supplier_items:
            # Build candidate item - USE SUPPLIER_ITEMS DATA
            candidate = {
                'id': si['id'],
                'supplier_company_id': si['supplier_company_id'],
                'name_raw': si['name_raw'],
                'price': si['price'],
                'super_class': si.get('super_class'),  # КРИТИЧНО!
                'product_core_id': si.get('product_core_id'),  # P1: для strict matching
                'unit_norm': si['unit_norm'],
                'brand_id': si.get('brand_id'),
                'origin_country': si.get('origin_country'),
                'origin_region': si.get('origin_region'),
                'origin_city': si.get('origin_city'),
                'net_weight_kg': si.get('net_weight_kg'),
                'net_volume_l': si.get('net_volume_l'),
                'base_unit': si.get('base_unit', si['unit_norm']),
                # P0.3/P0.5: min_order_qty for total_cost calculation
                'min_order_qty': si.get('min_order_qty', 1),
                'pack_qty': si.get('pack_qty', 1),
            }
            candidates.append(candidate)
        
        logger.info(f"   Total candidates: {len(candidates)}")
        
        # Step 5: Get company map for supplier names
        companies = await db.companies.find({}, {"_id": 0}).to_list(1000)
        company_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in companies}
        
        # Step 6: ПРОСТОЙ ПОИСК С ДЕТАЛЬНЫМ ЛОГИРОВАНИЕМ
        logger.info(f"🔍 НАЧАЛО ПОИСКА")
        
        # Detect super_class using UNIVERSAL mapper
        from universal_super_class_mapper import detect_super_class
        from p0_hotfix_stabilization import (
            calculate_match_percent, 
            has_negative_keywords,
            has_required_anchors,  # ДОБАВЛЕНО
            parse_pack_value,
            SearchLogger,
            check_seed_dict_match,  # NEW: seed_dict_rules support
            check_price_sanity,     # NEW: price sanity check
            check_category_mismatch,  # P0 FIX: seafood vs meat
            check_attribute_compatibility,  # P0 FIX: с хвостом vs без хвоста
        )
        
        # Initialize structured logger
        search_logger = SearchLogger(reference_id=request.favorite_id)
        
        # Classify reference super_class
        ref_super_class, confidence = detect_super_class(reference_name)
        
        # P1: Detect product_core for reference (after super_class)
        from product_core_classifier import detect_product_core as classify_core
        ref_product_core, ref_core_conf = classify_core(reference_name, ref_super_class)
        logger.info(f"   ref_product_core: {ref_product_core} (conf={ref_core_conf:.2f})")
        
        # Set context
        search_logger.set_context(
            reference_name=reference_name,
            brand_critical=brand_critical,
            brand_id=brand_id,
            requested_qty=request.qty
        )
        
        if not ref_super_class:
            logger.warning(f"⚠️ super_class не определён для '{reference_name}' (confidence={confidence:.2f})")
            search_logger.set_outcome('insufficient_data', 'INSUFFICIENT_CLASSIFICATION')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="insufficient_data",
                message="Категория продукта не определена"
            )
        
        logger.info(f"   super_class: {ref_super_class} (confidence={confidence:.2f})")
        search_logger.set_context(ref_super_class=ref_super_class, confidence=confidence)
        
        # Step 7: Filter candidates step-by-step with DETAILED LOGGING
        total_candidates = len(candidates)
        logger.info(f"   Total candidates: {total_candidates}")
        
        # Filter 1: Product Core Match (P1 STRICT MATCHING - NO FALLBACK)
        # Rule: Match ONLY by product_core_id
        # If no product_core or no matches → NOT_FOUND
        
        if not ref_product_core or ref_core_conf < 0.3:
            # Cannot determine product_core reliably
            logger.error(f"❌ Cannot determine product_core for '{reference_name}' (conf={ref_core_conf:.2f})")
            search_logger.set_outcome('not_found', 'CORE_NOT_DETECTED')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=f"Не удалось определить категорию товара (product_core)",
                build_sha=BUILD_SHA,
                request_id=request_id,
                ref_product_core=ref_product_core,
                ref_unit_type=ref_pack_info.unit_type.value if ref_pack_info else None,
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'reason_code': 'CORE_NOT_DETECTED',
                    'ref_product_core': ref_product_core,
                    'ref_core_conf': ref_core_conf,
                    'counts': {'total': total_candidates}
                }
            )
        
        # STRICT: Match only by product_core_id (NO FALLBACK)
        step1 = [
            c for c in candidates 
            if c.get('product_core_id') == ref_product_core
            and c.get('price', 0) > 0
        ]
        logger.info(f"   После product_core filter (STRICT, core={ref_product_core}): {len(step1)}")
        search_logger.set_count('after_product_core_strict', len(step1))
        
        # If no matches by core → NOT_FOUND (no fallback!)
        if len(step1) == 0:
            logger.error(f"❌ NO CANDIDATES for product_core={ref_product_core}")
            logger.error(f"   Available cores in catalog: {list(set(c.get('product_core_id') for c in candidates if c.get('product_core_id')))[:10]}")
            search_logger.set_outcome('not_found', 'CORE_NO_CANDIDATES')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=f"Не найдено товаров категории '{ref_product_core}'",
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'reason_code': 'CORE_NO_CANDIDATES',
                    'ref_product_core': ref_product_core,
                    'counts': {
                        'total': total_candidates,
                        'after_product_core_strict': 0
                    }
                }
            )
        
        search_logger.set_count('after_super_class', len(step1))
        search_logger.set_count('after_super_class', len(step1))
        
        # P0.2 FALLBACK: Если не найдено по super_class, пробуем 'other' с keyword matching  
        if len(step1) == 0:
            logger.warning(f"   ⚠️ Пробуем fallback на 'other' категорию с keyword matching...")
            
            # Try matching within 'other' category by keywords
            import re
            ref_keywords = set(re.findall(r'\w+', reference_name.lower()))
            ref_keywords = {w for w in ref_keywords if len(w) >= 4}  # Only meaningful words
            
            step1_fallback = []
            for c in candidates:
                if c.get('super_class') == 'other' and c.get('price', 0) > 0:
                    cand_keywords = set(re.findall(r'\w+', (c.get('name_raw') or '').lower()))
                    common = ref_keywords & cand_keywords
                    
                    # Require at least 2 common keywords
                    if len(common) >= 2:
                        c['_match_score'] = len(common) / len(ref_keywords) if ref_keywords else 0
                        step1_fallback.append(c)
            
            if step1_fallback:
                step1 = step1_fallback
                logger.info(f"   ✅ Fallback 'other': найдено {len(step1)} кандидатов")
            else:
                logger.error(f"   ❌ Fallback failed: нет совпадений")
        
        if len(step1) == 0:
            logger.error(f"❌ NO CANDIDATES after super_class filter")
            logger.error(f"   Reference super_class: {ref_super_class}")
            logger.error(f"   Total active: {sum(1 for si in supplier_items if si.get('active') == True)}")
            logger.error(f"   With super_class: {sum(1 for c in candidates if c.get('super_class'))}")
            logger.error(f"   Sample super_classes: {list(set(c.get('super_class') for c in candidates if c.get('super_class')))[:10]}")
            search_logger.set_outcome('not_found', 'NO_MATCHING_SUPER_CLASS')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=f"Не найдено товаров с категорией '{ref_super_class}'",
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'counts': {'total': total_candidates, 'after_super_class': 0}
                }
            )
        
        # Filter 2: GUARDS (FORBIDDEN + REQUIRED ANCHORS + SEED_DICT + CATEGORY + ATTRIBUTES) - Applied to CANDIDATE!
        step2_guards = []
        rejected_forbidden = 0
        rejected_anchors = 0
        rejected_seed_dict = 0
        rejected_category = 0  # P0 FIX: seafood vs meat
        rejected_attributes = 0  # P0 FIX: с хвостом vs без хвоста
        
        for c in step1:
            candidate_name = c.get('name_raw', '')
            
            # Check 0 (CRITICAL P0): Category mismatch - SEAFOOD vs MEAT
            # This must be first to prevent absurd matches like "кальмар" → "курица"
            cat_match, cat_reason = check_category_mismatch(reference_name, candidate_name, ref_super_class)
            if not cat_match:
                rejected_category += 1
                logger.debug(f"   ❌ CATEGORY_MISMATCH: '{candidate_name[:40]}' - {cat_reason}")
                continue
            
            # Check 0.5 (CRITICAL P0): Attribute compatibility - с хвостом vs без хвоста
            attr_match, attr_reason = check_attribute_compatibility(reference_name, candidate_name)
            if not attr_match:
                rejected_attributes += 1
                logger.debug(f"   ❌ ATTRIBUTE_MISMATCH: '{candidate_name[:40]}' - {attr_reason}")
                continue
            
            # Check 1: Forbidden tokens (e.g., растительн, веган, сырник)
            has_forbidden, forbidden_word = has_negative_keywords(candidate_name, ref_super_class)
            if has_forbidden:
                rejected_forbidden += 1
                logger.debug(f"   ❌ FORBIDDEN: '{candidate_name[:40]}' contains '{forbidden_word}'")
                continue
            
            # Check 2: Required anchors (e.g., васаби must contain васаби/wasabi)
            # ENHANCED: Pass reference_name for dynamic anchor detection
            has_anchor, found_anchor = has_required_anchors(candidate_name, ref_super_class, reference_name)
            if not has_anchor:
                rejected_anchors += 1
                logger.debug(f"   ❌ MISSING_ANCHOR: '{candidate_name[:40]}' missing required anchor '{found_anchor}' for {ref_super_class}")
                continue
            
            # Check 3: seed_dict_rules attributes (fat%, grade, size)
            # e.g., "Молоко 3.2%" must match "3.2%", "Креветки 16/20" must match "16/20"
            seed_match, seed_reason = check_seed_dict_match(reference_name, candidate_name)
            if not seed_match:
                rejected_seed_dict += 1
                logger.debug(f"   ❌ SEED_DICT_MISMATCH: '{candidate_name[:40]}' - {seed_reason}")
                continue
            
            # Passed all guards
            step2_guards.append(c)
        
        logger.info(f"   После guards filter: {len(step2_guards)} (rejected: category={rejected_category}, attributes={rejected_attributes}, forbidden={rejected_forbidden}, anchor={rejected_anchors}, seed_dict={rejected_seed_dict})")
        search_logger.set_count('after_guards', len(step2_guards))
        search_logger.set_count('rejected_by_category_mismatch', rejected_category)
        search_logger.set_count('rejected_by_attribute_mismatch', rejected_attributes)
        search_logger.set_count('rejected_by_forbidden', rejected_forbidden)
        search_logger.set_count('rejected_by_missing_anchor', rejected_anchors)
        search_logger.set_count('rejected_by_seed_dict', rejected_seed_dict)
        
        if len(step2_guards) == 0:
            logger.error(f"❌ NO CANDIDATES after guards filter")
            search_logger.set_outcome('not_found', 'REJECTED_BY_GUARDS')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=f"Не найдено товаров, прошедших guards (forbidden={rejected_forbidden}, missing_anchor={rejected_anchors})",
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'guards_applied': True,
                    'counts': {
                        'total': total_candidates,
                        'after_super_class': len(step1),
                        'after_guards': 0,
                        'rejected_by_forbidden': rejected_forbidden,
                        'rejected_by_missing_anchor': rejected_anchors
                    }
                }
            )
        
        # Filter 3: Brand (if brand_critical=ON) - STRICT + TEXT FALLBACK
        # P0 NEW: COUNTRY_AS_BRAND mode - фильтрация по стране вместо бренда
        if brand_critical and brand_id:
            from p0_hotfix_stabilization import load_brand_aliases, extract_brand_from_text
            
            # Check if we're in GEO_AS_BRAND mode (city/region/country cascade)
            if geo_as_brand:
                # GEO_AS_BRAND: фильтруем по соответствующему географическому полю
                logger.info(f"   🌍 GEO_AS_BRAND mode: filtering by {geo_filter_field}='{geo_filter_value}'")
                
                step3_brand = []
                for c in step2_guards:
                    cand_geo_value = (c.get(geo_filter_field) or '').strip().upper()
                    if cand_geo_value == geo_filter_value:
                        step3_brand.append(c)
                
                logger.info(f"   После geo filter ({geo_filter_type}='{geo_filter_value}'): {len(step3_brand)}")
                search_logger.set_count('after_geo_filter', len(step3_brand))
                
                # Geo diagnostics if no matches
                if len(step3_brand) == 0:
                    available_values = list(set(
                        (c.get(geo_filter_field) or '').strip().upper() 
                        for c in step2_guards 
                        if c.get(geo_filter_field)
                    ))[:10]
                    
                    geo_type_labels = {'city': 'Город', 'region': 'Регион', 'country': 'Страна'}
                    geo_label = geo_type_labels.get(geo_filter_type, 'Локация')
                    
                    logger.warning(f"   ❌ {geo_label} '{geo_filter_value}' не найден среди кандидатов")
                    logger.warning(f"   Available {geo_filter_type}s: {available_values}")
                    search_logger.set_brand_diagnostics(
                        requested_brand_id=f"{geo_filter_type.upper()}:{geo_filter_value}",
                        available_brands_id=available_values,
                        available_brands_text=[]
                    )
            else:
                # Standard brand matching
                # Step A: Strict brand_id filter
                step3_brand_strict = [c for c in step2_guards if c.get('brand_id') == brand_id]
                logger.info(f"   После brand_id filter (strict, brand_id={brand_id}): {len(step3_brand_strict)}")
                search_logger.set_count('after_brand_id_strict', len(step3_brand_strict))
                
                # Step B: Text fallback если strict дал 0
                if len(step3_brand_strict) == 0:
                    logger.warning(f"   ⚠️ Пробуем brand text fallback...")
                    
                    brand_aliases = load_brand_aliases()
                    step3_brand_fallback = []
                    
                    for c in step2_guards:
                        # Extract brand from text
                        brand_from_text = extract_brand_from_text(c.get('name_raw', ''), brand_aliases)
                        c['_brand_from_text'] = brand_from_text
                        
                        if brand_from_text == brand_id:
                            step3_brand_fallback.append(c)
                    
                    logger.info(f"   После brand text fallback: {len(step3_brand_fallback)}")
                    search_logger.set_count('after_brand_text_fallback', len(step3_brand_fallback))
                    
                    step3_brand = step3_brand_fallback
                else:
                    step3_brand = step3_brand_strict
                
                # Brand diagnostics
                if len(step3_brand) == 0:
                    # Collect available brands for diagnostics
                    brands_by_id = [c.get('brand_id') for c in step2_guards if c.get('brand_id')]
                    top_brands_id = list(set(brands_by_id))[:5]
                    
                    brands_by_text = [c.get('_brand_from_text') for c in step2_guards if c.get('_brand_from_text')]
                    top_brands_text = list(set(brands_by_text))[:5]
                    
                    logger.warning(f"   Бренд '{brand_id}' не найден")
                    logger.warning(f"   Available brands (by ID): {top_brands_id}")
                    logger.warning(f"   Available brands (by text): {top_brands_text}")
                    
                    search_logger.set_brand_diagnostics(
                        requested_brand_id=brand_id,
                        available_brands_id=top_brands_id,
                        available_brands_text=top_brands_text
                    )
                    
                    # ==================== P0 FIX: BRAND NOT FOUND FALLBACK ====================
                    # If brand is not found in database, fallback to product name matching
                    # This handles cases where the brand is unique or not in the brand master
                    
                    if len(step2_guards) > 0:
                        logger.warning(f"   🔄 BRAND_FALLBACK: Бренд '{brand_id}' не найден, ищем по названию товара...")
                        
                        # Extract product type from reference name (remove brand)
                        ref_name_without_brand = reference_name.lower()
                        # Remove brand from reference name for better matching
                        if brand_id:
                            ref_name_without_brand = ref_name_without_brand.replace(brand_id.lower(), '').strip()
                        
                        # Use rapidfuzz to find best matching candidates by name
                        from rapidfuzz import fuzz
                        
                        brand_fallback_candidates = []
                        for c in step2_guards:
                            cand_name = c.get('name_raw', '').lower()
                            # Calculate name similarity without brand
                            cand_without_brand = cand_name
                            if brand_id:
                                cand_without_brand = cand_without_brand.replace(brand_id.lower(), '').strip()
                            
                            similarity = fuzz.token_set_ratio(ref_name_without_brand, cand_without_brand)
                            
                            # Accept if similarity >= 70%
                            if similarity >= 70:
                                c['_brand_fallback_score'] = similarity
                                c['_brand_fallback'] = True
                                brand_fallback_candidates.append(c)
                        
                        # Sort by similarity score
                        brand_fallback_candidates.sort(key=lambda x: x.get('_brand_fallback_score', 0), reverse=True)
                        
                        logger.info(f"   После brand_fallback (name similarity >= 70%): {len(brand_fallback_candidates)}")
                        search_logger.set_count('after_brand_fallback', len(brand_fallback_candidates))
                        
                        if brand_fallback_candidates:
                            step3_brand = brand_fallback_candidates
                            logger.info(f"   ✅ BRAND_FALLBACK успешно: найдено {len(step3_brand)} похожих товаров")
            
            search_logger.set_count('after_brand_filter', len(step3_brand))
        else:
            step3_brand = step2_guards
            logger.info(f"   Brand filter: SKIP (brand_critical={brand_critical})")
            search_logger.set_count('after_brand_filter', len(step3_brand))
        
        if len(step3_brand) == 0:
            # Determine error message based on mode
            if geo_as_brand:
                geo_type_labels = {'city': 'города', 'region': 'региона', 'country': 'страны'}
                geo_label = geo_type_labels.get(geo_filter_type, 'локации')
                error_message = f"Не найдено товаров из {geo_label} '{geo_filter_value}'"
                reason_code = f'{geo_filter_type.upper()}_REQUIRED_NOT_FOUND'
            else:
                error_message = f"Не найдено товаров бренда '{brand_id}'"
                reason_code = 'BRAND_REQUIRED_NOT_FOUND'
            
            search_logger.set_outcome('not_found', reason_code)
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=error_message,
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'guards_applied': True,
                    'geo_as_brand': geo_as_brand,
                    'geo_filter_type': geo_filter_type,
                    'geo_filter_value': geo_filter_value,
                    'country_as_brand': country_as_brand,  # Legacy
                    'counts': {
                        'total': total_candidates,
                        'after_super_class': len(step1),
                        'after_guards': len(step2_guards),
                        'after_brand': 0
                    }
                }
            )
        
        # Filter 4: Unit Compatibility + Pack Calculation (P0 NEW LOGIC)
        # Added: pack_outlier rule (reject if packs_needed > 20)
        # Added: price_sanity rule (reject if price is absurdly low)
        step4_unit_compatible = []
        unit_mismatch_count = 0
        pack_calculated_count = 0
        pack_outlier_count = 0
        price_sanity_rejected = 0
        
        PACK_OUTLIER_THRESHOLD = 20  # Reject if > 20 упаковок
        
        # Get reference price for sanity check (estimate from product name/category)
        ref_price_estimate = None
        
        for c in step3_brand:
            candidate_name = c.get('name_raw', '')
            candidate_price = c.get('price', 0)
            
            # Parse candidate pack
            cand_pack_info = parse_pack_from_text(candidate_name)
            
            # Calculate packs_needed
            packs_needed, total_cost_mult, calc_reason = calculate_packs_needed(
                ref_pack_info, cand_pack_info
            )
            
            # Check for UNIT_MISMATCH (critical rejection)
            if "UNIT_MISMATCH" in calc_reason:
                unit_mismatch_count += 1
                logger.debug(f"   ❌ UNIT_MISMATCH: {candidate_name[:40]} - {calc_reason}")
                continue  # REJECT this candidate
            
            # Check for pack_outlier (>20 упаковок)
            if packs_needed and packs_needed > PACK_OUTLIER_THRESHOLD:
                pack_outlier_count += 1
                logger.debug(f"   ❌ PACK_OUTLIER: {candidate_name[:40]} - packs_needed={packs_needed} > {PACK_OUTLIER_THRESHOLD}")
                continue  # REJECT this candidate
            
            # NEW: Price sanity check
            # Use first valid candidate price as reference for comparison
            if ref_price_estimate is None and candidate_price > 0:
                ref_price_estimate = candidate_price * 2  # Assume reference is ~2x average price
            
            if ref_price_estimate:
                price_sane, price_reason = check_price_sanity(
                    reference_name, ref_price_estimate,
                    candidate_name, candidate_price,
                    ref_super_class
                )
                if not price_sane:
                    price_sanity_rejected += 1
                    logger.debug(f"   ❌ PRICE_INSANE: {candidate_name[:40]} - {price_reason}")
                    continue  # REJECT this candidate
            
            # Store pack calculation info
            c['_pack_info'] = cand_pack_info
            c['_packs_needed'] = packs_needed
            c['_total_cost_mult'] = total_cost_mult
            c['_calc_reason'] = calc_reason
            c['_pack_explanation'] = format_pack_explanation(ref_pack_info, cand_pack_info, packs_needed) if packs_needed else ""
            
            # Calculate pack penalty for match_percent
            pack_penalty = calculate_pack_penalty(packs_needed, cand_pack_info.unit_type)
            c['_pack_score_penalty'] = pack_penalty
            
            step4_unit_compatible.append(c)
            if packs_needed:
                pack_calculated_count += 1
        
        logger.info(f"   После unit compatibility filter: {len(step4_unit_compatible)}")
        logger.info(f"   Rejected: {unit_mismatch_count} unit_mismatch, {pack_outlier_count} pack_outlier")
        logger.info(f"   Pack calculated: {pack_calculated_count}")
        search_logger.set_count('after_unit_filter', len(step4_unit_compatible))
        search_logger.set_count('rejected_unit_mismatch', unit_mismatch_count)
        search_logger.set_count('rejected_pack_outlier', pack_outlier_count)
        search_logger.set_count('pack_calculated', pack_calculated_count)
        
        if len(step4_unit_compatible) == 0:
            # Determine reason
            if unit_mismatch_count > 0 and pack_outlier_count == 0:
                reason_code = 'UNIT_MISMATCH_ALL_REJECTED'
                message = f"Не найдено товаров с совместимыми единицами измерения (rejected: {unit_mismatch_count} unit_mismatch)"
            elif pack_outlier_count > 0 and unit_mismatch_count == 0:
                reason_code = 'PACK_OUTLIER_ALL_REJECTED'
                message = f"Не найдено товаров с подходящей фасовкой (rejected: {pack_outlier_count} слишком малая фасовка, требуется >{PACK_OUTLIER_THRESHOLD} упаковок)"
            else:
                reason_code = 'UNIT_AND_PACK_REJECTED'
                message = f"Не найдено подходящих товаров (rejected: {unit_mismatch_count} unit_mismatch, {pack_outlier_count} pack_outlier)"
            
            search_logger.set_outcome('not_found', reason_code)
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=message,
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'guards_applied': True,
                    'reason_code': reason_code,
                    'counts': {
                        'total': total_candidates,
                        'after_product_core': len(step1),
                        'after_guards': len(step2_guards),
                        'after_brand': len(step3_brand),
                        'after_unit_filter': 0,
                        'rejected_unit_mismatch': unit_mismatch_count,
                        'rejected_pack_outlier': pack_outlier_count
                    }
                }
            )
        
        # P0.5: Sort by TOTAL_COST with min_order_qty consideration
        # Formula: total_cost = ceil(user_qty / min_order_qty) * min_order_qty * price
        # 1. Товары с известным packs_needed → по total_cost
        # 2. Товары с неизвестным packs_needed → в конец
        import math
        
        user_qty = request.qty or 1  # User requested quantity
        
        def sort_key(c):
            packs = c.get('_packs_needed')
            mult = c.get('_total_cost_mult', 1.0)
            price = c.get('price', 999999)
            penalty = c.get('_pack_score_penalty', 0)
            min_order_qty = c.get('min_order_qty', 1) or 1
            
            # Если packs не определены → штраф
            if not packs:
                return (999999, penalty, price)
            
            # P0.5: Calculate total_cost with min_order_qty
            # actual_qty = ceil(user_qty / min_order_qty) * min_order_qty
            actual_qty = math.ceil(user_qty / min_order_qty) * min_order_qty
            
            # total_cost = actual_qty * price * pack_multiplier
            total_cost = actual_qty * price * mult
            
            # Store for later use
            c['_actual_qty'] = actual_qty
            c['_total_cost_p05'] = total_cost
            
            # Учитываем penalty (higher penalty = higher cost)
            adjusted_cost = total_cost * (1 + penalty * 0.01)
            
            return (adjusted_cost, penalty, price)
        
        step4_unit_compatible.sort(key=sort_key)
        logger.info(f"   Отсортировано по total_cost (P0.5) с учётом min_order_qty, user_qty={user_qty}")
        
        winner = step4_unit_compatible[0]
        
        # ==================== P0 FIX: SIMILARITY THRESHOLD CHECK ====================
        # Calculate preliminary match_percent to check against threshold
        # Thresholds: 95% for brand_critical, 90% for brand_not_critical
        
        THRESHOLD_BRAND_CRITICAL = 95  # User requested: минимум 95% для brand_critical
        THRESHOLD_BRAND_NOT_CRITICAL = 90  # User requested: минимум 90% для brand_not_critical
        
        # Calculate actual name similarity for accurate threshold check
        from rapidfuzz import fuzz
        
        winner_name = (winner.get('name_raw') or '').lower()
        ref_name_lower = reference_name.lower()
        name_similarity = fuzz.token_set_ratio(ref_name_lower, winner_name)
        
        # Calculate preliminary match score using new formula
        # Name similarity: 50% weight, Core: 25 points, Guards: 15 points, Brand: 10 points
        prelim_base_score = (name_similarity / 100) * 50  # Name similarity contribution
        if winner.get('product_core_id') == ref_product_core:
            prelim_base_score += 25  # Core match
        prelim_base_score += 15  # Guards passed
        if brand_critical and winner.get('brand_id') == brand_id:
            prelim_base_score += 10  # Brand match
        
        pack_penalty_check = winner.get('_pack_score_penalty', 0)
        prelim_match_percent = max(0, min(100, int(prelim_base_score - pack_penalty_check)))
        
        # Determine threshold based on brand_critical
        required_threshold = THRESHOLD_BRAND_CRITICAL if brand_critical else THRESHOLD_BRAND_NOT_CRITICAL
        
        logger.info(f"   💯 Match check: name_sim={name_similarity}%, prelim_match={prelim_match_percent}%, threshold={required_threshold}% (brand_critical={brand_critical})")
        
        # Check if match meets threshold
        if prelim_match_percent < required_threshold:
            logger.warning(f"   ⚠️ LOW_MATCH: {prelim_match_percent}% < {required_threshold}% - Will return original favorite")
            
            # Try to find original favorite item (STICK WITH FAVORITE logic)
            original_supplier_id = favorite.get('originalSupplierId')
            original_product_id = favorite.get('productId')
            original_ref_name = favorite.get('reference_name') or favorite.get('productName')
            
            original_item = None
            
            # Strategy 1: Find by supplier_id + product_id (most reliable)
            if original_supplier_id and original_product_id:
                original_item = await db.supplier_items.find_one({
                    'supplier_company_id': original_supplier_id,
                    'active': True,
                    '$or': [
                        {'id': original_product_id},
                        {'unique_key': {'$regex': original_product_id, '$options': 'i'}},
                    ]
                }, {'_id': 0})
                
            # Strategy 2: Find by exact reference_name match (fallback)
            if not original_item and original_ref_name:
                original_item = await db.supplier_items.find_one({
                    'active': True,
                    'name_raw': original_ref_name
                }, {'_id': 0})
                
            # Strategy 3: Find by name_norm similarity (last resort)
            if not original_item and original_ref_name:
                # Try partial match on normalized name
                name_prefix = original_ref_name[:30].lower()  # First 30 chars
                original_item = await db.supplier_items.find_one({
                    'active': True,
                    'name_norm': {'$regex': f'^{name_prefix[:20]}', '$options': 'i'}
                }, {'_id': 0})
            
            if original_item:
                logger.info(f"   ✅ STICK_WITH_FAVORITE: Returning original item: {original_item.get('name_raw', '')[:50]}")
                winner = original_item
                winner['_stick_with_favorite'] = True
                winner['_low_match_fallback'] = True
                # Recalculate costs for original item
                orig_min_qty = winner.get('min_order_qty', 1) or 1
                winner['_actual_qty'] = math.ceil(user_qty / orig_min_qty) * orig_min_qty
                winner['_total_cost_p05'] = winner['_actual_qty'] * winner.get('price', 0)
                winner['_packs_needed'] = 1
                # Set 100% match for original
                prelim_match_percent = 100
            else:
                # No original found - keep current winner but warn
                logger.warning(f"   ⚠️ Original item not found by any strategy. Keeping best match with {prelim_match_percent}% confidence")
                # Mark as low-confidence match
                winner['_low_match_warning'] = True
                winner['_match_below_threshold'] = True
        
        # HARD RULE: product_core MUST match (P1 CRITICAL)
        # EXCEPTION: If stick_with_favorite is active, skip this check (original item is trusted)
        winner_product_core = winner.get('product_core_id')
        if winner_product_core != ref_product_core and not winner.get('_stick_with_favorite'):
            logger.error(f"❌ CORE_MISMATCH: ref={ref_product_core} vs winner={winner_product_core}")
            logger.error(f"   Winner name: {winner.get('name_raw', '')[:60]}")
            search_logger.set_outcome('not_found', 'CORE_MISMATCH')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=f"Найденный товар не соответствует категории (ref={ref_product_core}, found={winner_product_core})",
                build_sha=BUILD_SHA,
                request_id=request_id,
                ref_product_core=ref_product_core,
                selected_product_core=winner_product_core,
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'reason_code': 'CORE_MISMATCH',
                    'ref_product_core': ref_product_core,
                    'winner_product_core': winner_product_core,
                    'winner_name': winner.get('name_raw', ''),
                    'counts': {
                        'total': total_candidates,
                        'after_product_core': len(step1),
                        'after_guards': len(step2_guards),
                        'after_brand': len(step3_brand),
                        'after_unit_filter': len(step4_unit_compatible)
                    }
                }
            )
        elif winner.get('_stick_with_favorite') and winner_product_core != ref_product_core:
            logger.info(f"   ⚠️ CORE_MISMATCH bypassed for stick_with_favorite (trusted original item)")
        
        # ==================== P0 FIX: STICK WITH FAVORITE LOGIC ====================
        # If the found winner is MORE EXPENSIVE than the original favorite item,
        # return the original favorite item instead.
        # This ensures BestPrice never suggests a worse deal.
        
        original_supplier_id = favorite.get('originalSupplierId')
        original_product_id = favorite.get('productId')
        
        stick_with_favorite = False
        original_item = None
        
        if original_supplier_id and original_product_id:
            # Try to find the original item in supplier_items
            original_item = await db.supplier_items.find_one({
                'supplier_company_id': original_supplier_id,
                'active': True,
                '$or': [
                    {'id': original_product_id},
                    # Also check by name similarity for legacy data
                    {'name_norm': {'$regex': reference_name[:20].lower(), '$options': 'i'}}
                ]
            }, {'_id': 0})
            
            if original_item:
                winner_total_cost = winner.get('_total_cost_p05', winner.get('price', 0) * user_qty)
                original_price = original_item.get('price', 0)
                original_min_qty = original_item.get('min_order_qty', 1) or 1
                original_actual_qty = math.ceil(user_qty / original_min_qty) * original_min_qty
                original_total_cost = original_actual_qty * original_price
                
                # If winner is more expensive → stick with original
                if winner_total_cost > original_total_cost:
                    logger.info(f"   🔄 STICK_WITH_FAVORITE: winner_cost={winner_total_cost:.2f} > original_cost={original_total_cost:.2f}")
                    logger.info(f"   Returning original item: {original_item.get('name_raw', '')[:40]}")
                    
                    # Replace winner with original item
                    winner = original_item
                    winner['_actual_qty'] = original_actual_qty
                    winner['_total_cost_p05'] = original_total_cost
                    winner['_packs_needed'] = 1
                    winner['_pack_explanation'] = "Оригинальный товар из избранного (дешевле альтернатив)"
                    winner['_stick_with_favorite'] = True
                    stick_with_favorite = True
                else:
                    logger.info(f"   ✅ Found cheaper alternative: winner_cost={winner_total_cost:.2f} < original_cost={original_total_cost:.2f}")
        
        # КРИТИЧНО: Определяем supplier_id СРАЗУ после winner
        supplier_id = winner.get('supplier_company_id')
        
        # Get supplier names
        companies = await db.companies.find({}, {"_id": 0}).to_list(1000)
        company_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in companies}
        
        if not supplier_id:
            logger.error(f"❌ supplier_company_id is None in winner!")
            logger.error(f"   Winner keys: {list(winner.keys())}")
            return AddFromFavoriteResponse(
                status="error",
                message="Internal error: supplier_company_id missing"
            )
        
        logger.info(f"✅ НАЙДЕНО: {len(step4_unit_compatible)} кандидатов")
        logger.info(f"   Победитель: {winner.get('name_raw', '')[:40]}")
        logger.info(f"   Цена: {winner.get('price')}₽")
        logger.info(f"   Packs needed: {winner.get('_packs_needed')}")
        logger.info(f"   Total cost mult: {winner.get('_total_cost_mult')}")
        logger.info(f"   Pack explanation: {winner.get('_pack_explanation')}")
        logger.info(f"   Бренд: {winner.get('brand_id', 'NONE')}")
        logger.info(f"   Supplier ID: {supplier_id}")
        logger.info(f"   Pack penalty: {winner.get('_pack_score_penalty', 0)}")
        
        # ==================== IMPROVED MATCH_PERCENT CALCULATION ====================
        # Updated scoring logic with name similarity for more accurate percentages
        # Target: 95%+ for excellent matches, 90%+ for good matches
        
        # Use prelim_match_percent if stick_with_favorite was triggered
        if winner.get('_stick_with_favorite'):
            match_percent = 100  # Original favorite = 100% match
        else:
            # Calculate actual name similarity using fuzzy matching
            from rapidfuzz import fuzz
            
            winner_name = (winner.get('name_raw') or '').lower()
            ref_name_lower = reference_name.lower()
            
            # Name similarity (0-100)
            name_similarity = fuzz.token_set_ratio(ref_name_lower, winner_name)
            
            # Base scoring breakdown:
            # - Name similarity: 50% weight (0-50 points)
            # - Product core match: 25 points
            # - Guards passed: 15 points  
            # - Brand match: 10 points (if brand_critical)
            
            base_score = 0
            
            # Name similarity contribution (50% of score)
            base_score += (name_similarity / 100) * 50
            
            # Product core bonus (25 points for exact match)
            if winner.get('product_core_id') == ref_product_core:
                base_score += 25
            
            # Guards bonus (15 points for passing all guards)
            base_score += 15
            
            # Brand bonus (10 points if brand_critical and matched)
            if brand_critical and winner.get('brand_id') == brand_id:
                base_score += 10
            
            # Pack penalty
            pack_penalty = winner.get('_pack_score_penalty', 0)
            
            match_percent = max(0, min(100, int(base_score - pack_penalty)))
            
            logger.info(f"   📊 Match score breakdown: name_sim={name_similarity}%, core_match={winner.get('product_core_id') == ref_product_core}, brand_match={winner.get('brand_id') == brand_id if brand_critical else 'N/A'}")
            logger.info(f"   📊 Final match_percent: {match_percent}%")
        
        # P0.5: Calculate actual total_cost with min_order_qty
        min_order_qty = winner.get('min_order_qty', 1) or 1
        actual_qty = winner.get('_actual_qty', request.qty)  # P0.5: actual qty with min_order_qty
        price = winner.get('price', 0)
        
        # Use P0.5 total_cost if available, otherwise calculate
        if winner.get('_total_cost_p05'):
            actual_total_cost = winner.get('_total_cost_p05')
        else:
            actual_total_cost = actual_qty * price
        
        packs_needed = winner.get('_packs_needed', 1)
        
        # Log selection
        search_logger.set_selection(
            selected_item_id=winner.get('id'),
            supplier_id=supplier_id,
            price=price,
            match_percent=match_percent,
            total_cost=actual_total_cost
        )
        search_logger.set_outcome('ok')
        search_logger.log()
        
        # Build result object
        result = type('obj', (object,), {
            'status': 'ok',
            'supplier_id': winner.get('supplier_company_id'),
            'supplier_name': company_map.get(winner.get('supplier_company_id'), 'Unknown'),
            'supplier_item_id': winner.get('id'),
            'name_raw': winner.get('name_raw'),
            'price': winner.get('price'),
            'price_per_base_unit': winner.get('price_per_base_unit') or winner.get('price'),
            'total_cost': actual_total_cost,  # P0: Correct total_cost
            'need_packs': packs_needed or 1.0,
            'match_percent': match_percent,
            'min_order_qty': min_order_qty,  # P0.5: min_order_qty
            'actual_qty': actual_qty,  # P0.5: actual qty to order
            'explanation': {
                'request_id': request_id,
                'build_sha': BUILD_SHA,
                'guards_applied': True,
                'total_candidates': total_candidates,
                'after_super_class_filter': len(step1),
                'after_guards': len(step2_guards),
                'rejected_by_forbidden': rejected_forbidden,
                'rejected_by_missing_anchor': rejected_anchors,
                'after_brand_filter': len(step3_brand),
                'after_unit_filter': len(step4_unit_compatible),
                'confidence_raw': round(confidence, 2),
                'match_percent_final': match_percent,
                'selected_item_id': winner.get('id'),
                'packs_needed': packs_needed,
                'total_cost': actual_total_cost,
                'min_order_qty': min_order_qty,  # P0.5
                'actual_qty': actual_qty  # P0.5
            }
        })()
        
        # result already set above
        result_status = result.status
        
        # Structured log line (ONE LINE JSON for easy parsing)
        try:
            log_summary = {
                'request_id': request_id,
                'build_sha': BUILD_SHA,
                'db_name': os.environ.get('DB_NAME'),
                'collection': 'supplier_items',
                'reference_name': reference_name,
                'brand_critical': brand_critical,
                'super_class': ref_super_class,
                'confidence': round(confidence, 2),
                'guards_applied': True,
                'counts': {
                    'total': total_candidates,
                    'after_super_class': len(step1),
                    'after_guards': len(step2_guards),
                    'rejected_by_forbidden': rejected_forbidden,
                    'rejected_by_missing_anchor': rejected_anchors,
                    'after_brand': len(step3_brand),
                    'after_unit_filter': len(step4_unit_compatible),
                    'rejected_unit_mismatch': unit_mismatch_count
                },
                'outcome': result_status,
                'selected_id': winner.get('id'),
                'selected_name': winner.get('name_raw', '')[:50],
                'price': winner.get('price'),
                'packs_needed': packs_needed,
                'total_cost': actual_total_cost,
                'match_percent': match_percent,
                'pack_explanation': winner.get('_pack_explanation', '')
            }
            logger.info(f"SEARCH_SUMMARY: {json.dumps(log_summary, ensure_ascii=False)}")
        except Exception as log_err:
            logger.warning(f"Log summary failed: {log_err}")  # SAFE
        
        # Step 8: Return response
        if result_status == "ok":
            # Add to cart
            user_cart = await db.cart.find_one({"userId": current_user['id']}, {"_id": 0})
            
            if not user_cart:
                user_cart = {
                    "userId": current_user['id'],
                    "items": []
                }
            
            # Check if item already in cart
            existing_item = next((item for item in user_cart.get('items', []) 
                                if item['pricelistId'] == result.supplier_item_id), None)
            
            if existing_item:
                existing_item['quantity'] += request.qty
            else:
                user_cart.setdefault('items', []).append({
                    "pricelistId": result.supplier_item_id,
                    "productName": result.name_raw,
                    "quantity": request.qty,
                    "price": result.price,
                    "supplierId": result.supplier_id,
                    "supplierName": result.supplier_name
                })
            
            await db.cart.replace_one(
                {"userId": current_user['id']},
                user_cart,
                upsert=True
            )
            
            # Build SelectedOffer for response with P0 unit fields
            cand_pack = winner.get('_pack_info')
            pack_explanation = winner.get('_pack_explanation', '')
            
            # Determine unit string for display
            if ref_pack_info.unit_type == UnitType.WEIGHT:
                ref_unit = "g"
                cand_unit = "g"
                unit_norm = "kg"
            elif ref_pack_info.unit_type == UnitType.VOLUME:
                ref_unit = "ml"
                cand_unit = "ml"
                unit_norm = "l"
            elif ref_pack_info.unit_type == UnitType.PIECE:
                ref_unit = "шт"
                cand_unit = "шт"
                unit_norm = "pcs"
            else:
                ref_unit = "?"
                cand_unit = "?"
                unit_norm = "?"
            
            selected_offer = SelectedOffer(
                supplier_id=result.supplier_id,
                supplier_name=result.supplier_name,
                supplier_item_id=result.supplier_item_id,
                name_raw=result.name_raw,
                price=result.price,
                currency='RUB',
                unit_norm=unit_norm,
                pack_value=cand_pack.base_qty if cand_pack else None,
                pack_unit=cand_unit,
                price_per_base_unit=result.price_per_base_unit or result.price,
                total_cost=actual_total_cost,  # P0: Correct total_cost
                units_needed=float(packs_needed) if packs_needed else 1.0,
                score=match_percent,
                match_percent=match_percent,  # P0: UI compatibility alias
                # P0: New unit fields
                selected_pack_base_qty=cand_pack.base_qty if cand_pack else None,
                selected_pack_unit=cand_unit,
                required_base_qty=ref_pack_info.base_qty,
                required_unit=ref_unit,
                packs_needed=packs_needed,
                pack_explanation=pack_explanation,
                # P0.5: min_order_qty support
                min_order_qty=result.min_order_qty,
                actual_qty=result.actual_qty,
                # P0: Stick with favorite flag
                stick_with_favorite=winner.get('_stick_with_favorite', False)
            )
            
            return AddFromFavoriteResponse(
                status="ok",
                selected_offer=selected_offer,
                top_candidates=[
                    {
                        'name_raw': c.get('name_raw', '')[:50],
                        'price': c.get('price'),
                        'supplier': company_map.get(c.get('supplier_company_id'), 'Unknown'),
                        'packs_needed': c.get('_packs_needed'),
                        'pack_explanation': c.get('_pack_explanation', ''),
                        'min_order_qty': c.get('min_order_qty', 1)  # P0.5
                    }
                    for c in step4_unit_compatible[:5]
                ],
                # P0+P1 Diagnostic fields (UI visible)
                build_sha=BUILD_SHA,
                request_id=request_id,
                ref_product_core=ref_product_core,
                selected_product_core=winner.get('product_core_id'),
                ref_unit_type=ref_pack_info.unit_type.value,
                selected_unit_type=winner.get('_pack_info').unit_type.value if winner.get('_pack_info') else None,
                packs_needed=packs_needed,
                computed_total_cost=actual_total_cost,
                # P0.5: min_order_qty in top-level response
                min_order_qty=result.min_order_qty,
                actual_qty=result.actual_qty,
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'guards_applied': True,
                    'geo_as_brand': geo_as_brand,
                    'geo_filter_type': geo_filter_type,
                    'geo_filter_value': geo_filter_value,
                    'country_as_brand': country_as_brand,  # Legacy
                    'counts': {
                        'total': total_candidates,
                        'after_product_core': len(step1),
                        'after_guards': len(step2_guards),
                        'rejected_by_forbidden': rejected_forbidden,
                        'rejected_by_missing_anchor': rejected_anchors,
                        'after_brand': len(step3_brand),
                        'after_unit_filter': len(step4_unit_compatible),
                        'rejected_unit_mismatch': unit_mismatch_count,
                        'pack_calculated': pack_calculated_count
                    },
                    'selected_item_id': winner.get('id'),
                    'confidence_raw': round(confidence, 2),
                    'match_percent_final': match_percent,
                    'packs_needed': packs_needed,
                    'total_cost': actual_total_cost,
                    'pack_explanation': pack_explanation
                },
                message="Товар добавлен в корзину"
            )
        else:
            return AddFromFavoriteResponse(
                status=result_status,
                message="Товар не найден"
            )
    
    except Exception as e:
        import traceback
        logger.error(f"❌ ADD_FROM_FAVORITE error: {str(e)}")
        logger.error(traceback.format_exc())
        
        return AddFromFavoriteResponse(
            status="error",
            message=f"Error: {str(e)}"
        )


@api_router.post("/favorites/order")
async def order_from_favorites(data: dict, current_user: dict = Depends(get_current_user)):
    """Create orders from favorites with HYBRID MATCHER + MVP minimum order logic
    
    Per MVP requirements:
    - Uses Hybrid Matcher for CHEAPEST mode
    - Enforces supplier minimum orders
    - Applies +10% top-up if below minimum
    - Redistributes between suppliers if beneficial
    - Excludes suppliers if no benefit
    """
    from matching.hybrid_matcher import find_best_match_hybrid
    from order_optimizer import optimize_order_with_minimums
    
    # Get company ID
    company_id = current_user.get('companyId')
    if current_user['role'] == 'customer':
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Load ALL supplier_items for matching
    all_supplier_items = await db.supplier_items.find({"active": True}, {"_id": 0}).to_list(15000)
    
    # Load company names map
    all_companies = await db.companies.find({}, {"_id": 0, "id": 1, "companyName": 1, "name": 1}).to_list(100)
    supplier_names = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in all_companies}
    
    # Process items and find best supplier for each
    orders_by_supplier = {}
    baseline_total = 0  # For savings calculation
    
    for item in data['items']:
        quantity = float(item.get('quantity', 0))
        if quantity <= 0:
            continue
        
        # Get favorite
        favorite = await db.favorites.find_one({"id": item['favoriteId']}, {"_id": 0})
        if not favorite:
            continue
        
        # Get original product
        original_product = await db.products.find_one({"id": favorite['productId']}, {"_id": 0})
        original_pl = await db.pricelists.find_one({"productId": favorite['productId']}, {"_id": 0})
        
        if not original_product or not original_pl:
            continue
        
        original_price = original_pl['price']
        
        # Determine best supplier based on mode
        if favorite.get('mode') == 'cheapest':
            # Use HYBRID MATCHER (NEW!)
            winner = find_best_match_hybrid(
                query_product_name=original_product['name'],
                original_price=original_price,
                all_items=all_supplier_items
            )
            
            if winner:
                supplier_id = winner['supplier_company_id']
                unit_price = winner['price']
                product_name = winner['name_raw']
                article = winner.get('supplier_item_code', '')
            else:
                # No cheaper match - use original
                supplier_id = original_pl['supplierId']
                unit_price = original_price
                product_name = original_product['name']
                article = original_pl.get('supplierItemCode', '')
        else:
            # EXACT mode - use original supplier
            supplier_id = favorite.get('originalSupplierId') or original_pl['supplierId']
            unit_price = original_price
            product_name = original_product['name']
            article = original_pl.get('supplierItemCode', '')
        
        # Add to supplier's order
        if supplier_id not in orders_by_supplier:
            orders_by_supplier[supplier_id] = {"items": [], "total": 0}
        
        item_total = quantity * unit_price
        orders_by_supplier[supplier_id]["items"].append({
            "productName": product_name,
            "article": article,
            "quantity": quantity,
            "price": unit_price,
            "unit": favorite.get('unit', 'шт')
        })
        orders_by_supplier[supplier_id]["total"] += item_total
        
        # Calculate baseline for this item (for savings analytics)
        all_prices = await db.pricelists.find({"productId": favorite['productId']}, {"_id": 0, "price": 1}).to_list(100)
        if all_prices:
            from order_optimizer import calculate_baseline_price
            baseline_price = calculate_baseline_price([p['price'] for p in all_prices])
            baseline_total += baseline_price * quantity
    
    # OPTIMIZE: Apply minimum order logic with +10% top-up
    optimized_orders, opt_stats = optimize_order_with_minimums(
        orders_by_supplier,
        all_supplier_items,
        supplier_names
    )
    
    # Get delivery address
    delivery_address = None
    if data.get('deliveryAddressId'):
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company and company.get('deliveryAddresses'):
            for addr in company['deliveryAddresses']:
                # Addresses might not have ID, match by address string
                if isinstance(addr, dict):
                    if addr.get('address') == data['deliveryAddressId'] or str(addr) == data['deliveryAddressId']:
                        delivery_address = addr
                        break
    
    # Create orders (only for suppliers that passed minimum check)
    for supplier_id in optimized_orders:
        if await _restaurant_is_paused(supplier_id, company_id):
            raise HTTPException(
                status_code=403,
                detail="Поставщик поставил ваш ресторан на паузу. Отгрузка временно недоступна."
            )
    created_orders = []
    actual_total = 0
    
    for supplier_id, order_data in optimized_orders.items():
        order = {
            "id": str(uuid.uuid4()),
            "customerCompanyId": company_id,
            "supplierCompanyId": supplier_id,
            "orderDate": datetime.now(timezone.utc).isoformat(),
            "amount": order_data["total"],
            "status": "new",
            "orderDetails": order_data["items"],
            "deliveryAddress": delivery_address,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        
        await db.orders.insert_one(order)
        created_orders.append({
            "orderId": order["id"],
            "supplierId": supplier_id,
            "supplierName": supplier_names.get(supplier_id, 'Unknown'),
            "amount": order_data["total"]
        })
        actual_total += order_data["total"]
    
    # Calculate savings
    savings = baseline_total - actual_total if baseline_total > 0 else 0
    savings_pct = (savings / baseline_total * 100) if baseline_total > 0 else 0
    
    return {
        "message": f"Created {len(created_orders)} order(s)",
        "orders": created_orders,
        "totalAmount": actual_total,
        "baselineAmount": baseline_total,
        "savings": savings,
        "savingsPercent": round(savings_pct, 2),
        "optimizationStats": opt_stats
    }

# ==================== SUPPLIER RESTAURANT MANAGEMENT ====================

# Whitelist: fields of restaurant (customer) company visible to supplier (always, not link-dependent)
REQUISITES_WHITELIST = {
    "companyName", "inn", "ogrn", "legalAddress", "actualAddress",
    "phone", "email", "contactPersonName", "contactPersonPosition", "contactPersonPhone",
    "deliveryAddresses", "edoNumber", "guid"
}
REQUISITES_PREVIEW_FIELDS = ("companyName", "inn", "phone", "email")


async def _restaurant_is_paused(supplier_id: str, restaurant_id: str) -> bool:
    """Check if supplier has paused this restaurant."""
    s = await db.supplier_restaurant_settings.find_one(
        {"supplierId": supplier_id, "restaurantId": restaurant_id},
        {"_id": 0, "is_paused": 1}
    )
    return bool(s and s.get("is_paused"))


def _build_requisites(company: dict) -> dict:
    """Build requisites dict from company, whitelist only. No private/internal fields."""
    out = {}
    for k in REQUISITES_WHITELIST:
        if k in company and company[k] is not None:
            out[k] = company[k]
    return out


def _build_requisites_preview(company: dict) -> dict:
    """Build 4-field preview: companyName, inn, phone, email."""
    out = {}
    for k in REQUISITES_PREVIEW_FIELDS:
        if k in company and company[k] is not None:
            out[k] = company[k]
    return out


@api_router.get("/supplier/restaurant-documents")
async def get_supplier_restaurant_documents(current_user: dict = Depends(get_current_user)):
    """List restaurants (customers) with their contract status for Documents page.
    restaurantRequisitesPreview: 4 fields (companyName, inn, phone, email) — always.
    restaurantRequisitesFull: whitelist including edoNumber, guid — always. Not link-dependent."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get('companyId')
    if not company_id:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        return []
    proj = {"_id": 0, "id": 1, "companyName": 1, "inn": 1}
    for k in REQUISITES_WHITELIST:
        proj[k] = 1
    customers = await db.companies.find({"type": "customer"}, proj).to_list(500)
    links = await db.supplier_restaurant_settings.find(
        {"supplierId": company_id},
        {"_id": 0, "restaurantId": 1, "contract_accepted": 1}
    ).to_list(500)
    link_map = {l['restaurantId']: l for l in links}
    docs = await db.documents.find({"companyId": {"$in": [c['id'] for c in customers]}}, {"_id": 0}).to_list(2000)
    docs_by_company = {}
    for d in docs:
        cid = d.get('companyId')
        if cid not in docs_by_company:
            docs_by_company[cid] = {}
        # Dedupe by type: keep newest per (companyId, type)
        doc_type = d.get('type', 'Документ')
        entry = {"id": d.get('id'), "type": doc_type, "uploadedAt": d.get('createdAt', ''), "status": d.get('status', 'uploaded')}
        existing = docs_by_company[cid].get(doc_type)
        if not existing or (d.get('createdAt', '') or '') > (existing.get('uploadedAt', '') or ''):
            docs_by_company[cid][doc_type] = entry
    for cid in docs_by_company:
        docs_by_company[cid] = list(docs_by_company[cid].values())
    result = []
    for c in customers:
        link = link_map.get(c['id'])
        contract_status = "accepted" if (link and link.get("contract_accepted")) else "pending"
        preview = _build_requisites_preview(c)
        # Full requisites only for accepted (contract_accepted) restaurants
        full = _build_requisites(c) if (link and link.get("contract_accepted")) else None
        item = {
            "restaurantId": c['id'],
            "restaurantName": c.get('companyName', c.get('name', 'N/A')),
            "inn": c.get('inn', ''),
            "documents": docs_by_company.get(c['id'], []),
            "contractStatus": contract_status,
            "restaurantRequisitesPreview": preview if preview else None,
            "restaurantRequisitesFull": full if full else None
        }
        result.append(item)
    return result


@api_router.post("/supplier/accept-contract")
async def accept_contract(data: dict, current_user: dict = Depends(get_current_user)):
    """Accept contract with restaurant: creates link with contract_accepted=true, is_paused=false."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    restaurant_id = data.get('restaurantId')
    if not restaurant_id:
        raise HTTPException(status_code=400, detail="restaurantId required")
    company_id = current_user.get('companyId')
    if not company_id:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    restaurant = await db.companies.find_one({"id": restaurant_id, "type": "customer"}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.supplier_restaurant_settings.update_one(
        {"supplierId": company_id, "restaurantId": restaurant_id},
        {"$set": {
            "contract_accepted": True,
            "is_paused": False,
            "ordersEnabled": True,
            "updatedAt": now
        }},
        upsert=True
    )
    return {"contractStatus": "accepted", "restaurantId": restaurant_id}


@api_router.get("/supplier/restaurants")
@api_router.get("/suppliers/me/restaurants")
async def get_supplier_restaurants(current_user: dict = Depends(get_current_user)):
    """Get restaurants with contract_accepted=true (source of truth: supplier_restaurant_settings)."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get('companyId')
    if not company_id:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        return []
    links = await db.supplier_restaurant_settings.find(
        {"supplierId": company_id, "contract_accepted": True},
        {"_id": 0}
    ).to_list(500)
    orders = await db.orders.find({"supplierCompanyId": company_id}, {"_id": 0, "customerCompanyId": 1}).to_list(1000)
    order_counts = {}
    for o in orders:
        cid = o.get('customerCompanyId')
        order_counts[cid] = order_counts.get(cid, 0) + 1
    restaurants = []
    for link in links:
        rest_id = link.get('restaurantId')
        restaurant = await db.companies.find_one({"id": rest_id}, {"_id": 0})
        if restaurant:
            restaurants.append({
                "id": restaurant['id'],
                "name": restaurant.get('companyName', restaurant.get('name', 'N/A')),
                "inn": restaurant.get('inn', ''),
                "contract_status": "accepted",
                "is_paused": bool(link.get('is_paused')),
                "orderCount": order_counts.get(rest_id, 0),
                "ordersEnabled": link.get('ordersEnabled', True),
                "unavailabilityReason": link.get('unavailabilityReason')
            })
    return restaurants

@api_router.patch("/suppliers/me/restaurants/{restaurant_id}")
async def patch_restaurant_pause(
    restaurant_id: str,
    data: RestaurantPauseBody,
    current_user: dict = Depends(get_current_user)
):
    """Toggle is_paused for a restaurant (supplier↔restaurant link must exist)."""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    company_id = current_user.get('companyId')
    if not company_id:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0, "id": 1})
        company_id = company['id'] if company else None
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    result = await db.supplier_restaurant_settings.update_one(
        {"supplierId": company_id, "restaurantId": restaurant_id, "contract_accepted": True},
        {"$set": {"is_paused": data.is_paused, "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant not found or contract not accepted")
    return {"is_paused": data.is_paused}


@api_router.put("/supplier/restaurants/{restaurant_id}/availability")
async def update_restaurant_availability(
    restaurant_id: str,
    data: UpdateRestaurantAvailability,
    current_user: dict = Depends(get_current_user)
):
    """Update order availability for a specific restaurant"""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company_id = current_user.get('companyId')
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Upsert settings (preserve contract_accepted if exists)
    update = {
        "ordersEnabled": data.ordersEnabled,
        "unavailabilityReason": data.unavailabilityReason,
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    existing = await db.supplier_restaurant_settings.find_one(
        {"supplierId": company_id, "restaurantId": restaurant_id}, {"_id": 0}
    )
    if not existing:
        update["supplierId"] = company_id
        update["restaurantId"] = restaurant_id
        update["contract_accepted"] = True
        update["is_paused"] = False
        await db.supplier_restaurant_settings.insert_one(update)
    else:
        await db.supplier_restaurant_settings.update_one(
            {"supplierId": company_id, "restaurantId": restaurant_id},
            {"$set": update}
        )
    
    return {
        "message": "Restaurant availability updated",
        "ordersEnabled": data.ordersEnabled
    }

# ==================== FAVORITES V2 MIGRATION ====================

@api_router.post("/admin/favorites/migrate-v2")
async def migrate_favorites_to_v2(current_user: dict = Depends(get_current_user)):
    """Migrate all favorites to v2 schema
    
    V2 schema adds:
    - source_item_id (from productId -> pricelist lookup)
    - brand_id (from product.brand_id)
    - unit_norm
    - pack (extracted from name)
    - tokens (normalized name words)
    - brand_critical (from brandMode)
    - schema_version = 2
    - broken (true if migration failed)
    
    Does NOT delete old data, only enriches.
    """
    import logging
    from pipeline.normalizer import normalize_name
    from pipeline.enricher import extract_weights
    from brand_master import get_brand_master
    
    logger = logging.getLogger(__name__)
    
    bm = get_brand_master()
    
    # Get all favorites
    favorites = await db.favorites.find({}, {"_id": 0}).to_list(10000)
    logger.info(f"📋 Migrating {len(favorites)} favorites to v2 schema")
    
    stats = {
        "total": len(favorites),
        "migrated": 0,
        "already_v2": 0,
        "broken": 0,
        "errors": 0
    }
    
    for fav in favorites:
        try:
            # Skip if already v2
            if fav.get('schema_version') == 2:
                stats["already_v2"] += 1
                continue
            
            # Try to enrich
            update_data = {"schema_version": 2}
            broken = False
            
            # Get product
            product = None
            if fav.get('productId'):
                product = await db.products.find_one({"id": fav['productId']}, {"_id": 0})
            
            if product:
                # Get source_item_id from pricelist
                pricelist = await db.pricelists.find_one({"productId": product['id']}, {"_id": 0})
                if pricelist:
                    update_data["source_item_id"] = pricelist['id']
                
                # Get brand_id from product
                update_data["brand_id"] = product.get('brand_id')
                
                # Get unit_norm
                update_data["unit_norm"] = product.get('unit', 'kg')
                
                # Extract pack from name
                weight_data = extract_weights(product.get('name', ''))
                update_data["pack"] = weight_data.get('net_weight_kg')
                
                # Generate tokens
                name_norm = normalize_name(product.get('name', ''))
                update_data["tokens"] = name_norm.split()[:10]  # Max 10 tokens
                
            else:
                # Product not found - try to extract from productName
                if fav.get('productName'):
                    # Detect brand from name
                    if bm:
                        brand_id, _ = bm.detect_brand(fav['productName'])
                        update_data["brand_id"] = brand_id
                    
                    # Extract weight
                    weight_data = extract_weights(fav['productName'])
                    update_data["pack"] = weight_data.get('net_weight_kg')
                    
                    # Generate tokens
                    name_norm = normalize_name(fav['productName'])
                    update_data["tokens"] = name_norm.split()[:10]
                    
                    update_data["unit_norm"] = fav.get('unit', 'kg')
                else:
                    broken = True
            
            # Set brand_critical from brandMode
            update_data["brand_critical"] = fav.get('brandMode') == 'STRICT'
            
            # Mark as broken if no essential data
            if broken or not update_data.get("tokens"):
                update_data["broken"] = True
                stats["broken"] += 1
            else:
                update_data["broken"] = False
                stats["migrated"] += 1
            
            # Update favorite
            await db.favorites.update_one(
                {"id": fav['id']},
                {"$set": update_data}
            )
            
        except Exception as e:
            logger.error(f"Error migrating favorite {fav.get('id')}: {e}")
            stats["errors"] += 1
            # Mark as broken
            await db.favorites.update_one(
                {"id": fav['id']},
                {"$set": {"schema_version": 2, "broken": True}}
            )
    
    logger.info(f"✅ Migration complete: {stats['migrated']} migrated, {stats['broken']} broken")
    
    return {
        "success": True,
        "message": f"Migrated {stats['migrated']} favorites to v2",
        "stats": stats
    }


@api_router.get("/favorites/{favorite_id}/enriched")
async def get_enriched_favorite(favorite_id: str, current_user: dict = Depends(get_current_user)):
    """Get favorite with enriched data for debugging
    
    Returns all fields including v2 fields and original product/pricelist data.
    """
    favorite = await db.favorites.find_one(
        {"id": favorite_id, "userId": current_user['id']}, 
        {"_id": 0}
    )
    
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    # Enrich with product data
    product = None
    pricelist = None
    
    if favorite.get('productId'):
        product = await db.products.find_one({"id": favorite['productId']}, {"_id": 0})
        pricelist = await db.pricelists.find_one({"productId": favorite['productId']}, {"_id": 0})
    
    return {
        "favorite": favorite,
        "product": product,
        "pricelist": pricelist,
        "v2_fields": {
            "schema_version": favorite.get('schema_version'),
            "source_item_id": favorite.get('source_item_id'),
            "brand_id": favorite.get('brand_id') or favorite.get('brandId'),
            "brand_critical": favorite.get('brand_critical') or (favorite.get('brandMode') == 'STRICT'),
            "unit_norm": favorite.get('unit_norm') or favorite.get('unit'),
            "pack": favorite.get('pack'),
            "tokens": favorite.get('tokens'),
            "broken": favorite.get('broken', False)
        }
    }


# ==================== SEARCH QUALITY REPORTS ====================

@api_router.get("/admin/search/quality-report")
async def get_search_quality_report(current_user: dict = Depends(get_current_user)):
    """Generate search quality report
    
    Returns:
    - Brand coverage by supplier
    - Overall brand statistics
    - Sample products without brand
    """
    from search_engine import generate_brand_quality_report
    
    # Load data
    all_products = await db.products.find({}, {"_id": 0}).to_list(20000)
    all_pricelists = await db.pricelists.find({}, {"_id": 0}).to_list(30000)
    
    # Get supplier names
    companies = await db.companies.find({}, {"_id": 0, "id": 1, "companyName": 1, "name": 1}).to_list(100)
    company_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in companies}
    
    # Generate report
    report = generate_brand_quality_report(all_products, all_pricelists)
    
    # Add supplier names to by_supplier stats
    by_supplier_with_names = {}
    for supplier_id, stats in report['by_supplier'].items():
        by_supplier_with_names[supplier_id] = {
            **stats,
            'supplier_name': company_map.get(supplier_id, 'Unknown')
        }
    
    report['by_supplier'] = by_supplier_with_names
    
    return report


@api_router.get("/admin/brands/families")
async def get_brand_families(current_user: dict = Depends(get_current_user)):
    """Get brand family information
    
    Returns:
    - List of brand families and their members
    - Statistics about family coverage
    """
    from brand_master import get_brand_master
    
    bm = get_brand_master()
    
    families = []
    for family_id, members in bm.family_to_members.items():
        family_info = bm.get_brand_info(family_id)
        families.append({
            'family_id': family_id,
            'family_name': family_info.get('brand_ru') if family_info else family_id,
            'members': members,
            'member_count': len(members)
        })
    
    # Sort by member count
    families.sort(key=lambda x: -x['member_count'])
    
    stats = bm.get_stats()
    
    return {
        'families': families,
        'stats': {
            'total_families': len(families),
            'brands_with_family': stats.get('brands_with_family', 0),
            'total_brands': stats.get('total_brands', 0)
        }
    }


# ==================== ADMIN BRAND MANAGEMENT ====================

@api_router.post("/test/create-fixtures")
async def create_test_fixtures(current_user: dict = Depends(get_current_user)):
    """Create test fixtures for matching + pack range tests
    
    MVP Tests:
    - ТЕСТ 1: brand_critical=false - выбирает любой бренд, дешевле
    - ТЕСТ 2: brand_critical=true - только указанный бренд
    - ТЕСТ 3: Pack range - 0.5x-2x допустимо
    - ТЕСТ 4: Экономика - выбор по total_cost
    - ТЕСТ 5: Старое избранное - не падает
    - ТЕСТ 6: Негатив - not_found без ошибки
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Get first supplier
    supplier = await db.companies.find_one({"type": "supplier"}, {"_id": 0})
    if not supplier:
        return {"error": "No supplier found in database"}
    
    supplier_id = supplier['id']
    
    # Create test products for Кетчуп tests
    test_products = [
        # ТЕСТ 1-2: Кетчуп с разными брендами и фасовками
        {
            "id": "TEST_KETCHUP_HEINZ_800",
            "name": "Кетчуп томатный Heinz 800г",
            "unit": "kg",
            "brand_id": "heinz",
            "brand_strict": False
        },
        {
            "id": "TEST_KETCHUP_HEINZ_1KG",
            "name": "Кетчуп томатный Heinz 1кг",
            "unit": "kg",
            "brand_id": "heinz",
            "brand_strict": False
        },
        {
            "id": "TEST_KETCHUP_OTHER_500",
            "name": "Кетчуп томатный Calve 500г",
            "unit": "kg",
            "brand_id": "calve",
            "brand_strict": False
        },
        {
            "id": "TEST_KETCHUP_OTHER_1KG",
            "name": "Кетчуп томатный MR.RICCO 1кг",
            "unit": "kg",
            "brand_id": "mr_ricco",
            "brand_strict": False
        },
        # ТЕСТ 3: Pack range tests - 340g (too small), 5kg (too large)
        {
            "id": "TEST_KETCHUP_SMALL",
            "name": "Кетчуп томатный Heinz 340г",
            "unit": "kg",
            "brand_id": "heinz",
            "brand_strict": False
        },
        {
            "id": "TEST_KETCHUP_LARGE",
            "name": "Кетчуп томатный Heinz 5кг",
            "unit": "kg",
            "brand_id": "heinz",
            "brand_strict": False
        },
        # ТЕСТ 4: Экономика - сравнение по total_cost
        {
            "id": "TEST_ECON_A",
            "name": "Соус острый 800г бренд_А",
            "unit": "kg",
            "brand_id": "test_econ_a",
            "brand_strict": False
        },
        {
            "id": "TEST_ECON_B",
            "name": "Соус острый 1кг бренд_Б",
            "unit": "kg",
            "brand_id": "test_econ_b",
            "brand_strict": False
        },
        # Guard test - Соус ≠ Кетчуп
        {
            "id": "TEST_SAUCE_NOT_KETCHUP",
            "name": "Соус соевый 500мл",
            "unit": "l",
            "brand_id": "test_soy",
            "brand_strict": False
        }
    ]
    
    # Create test pricelists with prices
    test_pricelists = [
        # Кетчуп Heinz 800г - эталон
        {
            "id": "SI_KETCHUP_HEINZ_800",
            "productId": "TEST_KETCHUP_HEINZ_800",
            "supplierId": supplier_id,
            "price": 250.00,  # 312.5₽/кг
            "supplierItemCode": "HEINZ-800"
        },
        # Кетчуп Heinz 1кг - дешевле за кг
        {
            "id": "SI_KETCHUP_HEINZ_1KG",
            "productId": "TEST_KETCHUP_HEINZ_1KG",
            "supplierId": supplier_id,
            "price": 280.00,  # 280₽/кг - ДЕШЕВЛЕ!
            "supplierItemCode": "HEINZ-1KG"
        },
        # Кетчуп Calve 500г - дешевле Heinz
        {
            "id": "SI_KETCHUP_OTHER_500",
            "productId": "TEST_KETCHUP_OTHER_500",
            "supplierId": supplier_id,
            "price": 120.00,  # 240₽/кг - САМЫЙ ДЕШЁВЫЙ!
            "supplierItemCode": "CALVE-500"
        },
        # Кетчуп MR.RICCO 1кг
        {
            "id": "SI_KETCHUP_OTHER_1KG",
            "productId": "TEST_KETCHUP_OTHER_1KG",
            "supplierId": supplier_id,
            "price": 260.00,  # 260₽/кг
            "supplierItemCode": "RICCO-1KG"
        },
        # Pack tests - слишком маленький (340г < 400г = 0.5*800г)
        {
            "id": "SI_KETCHUP_SMALL",
            "productId": "TEST_KETCHUP_SMALL",
            "supplierId": supplier_id,
            "price": 80.00,  # Очень дешёвый, но вне диапазона
            "supplierItemCode": "HEINZ-340"
        },
        # Pack tests - слишком большой (5кг > 1.6кг = 2*800г)
        {
            "id": "SI_KETCHUP_LARGE",
            "productId": "TEST_KETCHUP_LARGE",
            "supplierId": supplier_id,
            "price": 1000.00,  # Дёшево за кг, но вне диапазона
            "supplierItemCode": "HEINZ-5KG"
        },
        # Экономика тест A: 800г × 200₽ = 250₽/кг
        {
            "id": "SI_ECON_A",
            "productId": "TEST_ECON_A",
            "supplierId": supplier_id,
            "price": 200.00,
            "supplierItemCode": "ECON-A"
        },
        # Экономика тест B: 1кг × 230₽ = 230₽/кг (ДЕШЕВЛЕ ЗА КГ!)
        {
            "id": "SI_ECON_B",
            "productId": "TEST_ECON_B",
            "supplierId": supplier_id,
            "price": 230.00,
            "supplierItemCode": "ECON-B"
        },
        # Guard test
        {
            "id": "SI_SAUCE_NOT_KETCHUP",
            "productId": "TEST_SAUCE_NOT_KETCHUP",
            "supplierId": supplier_id,
            "price": 100.00,
            "supplierItemCode": "SOY-500"
        }
    ]
    
    # Create test favorites
    test_favorites = [
        # ТЕСТ 1: brand_critical=false - должен выбрать Calve (самый дешёвый)
        {
            "id": "FAV_KETCHUP_ANY",
            "userId": current_user['id'],
            "companyId": current_user.get('companyId'),
            "productId": "TEST_KETCHUP_HEINZ_800",
            "productName": "Кетчуп томатный Heinz 800г",
            "productCode": "HEINZ-800",
            "unit": "kg",
            "isBranded": True,
            "brandMode": "ANY",  # brand_critical = FALSE
            "brandId": "heinz",
            "brand": "Heinz",
            "schema_version": 2,
            "pack": 0.8,
            "broken": False,
            "displayOrder": 0
        },
        # ТЕСТ 2: brand_critical=true - должен выбрать только Heinz
        {
            "id": "FAV_KETCHUP_HEINZ",
            "userId": current_user['id'],
            "companyId": current_user.get('companyId'),
            "productId": "TEST_KETCHUP_HEINZ_800",
            "productName": "Кетчуп томатный Heinz 800г",
            "productCode": "HEINZ-800",
            "unit": "kg",
            "isBranded": True,
            "brandMode": "STRICT",  # brand_critical = TRUE
            "brandId": "heinz",
            "brand": "Heinz",
            "schema_version": 2,
            "pack": 0.8,
            "broken": False,
            "displayOrder": 1
        },
        # ТЕСТ 4: Экономика - должен выбрать B (дешевле за объём)
        {
            "id": "FAV_ECON_TEST",
            "userId": current_user['id'],
            "companyId": current_user.get('companyId'),
            "productId": "TEST_ECON_A",
            "productName": "Соус острый 800г бренд_А",
            "productCode": "ECON-A",
            "unit": "kg",
            "isBranded": True,
            "brandMode": "ANY",
            "brandId": "test_econ_a",
            "brand": "бренд_А",
            "schema_version": 2,
            "pack": 0.8,
            "broken": False,
            "displayOrder": 2
        },
        # ТЕСТ 5: Старое избранное без v2 полей
        {
            "id": "FAV_OLD_FORMAT",
            "userId": current_user['id'],
            "companyId": current_user.get('companyId'),
            "productId": None,  # No product link
            "productName": "Кетчуп томатный 800г",
            "productCode": "",
            "unit": "kg",
            "isBranded": False,
            "brandMode": "ANY",
            # NO v2 fields
            "displayOrder": 3
        }
    ]
    
    # Insert/update products
    for prod in test_products:
        await db.products.update_one(
            {"id": prod["id"]},
            {"$set": prod},
            upsert=True
        )
    
    # Insert/update pricelists
    for pl in test_pricelists:
        await db.pricelists.update_one(
            {"id": pl["id"]},
            {"$set": pl},
            upsert=True
        )
    
    # Insert/update favorites
    for fav in test_favorites:
        await db.favorites.update_one(
            {"id": fav["id"]},
            {"$set": fav},
            upsert=True
        )
    
    logger.info("✅ Test fixtures created")
    
    return {
        "success": True,
        "message": "Test fixtures created for MVP matching tests",
        "data": {
            "products": len(test_products),
            "pricelists": len(test_pricelists),
            "favorites": len(test_favorites)
        },
        "expected_behavior": {
            "FAV_KETCHUP_ANY": "brand_critical=false → SI_KETCHUP_OTHER_500 (Calve, 240₽/кг) - cheapest",
            "FAV_KETCHUP_HEINZ": "brand_critical=true → SI_KETCHUP_HEINZ_1KG (280₽/кг) - cheapest Heinz",
            "FAV_ECON_TEST": "Экономика → SI_ECON_B (230₽/кг) - cheaper per unit",
            "FAV_OLD_FORMAT": "Old format → should not crash, may return not_found",
            "PACK_RANGE": "340г and 5кг should be REJECTED (outside 0.5x-2x range of 800г)"
        }
    }


@api_router.delete("/test/cleanup-fixtures")
async def cleanup_test_fixtures(current_user: dict = Depends(get_current_user)):
    """Remove test fixtures"""
    # Remove test products
    await db.products.delete_many({"id": {"$regex": "^TEST_PROD_"}})
    # Remove test pricelists
    await db.pricelists.delete_many({"id": {"$regex": "^SI_TEST_"}})
    # Remove test favorites
    await db.favorites.delete_many({"id": {"$regex": "^FAV_TEST_"}})
    
    return {"success": True, "message": "Test fixtures removed"}

@api_router.post("/admin/brands/backfill")
async def backfill_brands_endpoint(current_user: dict = Depends(get_current_user)):
    """Backfill brand_id for all products using the new brand dictionary
    
    Part B of the brand overhaul:
    - Uses BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx
    - Updates brand_id and brand_strict in products collection
    - Does NOT reload pricelists
    
    Returns statistics about the backfill.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Force reload brand master to use new file
    from brand_master import BrandMaster
    bm = BrandMaster.reload()
    
    stats = bm.get_stats()
    logger.info(f"📋 Brand dictionary: {stats['total_brands']} brands, {stats['total_aliases']} aliases")
    
    # Get all products
    products = await db.products.find({}, {"_id": 0}).to_list(20000)
    logger.info(f"📦 Found {len(products)} products to process")
    
    # Statistics
    result_stats = {
        'total_products': len(products),
        'branded': 0,
        'strict': 0,
        'no_brand': 0,
        'updated': 0,
        'errors': 0,
        'brand_counts': {}
    }
    
    # Process each product
    for i, product in enumerate(products):
        product_id = product.get('id')
        product_name = product.get('name', '')
        
        # Detect brand using new master
        brand_id, brand_strict = bm.detect_brand(product_name)
        
        if brand_id:
            result_stats['branded'] += 1
            if brand_strict:
                result_stats['strict'] += 1
            # Track brand counts
            result_stats['brand_counts'][brand_id] = result_stats['brand_counts'].get(brand_id, 0) + 1
        else:
            result_stats['no_brand'] += 1
        
        # Update if changed
        old_brand = product.get('brand_id')
        if brand_id != old_brand or product.get('brand_strict') != brand_strict:
            try:
                await db.products.update_one(
                    {"id": product_id},
                    {"$set": {
                        "brand_id": brand_id,
                        "brand_strict": brand_strict
                    }}
                )
                result_stats['updated'] += 1
            except Exception as e:
                result_stats['errors'] += 1
                logger.error(f"Error updating {product_id}: {e}")
    
    # Get top 20 brands by count
    top_brands = sorted(
        result_stats['brand_counts'].items(),
        key=lambda x: -x[1]
    )[:20]
    
    logger.info(f"✅ Backfill complete: {result_stats['updated']} updated, {result_stats['branded']} branded")
    
    return {
        "success": True,
        "message": f"Backfill complete. Updated {result_stats['updated']} products.",
        "stats": {
            "total_products": result_stats['total_products'],
            "branded": result_stats['branded'],
            "strict_branded": result_stats['strict'],
            "no_brand": result_stats['no_brand'],
            "updated": result_stats['updated'],
            "errors": result_stats['errors'],
            "brand_dictionary": stats
        },
        "top_brands": [{"brand_id": b[0], "count": b[1]} for b in top_brands]
    }


@api_router.get("/admin/brands/stats")
async def get_brand_stats(current_user: dict = Depends(get_current_user)):
    """Get statistics about brand dictionary and product brands"""
    from brand_master import get_brand_master
    
    bm = get_brand_master()
    dict_stats = bm.get_stats()
    
    # Get product brand stats from DB
    pipeline = [
        {"$group": {
            "_id": "$brand_id",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": 30}
    ]
    brand_agg = await db.products.aggregate(pipeline).to_list(30)
    
    # Count branded vs non-branded
    branded_count = await db.products.count_documents({"brand_id": {"$ne": None}})
    total_count = await db.products.count_documents({})
    
    return {
        "dictionary": dict_stats,
        "products": {
            "total": total_count,
            "branded": branded_count,
            "unbranded": total_count - branded_count,
            "branded_percent": round(100 * branded_count / max(total_count, 1), 1)
        },
        "top_brands_in_products": [
            {"brand_id": b["_id"] or "NO_BRAND", "count": b["count"]}
            for b in brand_agg
        ]
    }


# ==================== ADVANCED PRODUCT SEARCH ====================

@api_router.post("/search/similar")
async def search_similar_products_endpoint(data: dict):
    """Advanced product search with 7 formulas and ±10% pack tolerance"""
    from advanced_product_matcher import search_similar_products, extract_features
    
    query_text = data.get('query_text', '')
    strict_pack = data.get('strict_pack')
    strict_brand = data.get('strict_brand', False)
    brand = data.get('brand')
    top_n = data.get('top_n', 20)
    
    if not query_text:
        raise HTTPException(status_code=400, detail="query_text is required")
    
    # Get all products with features
    all_products_data = []
    
    # Check if features collection exists and has data
    features_count = await db.supplier_item_features.count_documents({})
    
    if features_count == 0:
        # Features not yet extracted, use live extraction
        pricelists = await db.pricelists.find({"availability": {"$ne": False}}, {"_id": 0}).to_list(10000)
        
        for pl in pricelists:
            product = await db.products.find_one({"id": pl['productId']}, {"_id": 0})
            if product:
                features = extract_features(product['name'], product['unit'], pl['price'])
                features['supplier_item_id'] = pl['id']
                features['supplier_id'] = pl['supplierId']
                features['active'] = True
                all_products_data.append(features)
    else:
        # Use pre-computed features
        features_list = await db.supplier_item_features.find({}, {"_id": 0}).to_list(10000)
        all_products_data = features_list
    
    # Search
    results = search_similar_products(
        query_text=query_text,
        all_products=all_products_data,
        strict_pack=strict_pack,
        strict_brand=strict_brand,
        brand=brand,
        top_n=top_n
    )
    
    return {
        "query": query_text,
        "formula_used": results[0]['formula_id'] if results else '0',
        "total_candidates": len(all_products_data),
        "matches_found": len(results),
        "results": results
    }

# ============================================================
# VALIDATION ENDPOINTS (must be BEFORE app.include_router!)
# ============================================================

# Store validation report globally
_validation_report = None

@api_router.get("/debug/validation")
async def get_validation_report():
    """Get the latest rules validation report"""
    global _validation_report
    if _validation_report is None:
        # Run validation if not done yet
        _validation_report = validate_all_rules(strict=False)
    
    return {
        "timestamp": _validation_report.timestamp,
        "summary": _validation_report.summary,
        "has_critical_errors": _validation_report.has_critical_errors,
        "stats": _validation_report.stats,
        "critical_errors_count": len(_validation_report.critical_errors),
        "warnings_count": len(_validation_report.warnings),
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "message": i.message,
                "details": i.details
            }
            for i in _validation_report.issues
        ]
    }

@api_router.post("/debug/validate-rules")
async def run_validation():
    """Manually trigger rules validation"""
    global _validation_report
    _validation_report = validate_all_rules(strict=False)
    return {
        "status": "completed",
        "summary": _validation_report.summary,
        "has_critical_errors": _validation_report.has_critical_errors,
        "stats": _validation_report.stats
    }

# BestPrice v12 Router - include BEFORE app.include_router
try:
    from bestprice_v12.routes import router as v12_router
    api_router.include_router(v12_router)
    logging.info("✅ BestPrice v12 router loaded")
except ImportError as e:
    logging.warning(f"⚠️ BestPrice v12 router not available: {e}")

# Deterministic 422 for validation errors: never return raw Pydantic arrays to UI
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    path = getattr(request, "url", None) and getattr(request.url, "path", "") or ""
    endpoint = path or "/api/price-lists/import"
    if "/price-lists/import" in path:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "error_code": "validation_error",
                    "message": "Неверные параметры запроса. Убедитесь, что выбран файл (xlsx или csv) и нажмите «Загрузить».",
                    "endpoint": endpoint,
                    "hint": "Отправьте multipart/form-data: file (обязательно), replace (опционально). column_mapping не обязателен.",
                    "columns": [],
                }
            },
        )
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "error_code": "validation_error",
                "message": "Ошибка валидации запроса. Проверьте передаваемые данные.",
                "endpoint": endpoint,
                "hint": "Проверьте формат и обязательные поля.",
            }
        },
    )


# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_validation():
    """Run rules validation at server startup"""
    global _validation_report
    logger.info("🔍 Running rules validation at startup...")
    if SKIP_RULES_VALIDATION:
        logger.warning("BESTPRICE_SKIP_RULES_VALIDATION enabled – critical validation issues will be downgraded.")
    try:
        _validation_report = validate_all_rules(strict=not SKIP_RULES_VALIDATION)
        logger.info(f"✅ Validation complete: {_validation_report.summary}")
        if _validation_report.has_critical_errors:
            logger.error("⚠️ Critical validation errors detected! Check /api/debug/validation for details.")
        elif SKIP_RULES_VALIDATION:
            logger.warning("Validation completed with downgraded issues (dev mode).")
    except Exception as e:
        logger.error(f"❌ Validation failed with error: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
