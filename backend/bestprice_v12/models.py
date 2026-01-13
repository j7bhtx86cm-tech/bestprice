"""
BestPrice v12 - Data Models

Сущности по ТЗ:
- CatalogReference (карточка каталога / избранное)
- SupplierItem (оффер поставщика) - уже есть
- CartItem (позиция корзины)
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


# === ENUMS ===

class UnitType(str, Enum):
    PIECE = "PIECE"
    WEIGHT = "WEIGHT"
    VOLUME = "VOLUME"


class ReasonCode(str, Enum):
    """Reason codes для логов и UI"""
    ANCHOR_USED_NO_CHEAPER = "ANCHOR_USED_NO_CHEAPER"
    SUBSTITUTED_CHEAPER = "SUBSTITUTED_CHEAPER"
    ANCHOR_INACTIVE_USED_BEST = "ANCHOR_INACTIVE_USED_BEST"
    NO_SAME_PACK_FOUND = "NO_SAME_PACK_FOUND"
    NO_VALID_CANDIDATES = "NO_VALID_CANDIDATES"
    TOPUP_APPLIED_QTY = "TOPUP_APPLIED_QTY"
    SUPPLIER_MIN_NOT_MET = "SUPPLIER_MIN_NOT_MET"


# === GLOBAL PARAMETERS (п.3 ТЗ) ===

PACK_MATCH_MODE = "STRICT"  # Пересчётов фасовки нет
MIN_SUPPLIER_ORDER_RUB = 10000  # Минималка по поставщику
TOPUP_THRESHOLD_RUB = 1000  # 10% от 10000 - порог для автодобивки


# === CATALOG REFERENCE (п.2.1 ТЗ) ===

class CatalogReference(BaseModel):
    """Карточка каталога / reference для избранного"""
    reference_id: str
    product_core_id: str
    unit_type: UnitType
    pack_value: Optional[float] = None  # Значение фасовки (1, 0.5, 2.5 и т.д.)
    pack_unit: Optional[str] = None  # Единица фасовки (кг, л, шт)
    brand_id: Optional[str] = None
    origin_country_id: Optional[str] = None
    origin_region_id: Optional[str] = None
    critical_attrs: Optional[Dict[str, Any]] = None  # JSON для fresh атрибутов
    anchor_supplier_item_id: str  # ID оффера-якоря (что пользователь видел в каталоге)
    
    # Дополнительные поля для UI
    name: str  # Название для отображения
    super_class: Optional[str] = None
    best_price: Optional[float] = None  # Кэш лучшей цены
    best_supplier_id: Optional[str] = None  # ID поставщика с лучшей ценой
    
    # Метаданные
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CatalogReferenceDB(BaseModel):
    """Модель для MongoDB (без _id)"""
    reference_id: str
    product_core_id: str
    unit_type: str
    pack_value: Optional[float] = None
    pack_unit: Optional[str] = None
    brand_id: Optional[str] = None
    origin_country_id: Optional[str] = None
    origin_region_id: Optional[str] = None
    critical_attrs: Optional[Dict[str, Any]] = None
    anchor_supplier_item_id: str
    name: str
    super_class: Optional[str] = None
    best_price: Optional[float] = None
    best_supplier_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# === CART ITEM (п.2.3 ТЗ) ===

class CartItem(BaseModel):
    """Позиция корзины с прозрачностью"""
    cart_item_id: str
    reference_id: str
    anchor_supplier_item_id: str
    selected_supplier_item_id: str
    supplier_id: str
    user_qty: float  # Как ввёл пользователь
    effective_qty: float  # После округления по min_order
    unit_type: UnitType
    price: float  # Цена за единицу
    line_total: float  # effective_qty * price
    substitution_applied: bool = False
    topup_applied: bool = False
    reason_code: Optional[ReasonCode] = None
    
    # Дополнительные поля для UI
    product_name: str
    supplier_name: Optional[str] = None
    original_price: Optional[float] = None  # Цена anchor (для показа экономии)
    original_supplier_name: Optional[str] = None
    savings: Optional[float] = None  # Экономия в рублях
    
    # Информация о min_order
    min_order_qty: int = 1
    qty_increased_reason: Optional[str] = None  # Причина увеличения qty


class CartItemDB(BaseModel):
    """Модель для MongoDB"""
    cart_item_id: str
    user_id: str
    reference_id: str
    anchor_supplier_item_id: str
    selected_supplier_item_id: str
    supplier_id: str
    user_qty: float
    effective_qty: float
    unit_type: str
    price: float
    line_total: float
    substitution_applied: bool = False
    topup_applied: bool = False
    reason_code: Optional[str] = None
    product_name: str
    supplier_name: Optional[str] = None
    original_price: Optional[float] = None
    original_supplier_name: Optional[str] = None
    savings: Optional[float] = None
    min_order_qty: int = 1
    qty_increased_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# === API REQUEST/RESPONSE MODELS ===

class AddToCartRequest(BaseModel):
    """Запрос добавления из избранного в корзину"""
    reference_id: str
    qty: float = Field(gt=0, description="Количество в единицах (шт/кг/л)")


class AddToCartResponse(BaseModel):
    """Ответ на добавление в корзину"""
    status: str  # "ok", "not_found", "error"
    cart_item: Optional[CartItem] = None
    message: Optional[str] = None
    reason_code: Optional[str] = None
    
    # Информация о замене для UI
    substituted: bool = False
    original_item_name: Optional[str] = None
    new_item_name: Optional[str] = None
    savings: Optional[float] = None


class CatalogItemResponse(BaseModel):
    """Карточка каталога для API"""
    reference_id: str
    name: str
    product_core_id: str
    unit_type: str
    pack_value: Optional[float] = None
    pack_unit: Optional[str] = None
    brand_id: Optional[str] = None
    origin_country: Optional[str] = None
    
    # Best Price информация
    best_price: Optional[float] = None
    best_supplier_name: Optional[str] = None
    min_order_info: Optional[str] = None  # "Мин. заказ: 5 шт"
    offers_count: int = 0  # Количество предложений


class CartSummary(BaseModel):
    """Сводка по корзине"""
    items: List[CartItem]
    total: float
    suppliers: List[Dict[str, Any]]  # Группировка по поставщикам
    has_minimum_issues: bool = False
    minimum_issues: List[Dict[str, Any]] = []  # Поставщики где не хватает до минималки


class SupplierSubtotal(BaseModel):
    """Сумма по поставщику"""
    supplier_id: str
    supplier_name: str
    subtotal: float
    deficit: float  # 10000 - subtotal (если < 0, то всё ок)
    can_topup: bool  # deficit <= 1000
    items_count: int


# === SEED FAVORITES REQUEST ===

class SeedFavoritesRequest(BaseModel):
    """Запрос на добавление случайных карточек в избранное"""
    user_id: str
    count: int = Field(default=100, ge=1, le=500)
    filters: Optional[Dict[str, Any]] = None  # Опциональные фильтры


class SeedFavoritesResponse(BaseModel):
    """Ответ на seed favorites"""
    status: str
    added_count: int
    skipped_duplicates: int
    message: Optional[str] = None
