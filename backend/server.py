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
    mode: str = "cheapest"  # "exact" or "cheapest" - default to cheapest
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
    suppliers = await db.companies.find({"companyType": "supplier"}, {"_id": 0}).to_list(1000)
    logging.info(f"Found {len(suppliers)} suppliers in database")
    # Map to expected frontend format
    result = []
    for s in suppliers:
        result.append({
            "id": s['id'],
            "companyName": s['name'],
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
    """Add product to favorites"""
    
    # Get user's company
    company_id = current_user.get('companyId')
    if current_user['role'] == 'customer':
        company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
        company_id = company['id'] if company else None
    
    # Get product details
    product = await db.products.find_one({"id": data['productId']}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get product code from pricelist
    pricelist = await db.pricelists.find_one({"productId": data['productId']}, {"_id": 0})
    product_code = pricelist.get('supplierItemCode', '') if pricelist else ''
    
    # Check if already in favorites
    existing = await db.favorites.find_one({
        "userId": current_user['id'],
        "productId": data['productId']
    }, {"_id": 0})
    
    if existing:
        raise HTTPException(status_code=400, detail="Product already in favorites")
    
    # Create favorite with default mode "exact" (not cheapest!)
    favorite = {
        "id": str(uuid.uuid4()),
        "userId": current_user['id'],
        "companyId": company_id,
        "productId": data['productId'],
        "productName": product['name'],
        "productCode": product_code,
        "unit": product['unit'],
        "mode": "exact",  # DEFAULT TO EXACT
        "originalSupplierId": data.get('supplierId'),
        "originalPrice": pricelist['price'] if pricelist else None,  # Store original price
        "addedAt": datetime.now(timezone.utc).isoformat()
    }
    
    await db.favorites.insert_one(favorite)
    
    return {
        "id": favorite['id'],
        "productName": favorite['productName'],
        "productCode": favorite['productCode'],
        "unit": favorite['unit'],
        "mode": favorite['mode']
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


# NEW UNIVERSAL MATCHING ENGINE ENDPOINT
@api_router.get("/favorites/v2")
async def get_favorites_v2(current_user: dict = Depends(get_current_user)):
    """Get favorites with HYBRID matching engine (best of spec + simple)"""
    from matching.hybrid_matcher import find_best_match_hybrid
    
    favorites = await db.favorites.find({"userId": current_user['id']}, {"_id": 0}).sort("displayOrder", 1).to_list(100)
    
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
            # Use HYBRID matcher (best of spec + simple)
            winner = find_best_match_hybrid(
                query_product_name=original_product['name'],
                original_price=original_price,
                all_items=all_items
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
async def get_favorites(current_user: dict = Depends(get_current_user)):
    """Get user's favorites with product matching"""
    from product_intent_parser import extract_product_type, extract_weight_kg, extract_caliber
    
    favorites = await db.favorites.find({"userId": current_user['id']}, {"_id": 0}).sort("displayOrder", 1).to_list(100)
    
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