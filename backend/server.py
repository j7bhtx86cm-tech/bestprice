from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
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
    PackInfo
)

# Build info for debugging
BUILD_SHA = os.popen("cd /app && git rev-parse --short HEAD 2>/dev/null").read().strip() or "unknown"
BUILD_TIME = datetime.now(timezone.utc).isoformat()

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

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

# Supplier-Restaurant Settings
class SupplierRestaurantSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    supplierId: str
    restaurantId: str
    ordersEnabled: bool = True
    unavailabilityReason: Optional[str] = None
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UpdateRestaurantAvailability(BaseModel):
    ordersEnabled: bool
    unavailabilityReason: Optional[str] = None

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
    phone: str
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
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SupplierSettingsUpdate(BaseModel):
    minOrderAmount: Optional[float] = None
    deliveryDays: Optional[List[str]] = None
    deliveryTime: Optional[str] = None
    orderReceiveDeadline: Optional[str] = None
    logisticsType: Optional[LogisticsType] = None

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
    article: str
    price: float
    unit: str
    minQuantity: Optional[int] = 1
    availability: bool = True
    active: bool = True

class PriceListUpdate(BaseModel):
    price: Optional[float] = None
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
    article: str
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

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
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

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    if current_user['role'] in ['responsible', 'chef', 'supplier']:
        # These roles have companyId directly in user document
        company_id = current_user.get('companyId')
    else:
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    return {
        "id": current_user['id'],
        "email": current_user['email'],
        "role": current_user['role'],
        "companyId": company_id
    }

