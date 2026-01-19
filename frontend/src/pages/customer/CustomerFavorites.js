import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Heart, Trash2, ShoppingCart, Search,
  TrendingDown, Loader2
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

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

// Favorite Item Card
const FavoriteItemCard = ({ item, onRemove, onAddToCart, adding, isInCart }) => {
  const [qty, setQty] = useState(1);
  const [addedToCart, setAddedToCart] = useState(false);

  const handleAddClick = async () => {
    console.log('handleAddClick called for item:', item.id);
    try {
      await onAddToCart(item, qty);
      setAddedToCart(true);
    } catch (error) {
      console.error('Error in handleAddClick:', error);
      // Error already handled in parent
    }
  };

  return (
    <Card className="p-4 hover:shadow-lg transition-all">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <Badge className={getCategoryColor(item.super_class)} variant="secondary">
          {item.super_class?.split('.')[0] || 'other'}
        </Badge>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRemove(item.id)}
          className="text-red-500 hover:text-red-700 -mt-1 -mr-2"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      {/* Product name */}
      <h3 className="font-semibold text-base mb-2 line-clamp-2 min-h-[48px]">
        {item.product_name}
      </h3>

      {/* Pack info */}
      {item.pack_value && item.pack_unit && (
        <p className="text-sm text-gray-600 mb-2">
          Фасовка: {item.pack_value} {item.pack_unit}
        </p>
      )}

      {/* Best price */}
      {item.best_price && (
        <div className="flex items-center gap-2 mb-3">
          <TrendingDown className="h-4 w-4 text-green-600" />
          <span className="text-lg font-bold text-green-600">
            {item.best_price.toLocaleString('ru-RU')} ₽
          </span>
        </div>
      )}

      {/* Quantity input */}
      <div className="flex items-center gap-2 mb-3">
        <label className="text-sm text-gray-600">Кол-во:</label>
        <Input
          type="number"
          min="1"
          value={qty}
          onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
          className="w-20"
        />
        <span className="text-sm text-gray-500">
          {item.unit_type === 'WEIGHT' ? 'кг' : item.unit_type === 'VOLUME' ? 'л' : 'шт'}
        </span>
      </div>

      {/* Add to cart */}
      <Button
        className={`w-full ${(isInCart || addedToCart) ? 'bg-green-600 hover:bg-green-700' : ''}`}
        onClick={handleAddClick}
        disabled={adding === item.id || isInCart || addedToCart}
      >
        {adding === item.id ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Добавление...
          </>
        ) : (isInCart || addedToCart) ? (
          <>
            <ShoppingCart className="h-4 w-4 mr-2" />
            ✓ В корзине
          </>
        ) : (
          <>
            <ShoppingCart className="h-4 w-4 mr-2" />
            В корзину
          </>
        )}
      </Button>
    </Card>
  );
};

