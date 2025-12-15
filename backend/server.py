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
    lastOrderQuantity: Optional[float] = None
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MatrixProductCreate(BaseModel):
    productId: str
    productName: Optional[str] = None  # If not provided, use global product name
    productCode: Optional[str] = None

class MatrixProductUpdate(BaseModel):
    productName: Optional[str] = None
    lastOrderQuantity: Optional[float] = None

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
    if current_user['role'] == UserRole.responsible:
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
    
    # Calculate CORRECT BestPrice value: Compare best possible vs actual paid
    optimal_total = 0  # Best possible if buying each item at cheapest price
    actual_total = 0   # What customer actually paid
    
    for order in orders:
        for item in order.get('orderDetails', []):
            actual_item_cost = item['price'] * item['quantity']
            actual_total += actual_item_cost
            
            # Find ALL suppliers offering this exact product
            matching_products = [p for p in all_products 
                               if p['productName'].lower() == item['productName'].lower() 
                               and p['unit'].lower() == item['unit'].lower()]
            
            if matching_products:
                # Find CHEAPEST price across ALL suppliers  
                cheapest_price = min(p['price'] for p in matching_products)
                optimal_item_cost = cheapest_price * item['quantity']
                optimal_total += optimal_item_cost
            else:
                # Product not in catalog, use actual price
                optimal_total += actual_item_cost
    
    # Calculate savings (should be 0 or positive if BestPrice is working correctly)
    actual_savings = optimal_total - actual_total
    savings_percentage = (actual_savings / optimal_total * 100) if optimal_total > 0 else 0
    
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
        "savings": actual_savings,
        "savingsPercentage": savings_percentage,
        "optimalCost": optimal_total,
        "actualCost": actual_total,
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
    query = {"supplierId": supplier_id}
    
    # Get all pricelists for this supplier
    pricelists = await db.pricelists.find(query, {"_id": 0}).to_list(10000)
    
    # Get all products
    product_ids = [pl['productId'] for pl in pricelists]
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0}).to_list(10000)
    
    # Create product lookup map
    products_map = {p['id']: p for p in products}
    
    # Join pricelists with products to create the format frontend expects
    result = []
    for pl in pricelists:
        product = products_map.get(pl['productId'])
        if product:
            # Enhanced search with synonym support
            if search:
                search_lower = search.lower().strip()
                product_name_lower = product['name'].lower()
                
                # Define synonyms and translations
                synonyms_map = {
                    # English to Russian food terms
                    "sweet chili": ["кисло острый", "кисло-острый", "свит чили"],
                    "chili": ["чили", "перец"],
                    "sauce": ["соус"],
                    "sweet": ["сладкий", "кисло"],
                    "cheese": ["сыр"],
                    "chicken": ["курица", "куриный", "курин"],
                    "beef": ["говядина", "говяжий"],
                    "pork": ["свинина", "свиной"],
                    "fish": ["рыба", "рыбный"],
                    "potato": ["картофель", "картошка"],
                    "tomato": ["помидор", "томат"],
                    "mushroom": ["гриб", "грибы", "грибной", "шампиньон"],
                    "rice": ["рис"],
                    "pasta": ["макароны", "паста"],
                    "butter": ["масло"],
                    "oil": ["масло"],
                    "milk": ["молоко"],
                    "cream": ["сливки", "крем"],
                    "sugar": ["сахар"],
                    "salt": ["соль"],
                    "pepper": ["перец"],
                    "onion": ["лук", "луковый"],
                    "garlic": ["чеснок"],
                    "bread": ["хлеб"],
                    # Russian variations
                    "кисло острый": ["sweet chili", "кисло-острый", "свит чили"],
                    "грибы": ["mushroom", "гриб", "грибной", "шампиньон", "опята", "вешенки"],
                    "шампиньоны": ["mushroom", "грибы"],
                    "соус": ["sauce"],
                }
                
                # Build search terms including original and synonyms
                search_terms = [search_lower]
                for key, values in synonyms_map.items():
                    if key in search_lower:
                        search_terms.extend(values)
                
                # Check if any search term matches product name
                match_found = any(term in product_name_lower for term in search_terms)
                
                if not match_found:
                    continue  # Skip this product if search doesn't match
            
            # Create PriceList response format that frontend expects
            result.append({
                "id": pl['id'],
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
    
    # Create matrix product
    matrix_product = MatrixProduct(
        matrixId=matrix_id,
        rowNumber=next_row,
        productId=data.productId,
        productName=data.productName if data.productName else product['name'],
        productCode=data.productCode if data.productCode else product_code,
        unit=product['unit']
    )
    
    mp_dict = matrix_product.model_dump()
    mp_dict['createdAt'] = mp_dict['createdAt'].isoformat()
    await db.matrix_products.insert_one(mp_dict)
    
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
        
        # Get best price supplier for this product
        pricelists = await db.pricelists.find(
            {"productId": matrix_product['productId']}, 
            {"_id": 0}
        ).to_list(100)
        
        if not pricelists:
            continue
        
        # Sort by price and get cheapest
        pricelists.sort(key=lambda x: x['price'])
        best_pl = pricelists[0]
        
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