@api_router.get("/auth/inn/{inn}")
async def lookup_inn(inn: str):
    if inn in MOCK_INN_DATA:
        return MOCK_INN_DATA[inn]
    return {"companyName": "", "legalAddress": "", "ogrn": ""}

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
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data['updatedAt'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.supplier_settings.update_one(
        {"supplierCompanyId": company['id']},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Settings not found")
    
    settings = await db.supplier_settings.find_one({"supplierCompanyId": company['id']}, {"_id": 0})
    return settings

# ==================== PRICE LIST ROUTES ====================

@api_router.get("/price-lists/my")
async def get_my_price_lists(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get company ID from user
    company_id = current_user.get('companyId')
    if not company_id:
        return []
    
    # Get pricelists for this supplier
    pricelists = await db.pricelists.find({"supplierId": company_id}, {"_id": 0}).to_list(10000)
    
    # Get products and join data
    product_ids = [pl['productId'] for pl in pricelists]
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0}).to_list(10000)
    products_map = {p['id']: p for p in products}
    
    # Format for frontend (PriceList format)
    result = []
    for pl in pricelists:
        product = products_map.get(pl['productId'])
        if product:
            result.append({
                "id": pl['id'],
                "supplierCompanyId": pl['supplierId'],
                "productName": product['name'],
                "article": pl.get('supplierItemCode', ''),
                "price": pl['price'],
                "unit": product['unit'],
                "minQuantity": pl.get('minQuantity', 1),
                "availability": pl.get('availability', True),
                "active": pl.get('active', True),
                "createdAt": pl.get('createdAt', datetime.now(timezone.utc).isoformat()),
                "updatedAt": pl.get('createdAt', datetime.now(timezone.utc).isoformat())
            })
    
    return result

@api_router.post("/price-lists", response_model=PriceList)
async def create_price_list(data: PriceListCreate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    price_list = PriceList(
        supplierCompanyId=company['id'],
        **data.model_dump()
    )
    price_dict = price_list.model_dump()
    price_dict['createdAt'] = price_dict['createdAt'].isoformat()
    price_dict['updatedAt'] = price_dict['updatedAt'].isoformat()
    await db.price_lists.insert_one(price_dict)
    return price_list

@api_router.put("/price-lists/{price_id}")
async def update_price_list(price_id: str, data: PriceListUpdate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get company ID from user
    company_id = current_user.get('companyId')
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Update pricelist
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    
    result = await db.pricelists.update_one(
        {"id": price_id, "supplierId": company_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Price list item not found")
    
    # Get updated pricelist and join with product
    pricelist = await db.pricelists.find_one({"id": price_id}, {"_id": 0})
    product = await db.products.find_one({"id": pricelist['productId']}, {"_id": 0})
    
    # Return in expected format with actual saved values
    return {
        "id": pricelist['id'],
        "supplierCompanyId": pricelist['supplierId'],
        "productName": product['name'] if product else '',
        "article": pricelist.get('supplierItemCode', ''),
        "price": pricelist['price'],
        "unit": product['unit'] if product else '',
        "minQuantity": pricelist.get('minQuantity', 1),
        "availability": pricelist.get('availability', True),
        "active": pricelist.get('active', True),
        "createdAt": pricelist.get('createdAt', datetime.now(timezone.utc).isoformat()),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }

@api_router.delete("/price-lists/{price_id}")
async def delete_price_list(price_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get company ID from user
    company_id = current_user.get('companyId')
    if not company_id:
        raise HTTPException(status_code=404, detail="Company not found")
    
    result = await db.pricelists.delete_one({"id": price_id, "supplierId": company_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Price list not found")
    
    return {"message": "Price list deleted"}

@api_router.post("/price-lists/upload")
async def upload_price_list(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Read file
    contents = await file.read()
    
    try:
        # Try to parse as CSV or Excel
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")
        
        # Return columns for mapping
        return {
            "columns": df.columns.tolist(),
            "preview": df.head(5).to_dict('records'),
            "total_rows": len(df)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing file: {str(e)}")

@api_router.post("/price-lists/import")
async def import_price_list(
    file: UploadFile = File(...),
    column_mapping: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Parse column mapping
    import json
    mapping = json.loads(column_mapping)
    
    # Read file
    contents = await file.read()
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")
        
        # Import products
        imported_count = 0
        for _, row in df.iterrows():
            price_list = PriceList(
                supplierCompanyId=company['id'],
                productName=str(row[mapping.get('productName', 'productName')]),
                article=str(row[mapping.get('article', 'article')]),
                price=float(row[mapping.get('price', 'price')]),
                unit=str(row[mapping.get('unit', 'unit')]),
                availability=True,
                active=True
            )
            price_dict = price_list.model_dump()
            price_dict['createdAt'] = price_dict['createdAt'].isoformat()
            price_dict['updatedAt'] = price_dict['updatedAt'].isoformat()
            await db.price_lists.insert_one(price_dict)
            imported_count += 1
        
        return {"message": f"Successfully imported {imported_count} products"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error importing file: {str(e)}")

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
    current_user: dict = Depends(get_current_user)
):
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
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
    
    return document

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
    """Get supplier price lists with enhanced fuzzy search"""
    from enhanced_matching import normalize_with_synonyms, fuzzy_match
    
    query = {"supplierId": supplier_id}
    
    # Get all pricelists for this supplier
    pricelists = await db.pricelists.find(query, {"_id": 0}).to_list(10000)
    
    # Get all products
    product_ids = [pl['productId'] for pl in pricelists]
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0}).to_list(10000)
    products_map = {p['id']: p for p in products}
    
    # Join and filter
    result = []
    for pl in pricelists:
        product = products_map.get(pl['productId'])
        if product:
            # Skip if price is 0 (category headers)
            if pl.get('price', 0) <= 0:
                continue
            
            # Enhanced search with fuzzy matching
            if search:
                # Normalize and expand search with synonyms
                search_terms = [search.lower().strip()]
                
                # Add common typo corrections
                typo_map = {
                    'ласось': 'лосось',
                    'лососс': 'лосось',
                    'лососк': 'лосось',
                    'лосос': 'лосось',
                    'сибасс': 'сибас',
                    'сибаса': 'сибас',
                    'дорада': 'дорадо',
                    'креветка': 'креветки',
                    'креветк': 'креветки'
                }
                
                search_normalized = search.lower().strip()
                for typo, correct in typo_map.items():
                    if typo in search_normalized:
                        search_terms.append(search_normalized.replace(typo, correct))
                
                # Check if any search term matches
                product_name_lower = product['name'].lower()
                match_found = any(term in product_name_lower for term in search_terms)
                
                # Also try fuzzy match on words
                if not match_found:
                    search_words = search_normalized.split()
                    product_words = product_name_lower.split()
                    
                    for sw in search_words:
                        for pw in product_words:
                            # Simple fuzzy: allow 1-2 char difference
                            if len(sw) > 3 and len(pw) > 3:
                                if sw in pw or pw in sw:
                                    match_found = True
                                    break
                                # Check edit distance (simple)
                                if abs(len(sw) - len(pw)) <= 2:
                                    diff = sum(1 for a, b in zip(sw, pw) if a != b)
                                    if diff <= 2:
                                        match_found = True
                                        break
                        if match_found:
                            break
                
                if not match_found:
                    continue
            
            result.append({
                "id": pl['id'],
                "productId": pl['productId'],
                "supplierCompanyId": pl['supplierId'],
                "productName": product['name'],
                "article": pl.get('supplierItemCode', ''),
                "price": pl['price'],
                "unit": product['unit'],
                "minQuantity": pl.get('minQuantity', 1),
                "availability": True,
                "active": True,
                "createdAt": pl.get('createdAt', datetime.now(timezone.utc).isoformat()),
                "updatedAt": pl.get('createdAt', datetime.now(timezone.utc).isoformat())
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
    created_orders = []
    for supplier_id, order_data in orders_by_supplier.items():
        order = Order(
            customerCompanyId=matrix['restaurantCompanyId'],
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
        "brand_critical": False,            # По умолчанию OFF
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
    # P0: New fields for unit normalization
    selected_pack_base_qty: Optional[float] = None  # e.g., 5 (in grams)
    selected_pack_unit: Optional[str] = None  # e.g., "g"
    required_base_qty: Optional[float] = None  # e.g., 1000 (in grams)
    required_unit: Optional[str] = None  # e.g., "g"
    packs_needed: Optional[int] = None  # e.g., 200
    pack_explanation: Optional[str] = None  # e.g., "200 × 5 г = 1000 г"

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
        brand_critical = favorite.get('brand_critical', False)  # Schema v2
        if not isinstance(brand_critical, bool):
            # Fallback to legacy brandMode
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
                'unit_norm': si['unit_norm'],
                'brand_id': si.get('brand_id'),
                'origin_country': si.get('origin_country'),
                'origin_region': si.get('origin_region'),
                'origin_city': si.get('origin_city'),
                'net_weight_kg': si.get('net_weight_kg'),
                'net_volume_l': si.get('net_volume_l'),
                'base_unit': si.get('base_unit', si['unit_norm'])
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
            SearchLogger
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
        
        # Filter 1: super_class match
        step1 = [
            c for c in candidates 
            if c.get('super_class') == ref_super_class
            and c.get('price', 0) > 0
        ]
        logger.info(f"   После super_class filter ({ref_super_class}): {len(step1)}")
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
        
        # Filter 2: GUARDS (FORBIDDEN + REQUIRED ANCHORS) - Applied to CANDIDATE!
        step2_guards = []
        rejected_forbidden = 0
        rejected_anchors = 0
        
        for c in step1:
            candidate_name = c.get('name_raw', '')
            
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
            
            # Passed guards
            step2_guards.append(c)
        
        logger.info(f"   После guards filter: {len(step2_guards)} (rejected: {rejected_forbidden} forbidden, {rejected_anchors} missing_anchor)")
        search_logger.set_count('after_guards', len(step2_guards))
        search_logger.set_count('rejected_by_forbidden', rejected_forbidden)
        search_logger.set_count('rejected_by_missing_anchor', rejected_anchors)
        
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
        # Filter 3: Brand (if brand_critical=ON) - STRICT + TEXT FALLBACK
        if brand_critical and brand_id:
            from p0_hotfix_stabilization import load_brand_aliases, extract_brand_from_text
            
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
            
            search_logger.set_count('after_brand_filter', len(step3_brand))
        else:
            step3_brand = step2_guards
            logger.info(f"   Brand filter: SKIP (brand_critical={brand_critical})")
            search_logger.set_count('after_brand_filter', len(step3_brand))
        
        if len(step3_brand) == 0:
            search_logger.set_outcome('not_found', 'BRAND_REQUIRED_NOT_FOUND')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=f"Не найдено товаров бренда {brand_id}",
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'guards_applied': True,
                    'counts': {
                        'total': total_candidates,
                        'after_super_class': len(step1),
                        'after_guards': len(step2_guards),
                        'after_brand': 0
                    }
                }
            )
        
        # Filter 4: Unit Compatibility + Pack Calculation (P0 NEW LOGIC)
        step4_unit_compatible = []
        unit_mismatch_count = 0
        pack_calculated_count = 0
        
        for c in step3_brand:
            candidate_name = c.get('name_raw', '')
            
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
        
        logger.info(f"   После unit compatibility filter: {len(step4_unit_compatible)} (rejected: {unit_mismatch_count} unit_mismatch)")
        logger.info(f"   Pack calculated: {pack_calculated_count}")
        search_logger.set_count('after_unit_filter', len(step4_unit_compatible))
        search_logger.set_count('rejected_unit_mismatch', unit_mismatch_count)
        search_logger.set_count('pack_calculated', pack_calculated_count)
        
        if len(step4_unit_compatible) == 0:
            search_logger.set_outcome('not_found', 'UNIT_MISMATCH_ALL_REJECTED')
            search_logger.log()
            return AddFromFavoriteResponse(
                status="not_found",
                message=f"Не найдено товаров с совместимыми единицами измерения (rejected: {unit_mismatch_count} unit_mismatch)",
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'guards_applied': True,
                    'counts': {
                        'total': total_candidates,
                        'after_super_class': len(step1),
                        'after_guards': len(step2_guards),
                        'after_brand': len(step3_brand),
                        'after_unit_filter': 0,
                        'rejected_unit_mismatch': unit_mismatch_count
                    }
                }
            )
        
        # КРИТИЧНО: Sort by TOTAL_COST (price * total_cost_mult + pack_penalty)
        # 1. Товары с известным packs_needed → по total_cost
        # 2. Товары с неизвестным packs_needed → в конец
        def sort_key(c):
            packs = c.get('_packs_needed')
            mult = c.get('_total_cost_mult', 1.0)
            price = c.get('price', 999999)
            penalty = c.get('_pack_score_penalty', 0)
            
            # Если packs не определены → штраф
            if not packs:
                return (999999, penalty, price)
            
            # Рассчитываем total_cost
            total_cost = price * mult
            
            # Учитываем penalty (higher penalty = higher cost)
            adjusted_cost = total_cost * (1 + penalty * 0.01)
            
            return (adjusted_cost, penalty, price)
        
        step4_unit_compatible.sort(key=sort_key)
        logger.info(f"   Отсортировано по total_cost + pack penalty")
        
        winner = step4_unit_compatible[0]
        
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
        
        # Calculate match_percent with STRICT CLAMP 0..100 and pack penalty
        base_match_percent = calculate_match_percent(confidence)
        pack_penalty = winner.get('_pack_score_penalty', 0)
        match_percent = max(0, min(100, base_match_percent - pack_penalty))
        
        # Calculate actual total_cost
        packs_needed = winner.get('_packs_needed', 1)
        total_cost_mult = winner.get('_total_cost_mult', 1.0)
        actual_total_cost = winner.get('price', 0) * total_cost_mult
        
        # Log selection
        search_logger.set_selection(
            selected_item_id=winner.get('id'),
            supplier_id=supplier_id,
            price=winner.get('price'),
            match_percent=match_percent,
            total_cost=winner.get('price') * request.qty
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
                'total_cost': actual_total_cost
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
                # P0: New unit fields
                selected_pack_base_qty=cand_pack.base_qty if cand_pack else None,
                selected_pack_unit=cand_unit,
                required_base_qty=ref_pack_info.base_qty,
                required_unit=ref_unit,
                packs_needed=packs_needed,
                pack_explanation=pack_explanation
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
                        'pack_explanation': c.get('_pack_explanation', '')
                    }
                    for c in step4_unit_compatible[:5]
                ],
                debug_log={
                    'request_id': request_id,
                    'build_sha': BUILD_SHA,
                    'guards_applied': True,
                    'counts': {
                        'total': total_candidates,
                        'after_super_class': len(step1),
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

@api_router.get("/supplier/restaurants")
async def get_supplier_restaurants(current_user: dict = Depends(get_current_user)):
    """Get all restaurants that have ordered from this supplier"""
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company_id = current_user.get('companyId')
    if not company_id:
        return []
    
    # Get all orders for this supplier
    orders = await db.orders.find({"supplierCompanyId": company_id}, {"_id": 0}).to_list(1000)
    
    # Get unique restaurant IDs
    restaurant_ids = list(set([order['customerCompanyId'] for order in orders]))
    
    # Get restaurant details
    restaurants = []
    for rest_id in restaurant_ids:
        restaurant = await db.companies.find_one({"id": rest_id}, {"_id": 0})
        if restaurant:
            # Get settings for this supplier-restaurant pair
            settings = await db.supplier_restaurant_settings.find_one(
                {"supplierId": company_id, "restaurantId": rest_id},
                {"_id": 0}
            )
            
            # Count orders
            order_count = len([o for o in orders if o['customerCompanyId'] == rest_id])
            
            restaurants.append({
                "id": restaurant['id'],
                "name": restaurant.get('companyName', restaurant.get('name', 'N/A')),
                "inn": restaurant.get('inn', ''),
                "orderCount": order_count,
                "ordersEnabled": settings.get('ordersEnabled', True) if settings else True,
                "unavailabilityReason": settings.get('unavailabilityReason') if settings else None
            })
    
    return restaurants

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
    
    # Upsert settings
    settings = {
        "supplierId": company_id,
        "restaurantId": restaurant_id,
        "ordersEnabled": data.ordersEnabled,
        "unavailabilityReason": data.unavailabilityReason,
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    
    await db.supplier_restaurant_settings.update_one(
        {"supplierId": company_id, "restaurantId": restaurant_id},
        {"$set": settings},
        upsert=True
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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()