// Main Favorites Component
export const CustomerFavorites = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [favorites, setFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [adding, setAdding] = useState(null);
  const [cartItems, setCartItems] = useState(new Set());
  const [cartCount, setCartCount] = useState(0);

  // Categories for filter (same as catalog)
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

  // Get user ID from auth context
  const getUserId = () => {
    return user?.id || 'anonymous';
  };

  // Get auth headers
  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Fetch favorites
  const fetchFavorites = useCallback(async () => {
    setLoading(true);
    try {
      const userId = getUserId();
      if (!userId || userId === 'anonymous') {
        setLoading(false);
        return;
      }
      
      const response = await axios.get(`${API}/v12/favorites?user_id=${userId}&limit=1000`, {
        headers: getHeaders()
      });
      setFavorites(response.data.items || []);
    } catch (error) {
      console.error('Failed to fetch favorites:', error);
      toast.error('Ошибка загрузки избранного');
    } finally {
      setLoading(false);
    }
  }, [user]);

  // Fetch cart to show which items are already in cart
  const fetchCart = useCallback(async () => {
    try {
      const userId = getUserId();
      if (!userId || userId === 'anonymous') return;
      
      const response = await axios.get(`${API}/v12/cart?user_id=${userId}`, {
        headers: getHeaders()
      });
      const items = response.data.items || [];
      setCartCount(items.length);
      // Store both supplier_item_id and reference_id for matching
      const cartSet = new Set();
      items.forEach(i => {
        if (i.supplier_item_id) cartSet.add(i.supplier_item_id);
      });
      setCartItems(cartSet);
    } catch (error) {
      console.error('Failed to fetch cart:', error);
    }
  }, [user]);

  useEffect(() => {
    if (user?.id) {
      fetchFavorites();
      fetchCart();
    }
  }, [fetchFavorites, fetchCart, user]);

  // Remove from favorites
  const handleRemove = async (favoriteId) => {
    if (!confirm('Удалить из избранного?')) return;
    
    try {
      const userId = getUserId();
      await axios.delete(`${API}/v12/favorites/${favoriteId}?user_id=${userId}`, {
        headers: getHeaders()
      });
      setFavorites(prev => prev.filter(f => f.id !== favoriteId));
      toast.success('Удалено из избранного');
    } catch (error) {
      toast.error('Ошибка удаления');
    }
  };

  // Add to cart (NEW: intent-based)
  const handleAddToCart = async (item, qty) => {
    setAdding(item.id);
    try {
      const userId = getUserId();
      
      // ВАЖНО: Используем anchor_supplier_item_id если есть (после GOLD миграции)
      // Это гарантирует что добавится именно выбранный товар без замены
      const anchorId = item.anchor_supplier_item_id || item.best_supplier_id;
      const referenceId = item.reference_id || item.id;
      
      console.log('Adding to cart (intent):', { 
        referenceId, 
        anchorId,
        product_name: item.product_name, 
        qty 
      });
      
      // Если есть anchor_supplier_item_id - используем его напрямую
      const payload = anchorId ? {
        supplier_item_id: anchorId,
        qty: qty,
        user_id: userId
      } : {
        reference_id: referenceId,
        qty: qty,
        user_id: userId
      };
      
      const response = await axios.post(`${API}/v12/cart/intent`, payload, {
        headers: getHeaders()
      });

      if (response.data.status === 'ok') {
        // Помечаем что добавлено в корзину
        const intentData = response.data.intent || {};
        const addedItemId = intentData.supplier_item_id || referenceId;
        setCartItems(prev => new Set([...prev, addedItemId]));
        setCartCount(prev => prev + 1);
        toast.success('✓ Добавлено в корзину');
        return true; // Success
      } else {
        toast.error(response.data.message || 'Ошибка добавления');
        throw new Error(response.data.message || 'Error');
      }
    } catch (error) {
      console.error('Add to cart error:', error);
      const errorMessage = error.response?.data?.detail || 'Ошибка добавления в корзину';
      toast.error(errorMessage);
      throw error;
    } finally {
      setAdding(null);
    }
  };

  // Add all to cart
  const handleAddAllToCart = async () => {
    if (!favorites.length) return;
    if (!confirm(`Добавить ${favorites.length} товаров в корзину?`)) return;

    let added = 0;
    let errors = 0;

    for (const item of favorites) {
      try {
        const userId = getUserId();
        const referenceId = item.reference_id || item.id;
        
        if (!referenceId) {
          errors++;
          continue;
        }
        
        const response = await axios.post(`${API}/v12/cart/intent`, {
          reference_id: referenceId,
          qty: 1,
          user_id: userId
        }, {
          headers: getHeaders()
        });
        if (response.data.status === 'ok') added++;
        else errors++;
      } catch (error) {
        errors++;
      }
    }

    toast.success(`Добавлено: ${added}, ошибок: ${errors}`);
    navigate('/customer/cart');
  };

  // Filter favorites by search and category
  const filteredFavorites = favorites.filter(f => {
    const matchesSearch = !search || f.product_name?.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = !category || f.super_class?.startsWith(category);
    return matchesSearch && matchesCategory;
  });

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold">Избранное</h1>
          <p className="text-gray-600">
            {favorites.length} товаров
          </p>
        </div>
        
        <div className="flex gap-2 flex-wrap">
          <Button onClick={handleAddAllToCart} disabled={!favorites.length}>
            <ShoppingCart className="h-4 w-4 mr-2" />
            Все в корзину
          </Button>
          {cartCount > 0 && (
            <Button 
              onClick={() => navigate('/customer/cart')}
              className="bg-blue-600 hover:bg-blue-700"
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              Корзина ({cartCount})
            </Button>
          )}
        </div>
      </div>

      {/* Search and Category Filter */}
      <Card className="p-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Поиск в избранном..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Category filter */}
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="px-4 py-2 border rounded-md bg-white min-w-[180px]"
          >
            {categories.map(cat => (
              <option key={cat.value} value={cat.value}>{cat.label}</option>
            ))}
          </select>
        </div>
      </Card>

      {/* Empty state */}
      {filteredFavorites.length === 0 ? (
        <Card className="p-12 text-center">
          <Heart className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">Избранное пусто</p>
          <p className="text-sm text-gray-500 mb-4">Добавьте товары из каталога</p>
          <Button variant="outline" onClick={() => navigate('/customer/catalog')}>
            Перейти в каталог
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredFavorites.map(item => (
            <FavoriteItemCard
              key={item.id}
              item={item}
              onRemove={handleRemove}
              onAddToCart={handleAddToCart}
              adding={adding}
              isInCart={cartItems.has(item.anchor_supplier_item_id) || cartItems.has(item.reference_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default CustomerFavorites;
