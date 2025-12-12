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
    company = await db.companies.find_one({"userId": user['id']}, {"_id": 0})
    
    token = create_access_token({"sub": user['id'], "role": user['role']})
    
    return TokenResponse(
        access_token=token,
        user={
            "id": user['id'],
            "email": user['email'],
            "role": user['role'],
            "companyId": company['id'] if company else None
        }
    )

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    return {
        "id": current_user['id'],
        "email": current_user['email'],
        "role": current_user['role'],
        "companyId": company['id'] if company else None
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

@api_router.get("/price-lists/my", response_model=List[PriceList])
async def get_my_price_lists(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    price_lists = await db.price_lists.find({"supplierCompanyId": company['id']}, {"_id": 0}).to_list(1000)
    return price_lists

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

@api_router.put("/price-lists/{price_id}", response_model=PriceList)
async def update_price_list(price_id: str, data: PriceListUpdate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data['updatedAt'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.price_lists.update_one(
        {"id": price_id, "supplierCompanyId": company['id']},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Price list not found")
    
    price_list = await db.price_lists.find_one({"id": price_id}, {"_id": 0})
    return price_list

@api_router.delete("/price-lists/{price_id}")
async def delete_price_list(price_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != UserRole.supplier:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    result = await db.price_lists.delete_one({"id": price_id, "supplierCompanyId": company['id']})
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
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    if current_user['role'] == UserRole.supplier:
        orders = await db.orders.find({"supplierCompanyId": company['id']}, {"_id": 0}).to_list(1000)
    else:
        orders = await db.orders.find({"customerCompanyId": company['id']}, {"_id": 0}).to_list(1000)
    
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
    
    company = await db.companies.find_one({"userId": current_user['id']}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Check if user has access to this order
    if order['customerCompanyId'] != company['id'] and order['supplierCompanyId'] != company['id']:
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
    total_amount = sum(order['amount'] for order in orders)
    
    # Get all products and suppliers
    all_products = await db.price_lists.find({}, {"_id": 0}).to_list(10000)
    
    # Calculate CORRECT savings: Best possible price vs what customer paid
    all_ordered_items = []
    optimal_total = 0
    actual_total = 0
    
    for order in orders:
        for item in order.get('orderDetails', []):
            # Find ALL suppliers offering this product
            matching_products = [p for p in all_products 
                               if p['productName'].lower() == item['productName'].lower() 
                               and p['unit'].lower() == item['unit'].lower()]
            
            if matching_products:
                # Find CHEAPEST price across ALL suppliers
                cheapest_price = min(p['price'] for p in matching_products)
                optimal_item_cost = cheapest_price * item['quantity']
                actual_item_cost = item['price'] * item['quantity']
                
                optimal_total += optimal_item_cost
                actual_total += actual_item_cost
            else:
                # If product not found in current catalog, use paid price
                actual_total += item['price'] * item['quantity']
                optimal_total += item['price'] * item['quantity']
    
    # Calculate savings
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

@api_router.get("/suppliers", response_model=List[Company])
async def get_suppliers():
    suppliers = await db.companies.find({"type": CompanyType.supplier}, {"_id": 0}).to_list(1000)
    return suppliers

@api_router.get("/suppliers/{supplier_id}/price-lists", response_model=List[PriceList])
async def get_supplier_price_lists(supplier_id: str):
    price_lists = await db.price_lists.find({"supplierCompanyId": supplier_id, "active": True}, {"_id": 0}).to_list(10000)
    return price_lists

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