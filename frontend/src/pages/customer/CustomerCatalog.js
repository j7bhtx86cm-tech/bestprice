import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Search, Heart, ShoppingCart, Package, TrendingDown,
  ChevronLeft, ChevronRight, RefreshCw, AlertTriangle, Layers
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';
import OfferSelectModal from '@/components/OfferSelectModal';
import SearchAutocomplete from '@/components/SearchAutocomplete';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Debounce hook for search
const useDebounce = (value, delay) => {
  const [debouncedValue, setDebouncedValue] = useState(value);
  
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    
    return () => clearTimeout(handler);
  }, [value, delay]);
  
  return debouncedValue;
};

// Catalog Item Card - стиль v12 (P1: добавлен выбор оффера)
const CatalogItemCard = ({ item, onAddToFavorites, onRemoveFromFavorites, onAddToCart, onShowOffers, isInFavorites, isInCart }) => {
  const [adding, setAdding] = useState(false);
  const [addedToCart, setAddedToCart] = useState(false);
  const [inFavorites, setInFavorites] = useState(isInFavorites);
  const [qty, setQty] = useState(1);  // P1.3: количество для добавления

  // Sync with parent state
  React.useEffect(() => {
    setInFavorites(isInFavorites);
  }, [isInFavorites]);

  const handleToggleFavorites = async () => {
    setAdding(true);
    try {
      if (inFavorites) {
        await onRemoveFromFavorites(item);
        setInFavorites(false);
        toast.success('Удалено из избранного');
      } else {
        await onAddToFavorites(item);
        setInFavorites(true);
        toast.success('Добавлено в избранное');
      }
    } catch (error) {
      toast.error('Ошибка');
    } finally {
      setAdding(false);
    }
  };

  // P1.3: Добавление с выбранным количеством
  const handleAddToCart = async () => {
    setAdding(true);
    try {
      await onAddToCart(item, qty);  // Передаём qty
      setAddedToCart(true);
      toast.success(`Добавлено в корзину: ${qty} шт.`);
    } catch (error) {
      toast.error(error.message || 'Ошибка добавления');
    } finally {
      setAdding(false);
    }
  };

  // Format price
  const formatPrice = (price) => {
    if (!price) return 'Нет цены';
    return `${price.toLocaleString('ru-RU')} ₽`;
  };

  // Get category badge color
  const getCategoryColor = (superClass) => {
    if (!superClass) return 'bg-gray-100 text-gray-800';
    if (superClass.startsWith('seafood')) return 'bg-blue-100 text-blue-800';
    if (superClass.startsWith('meat')) return 'bg-red-100 text-red-800';
    if (superClass.startsWith('dairy')) return 'bg-yellow-100 text-yellow-800';
    if (superClass.startsWith('vegetables')) return 'bg-green-100 text-green-800';
    if (superClass.startsWith('fruits')) return 'bg-orange-100 text-orange-800';
    if (superClass.startsWith('bakery')) return 'bg-amber-100 text-amber-800';
    if (superClass.startsWith('beverages')) return 'bg-cyan-100 text-cyan-800';
    if (superClass.startsWith('condiments')) return 'bg-purple-100 text-purple-800';
    if (superClass.startsWith('pasta')) return 'bg-yellow-100 text-yellow-800';
    if (superClass.startsWith('staples')) return 'bg-amber-100 text-amber-800';
    if (superClass.startsWith('canned')) return 'bg-slate-100 text-slate-800';
    if (superClass.startsWith('oils')) return 'bg-lime-100 text-lime-800';
    if (superClass.startsWith('frozen')) return 'bg-sky-100 text-sky-800';
    if (superClass.startsWith('desserts')) return 'bg-pink-100 text-pink-800';
    if (superClass.startsWith('ready_meals')) return 'bg-indigo-100 text-indigo-800';
    if (superClass.startsWith('packaging')) return 'bg-stone-100 text-stone-800';
    if (superClass.startsWith('disposables')) return 'bg-neutral-100 text-neutral-800';
    return 'bg-gray-100 text-gray-800';
  };

  return (
    <Card className={`p-4 hover:shadow-lg transition-all border-2 ${inFavorites ? 'border-red-300 bg-red-50' : 'hover:border-blue-300'}`}>
      {/* Header with category */}
      <div className="flex justify-between items-start mb-3">
        <Badge className={getCategoryColor(item.super_class)} variant="secondary">
          {item.super_class?.split('.')[0] || 'other'}
        </Badge>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleToggleFavorites}
          disabled={adding}
          className={inFavorites ? 'text-red-500' : 'text-gray-400 hover:text-red-500'}
          title={inFavorites ? 'Убрать из избранного' : 'Добавить в избранное'}
        >
          <Heart className={`h-5 w-5 ${inFavorites ? 'fill-current' : ''}`} />
        </Button>
      </div>

      {/* Product name */}
      <h3 className="font-semibold text-base mb-2 line-clamp-2 min-h-[48px]">
        {item.name_raw || item.name}
      </h3>

      {/* Pack info */}
      {item.pack_qty > 1 && (
        <p className="text-sm text-gray-600 mb-2">
          Фасовка: {item.pack_qty} {item.unit_type === 'WEIGHT' ? 'кг' : item.unit_type === 'VOLUME' ? 'л' : 'шт'}
        </p>
      )}

      {/* Price */}
      <div className="flex items-center gap-2 mb-3">
        <TrendingDown className="h-4 w-4 text-green-600" />
        <span className="text-lg font-bold text-green-600">
          {formatPrice(item.price || item.best_price)}
        </span>
      </div>

      {/* Supplier */}
      {(item.supplier_name || item.best_supplier_name) && (
        <p className="text-sm text-gray-500 mb-3">
          <Package className="h-3 w-3 inline mr-1" />
          {item.supplier_name || item.best_supplier_name}
        </p>
      )}

      {/* P1.3: Quantity input (как в избранном) */}
      <div className="flex items-center gap-2 mb-3">
        <label className="text-sm text-gray-600">Кол-во:</label>
        <Input
          type="number"
          min="1"
          value={qty}
          onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
          className="w-20"
          disabled={adding || isInCart || addedToCart}
        />
        <span className="text-sm text-gray-500">
          {item.unit_type === 'WEIGHT' ? 'кг' : item.unit_type === 'VOLUME' ? 'л' : 'шт'}
        </span>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          className={`${inFavorites ? 'bg-red-50 border-red-300 text-red-600' : 'text-gray-400 hover:text-red-500 hover:border-red-300'}`}
          onClick={handleToggleFavorites}
          disabled={adding}
          title={inFavorites ? 'Убрать из избранного' : 'Добавить в избранное'}
        >
          <Heart className={`h-5 w-5 ${inFavorites ? 'fill-red-500' : ''}`} />
        </Button>
        
        {/* Кнопка выбора оффера (P1) */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => onShowOffers(item)}
          disabled={adding}
          title="Сравнить предложения"
          data-testid="compare-offers-btn"
        >
          <Layers className="h-4 w-4" />
        </Button>
        
        <Button
          size="sm"
          className={`flex-1 ${(isInCart || addedToCart) ? 'bg-green-600 hover:bg-green-700' : ''}`}
          onClick={handleAddToCart}
          disabled={adding || isInCart || addedToCart}
          data-testid="add-to-cart-btn"
        >
          <ShoppingCart className="h-4 w-4 mr-1" />
          {(isInCart || addedToCart) ? '✓ В корзине' : 'В корзину'}
        </Button>
      </div>
    </Card>
  );
};

// Loading skeleton
const CatalogSkeleton = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
    {[...Array(8)].map((_, i) => (
      <Card key={i} className="p-4">
        <Skeleton className="h-6 w-20 mb-3" />
        <Skeleton className="h-12 w-full mb-2" />
        <Skeleton className="h-4 w-32 mb-2" />
        <Skeleton className="h-8 w-24 mb-3" />
        <div className="flex gap-2">
          <Skeleton className="h-9 flex-1" />
          <Skeleton className="h-9 flex-1" />
        </div>
      </Card>
    ))}
  </div>
);

// Main Catalog Component
export const CustomerCatalog = () => {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState('');  // Immediate input state
  const [category, setCategory] = useState('');
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [favorites, setFavorites] = useState(new Set());
  const [cartCount, setCartCount] = useState(0);
  const [cartItems, setCartItems] = useState(new Set());
  
  // P1: Состояние модального окна выбора оффера
  const [offerModalOpen, setOfferModalOpen] = useState(false);
  const [selectedItemForOffers, setSelectedItemForOffers] = useState(null);
  
  const LIMIT = 20;
  
  // Debounced search value (300ms delay)
  const search = useDebounce(searchInput, 300);

  // Get auth headers
  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Get user ID from auth context
  const getUserId = () => {
    return user?.id || 'anonymous';
  };

  // Fetch cart count
  const fetchCartCount = useCallback(async () => {
    try {
      const userId = getUserId();
      if (!userId || userId === 'anonymous') return;
      
      const response = await axios.get(`${API}/v12/cart?user_id=${userId}`, {
        headers: getHeaders()
      });
      const items = response.data.items || [];
      setCartCount(items.length);
      setCartItems(new Set(items.map(i => i.supplier_item_id)));
    } catch (error) {
      console.error('Failed to fetch cart:', error);
    }
  }, [user]);

  // Fetch catalog from v12 API
  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: page * LIMIT,
        limit: LIMIT,
      });
      if (search) params.append('search', search);
      if (category) params.append('super_class', category);

      const response = await axios.get(`${API}/v12/catalog?${params}`, {
        headers: getHeaders()
      });
      
      setItems(response.data.items || []);
      setTotal(response.data.total || 0);
    } catch (error) {
      console.error('Failed to fetch catalog:', error);
      toast.error('Ошибка загрузки каталога');
    } finally {
      setLoading(false);
    }
  }, [page, search, category]);

  // Fetch favorites to mark items
  const fetchFavorites = useCallback(async () => {
    try {
      const userId = getUserId();
      if (!userId || userId === 'anonymous') return;
      
      const response = await axios.get(`${API}/v12/favorites?user_id=${userId}&limit=500`, {
        headers: getHeaders()
      });
      // Собираем все возможные ID для сопоставления:
      // - reference_id (новый формат = supplier_item.id)
      // - anchor_supplier_item_id (старый формат)
      const favIds = new Set();
      response.data.items?.forEach(f => {
        if (f.reference_id) favIds.add(f.reference_id);
        if (f.anchor_supplier_item_id) favIds.add(f.anchor_supplier_item_id);
      });
      setFavorites(favIds);
    } catch (error) {
      console.error('Failed to fetch favorites:', error);
    }
  }, [user]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  useEffect(() => {
    if (user?.id) {
      fetchFavorites();
      fetchCartCount();
    }
  }, [fetchFavorites, fetchCartCount, user]);

  // Add to favorites
  const handleAddToFavorites = async (item) => {
    const userId = getUserId();
    // Используем item.id - это supplier_item.id
    const refId = item.id;
    try {
      const response = await axios.post(`${API}/v12/favorites?user_id=${userId}&reference_id=${refId}`, {}, {
        headers: getHeaders()
      });
      if (response.data.status === 'ok' || response.data.status === 'duplicate') {
        setFavorites(prev => new Set([...prev, refId]));
        return response.data;
      }
    } catch (error) {
      console.error('Failed to add to favorites:', error);
      throw error;
    }
  };

  // Remove from favorites
  const handleRemoveFromFavorites = async (item) => {
    const userId = getUserId();
    const refId = item.id;
    try {
      // Найдём favorite_id по reference_id
      const response = await axios.get(`${API}/v12/favorites?user_id=${userId}&limit=1000`, {
        headers: getHeaders()
      });
      const fav = response.data.items?.find(f => 
        f.reference_id === refId || f.anchor_supplier_item_id === refId
      );
      
      if (fav) {
        await axios.delete(`${API}/v12/favorites/${fav.id}?user_id=${userId}`, {
          headers: getHeaders()
        });
        setFavorites(prev => {
          const newSet = new Set(prev);
          newSet.delete(refId);
          if (fav.anchor_supplier_item_id) newSet.delete(fav.anchor_supplier_item_id);
          return newSet;
        });
      }
    } catch (error) {
      console.error('Failed to remove from favorites:', error);
      throw error;
    }
  };

  // P1.3: Add to cart with quantity support
  const handleAddToCart = async (item, qty = 1) => {
    const userId = getUserId();
    
    // Для каталога используем supplier_item_id (item.id)
    // Для избранного используем reference_id
    const requestData = {
      qty: qty,  // P1.3: используем переданное количество
      user_id: userId
    };
    
    // Определяем что передавать
    if (item.reference_id) {
      requestData.reference_id = item.reference_id;
    } else {
      // Из каталога - используем id как supplier_item_id
      requestData.supplier_item_id = item.id || item.unique_key;
    }
    
    const response = await axios.post(`${API}/v12/cart/intent`, requestData, {
      headers: getHeaders()
    });

    if (response.data.status !== 'ok') {
      throw new Error(response.data.message || 'Ошибка добавления');
    }
    
    // Обновляем счётчик корзины
    setCartCount(prev => prev + 1);
    const itemKey = item.reference_id || item.id || item.unique_key;
    setCartItems(prev => new Set([...prev, itemKey]));
  };

  // P1: Показать модальное окно выбора оффера
  const handleShowOffers = (item) => {
    setSelectedItemForOffers({
      id: item.id || item.unique_key,
      name: item.name_raw || item.name,
      price: item.price || item.best_price,
      pack_qty: item.pack_qty,
      unit_type: item.unit_type,
      supplier_name: item.supplier_name || item.best_supplier_name,
      supplier_id: item.supplier_company_id,
    });
    setOfferModalOpen(true);
  };

  // P1: Добавить выбранный оффер в корзину
  const handleOfferSelect = async (offer, qty) => {
    try {
      await handleAddToCart({ 
        id: offer.id,
        unit_type: offer.unit_type,
      }, qty);
      toast.success(`Добавлено в корзину: ${qty} ${offer.unit_type === 'WEIGHT' ? 'кг' : 'шт'}`);
    } catch (error) {
      toast.error(error.message || 'Ошибка добавления');
    }
  };

  // Search handler - updates immediate input, debounce handles API call
  const handleSearch = (value) => {
    setSearchInput(value);
    setPage(0);
  };

  // Categories for filter
  const categories = [
    { value: '', label: 'Все категории' },
    { value: 'seafood', label: '🐟 Морепродукты' },
    { value: 'meat', label: '🥩 Мясо' },
    { value: 'dairy', label: '🧀 Молочные' },
    { value: 'vegetables', label: '🥬 Овощи' },
    { value: 'fruits', label: '🍎 Фрукты' },
    { value: 'bakery', label: '🍞 Выпечка' },
    { value: 'beverages', label: '🥤 Напитки' },
    { value: 'condiments', label: '🧂 Приправы' },
    { value: 'pasta', label: '🍝 Макароны' },
    { value: 'staples', label: '🌾 Крупы' },
    { value: 'canned', label: '🥫 Консервы' },
    { value: 'oils', label: '🫒 Масла' },
    { value: 'frozen', label: '❄️ Заморозка' },
    { value: 'desserts', label: '🍰 Десерты' },
    { value: 'ready_meals', label: '🍱 Готовые блюда' },
    { value: 'packaging', label: '📦 Упаковка' },
  ];

  const totalPages = Math.ceil(total / LIMIT);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold">Каталог товаров</h1>
          <p className="text-gray-600">
            {total} товаров • Best Price • STRICT фасовка
          </p>
        </div>
        
        {/* Cart button with counter */}
        {cartCount > 0 && (
          <Button 
            onClick={() => window.location.href = '/customer/cart'}
            className="bg-blue-600 hover:bg-blue-700"
            data-testid="cart-btn"
          >
            <ShoppingCart className="h-4 w-4 mr-2" />
            Корзина ({cartCount})
          </Button>
        )}
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Поиск товаров..."
              value={searchInput}
              onChange={(e) => handleSearch(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Category filter */}
          <select
            value={category}
            onChange={(e) => { setCategory(e.target.value); setPage(0); }}
            className="px-4 py-2 border rounded-md bg-white"
          >
            {categories.map(cat => (
              <option key={cat.value} value={cat.value}>{cat.label}</option>
            ))}
          </select>

          {/* P1.4: Кнопка "Обновить" удалена */}
        </div>
      </Card>

      {/* Catalog Grid */}
      {loading ? (
        <CatalogSkeleton />
      ) : items.length === 0 ? (
        <Card className="p-12 text-center">
          <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-yellow-500" />
          <p className="text-gray-600 mb-2">Товары не найдены</p>
          <p className="text-sm text-gray-500">Попробуйте изменить параметры поиска</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {items.map(item => (
            <CatalogItemCard
              key={item.id || item.reference_id}
              item={item}
              onAddToFavorites={handleAddToFavorites}
              onRemoveFromFavorites={handleRemoveFromFavorites}
              onAddToCart={handleAddToCart}
              onShowOffers={handleShowOffers}
              isInFavorites={favorites.has(item.id) || favorites.has(item.reference_id)}
              isInCart={cartItems.has(item.id) || cartItems.has(item.reference_id)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-4">
          <Button
            variant="outline"
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            Назад
          </Button>
          
          <span className="text-sm text-gray-600">
            Страница {page + 1} из {totalPages}
          </span>
          
          <Button
            variant="outline"
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
          >
            Вперёд
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      )}

      {/* P1: Модальное окно выбора оффера */}
      <OfferSelectModal
        isOpen={offerModalOpen}
        onClose={() => setOfferModalOpen(false)}
        sourceItem={selectedItemForOffers}
        onSelect={handleOfferSelect}
        getHeaders={getHeaders}
      />
    </div>
  );
};

export default CustomerCatalog;
