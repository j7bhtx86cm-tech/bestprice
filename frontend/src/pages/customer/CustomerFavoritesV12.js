import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import {
  Heart, Trash2, ShoppingCart, Search, Package,
  RefreshCw, TrendingDown, AlertCircle, Shuffle, Loader2
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Favorite Item Card
const FavoriteItemCard = ({ item, onRemove, onAddToCart, adding }) => {
  const [qty, setQty] = useState(1);

  return (
    <Card className="p-4 hover:shadow-lg transition-all">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <Badge variant="secondary" className="text-xs">
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
        <span className="text-sm text-gray-500">{item.unit_type === 'WEIGHT' ? 'кг' : item.unit_type === 'VOLUME' ? 'л' : 'шт'}</span>
      </div>

      {/* Add to cart */}
      <Button
        className="w-full"
        onClick={() => onAddToCart(item, qty)}
        disabled={adding === item.id}
      >
        {adding === item.id ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Добавление...
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
export const CustomerFavoritesV12 = () => {
  const navigate = useNavigate();
  const [favorites, setFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [adding, setAdding] = useState(null);
  const [seeding, setSeeding] = useState(false);

  // Get user ID
  const getUserId = () => {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    return user.id || 'test_user_v12';
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
      const response = await axios.get(`${API}/v12/favorites?user_id=${userId}&limit=500`, {
        headers: getHeaders()
      });
      setFavorites(response.data.items || []);
    } catch (error) {
      console.error('Failed to fetch favorites:', error);
      toast.error('Ошибка загрузки избранного');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFavorites();
  }, [fetchFavorites]);

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

  // Add to cart
  const handleAddToCart = async (item, qty) => {
    setAdding(item.id);
    try {
      const userId = getUserId();
      const response = await axios.post(`${API}/v12/cart/add`, {
        reference_id: item.reference_id,
        qty: qty,
        user_id: userId
      }, {
        headers: getHeaders()
      });

      if (response.data.status === 'ok') {
        const msg = response.data.substituted 
          ? `Добавлено в корзину (заменено, экономия ${response.data.savings?.toLocaleString('ru-RU')} ₽)`
          : 'Добавлено в корзину';
        toast.success(msg);
      } else {
        toast.error(response.data.message || 'Ошибка добавления');
      }
    } catch (error) {
      toast.error('Ошибка добавления в корзину');
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
        const response = await axios.post(`${API}/v12/cart/add`, {
          reference_id: item.reference_id,
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
    navigate('/customer/cart-v12');
  };

  // Seed random favorites
  const handleSeedFavorites = async () => {
    if (!confirm('Добавить 100 случайных карточек в избранное?')) return;
    
    setSeeding(true);
    try {
      const userId = getUserId();
      const response = await axios.post(`${API}/v12/admin/test/favorites/random`, {
        user_id: userId,
        count: 100
      }, {
        headers: getHeaders()
      });
      
      toast.success(`Добавлено ${response.data.added_count} карточек`);
      fetchFavorites();
    } catch (error) {
      toast.error('Ошибка добавления');
    } finally {
      setSeeding(false);
    }
  };

  // Filter favorites
  const filteredFavorites = favorites.filter(f =>
    !search || f.product_name?.toLowerCase().includes(search.toLowerCase())
  );

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
          <h1 className="text-3xl font-bold">Избранное v12</h1>
          <p className="text-gray-600">
            {favorites.length} товаров
          </p>
        </div>
        
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleSeedFavorites} disabled={seeding}>
            {seeding ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Добавление...
              </>
            ) : (
              <>
                <Shuffle className="h-4 w-4 mr-2" />
                +100 случайных
              </>
            )}
          </Button>
          <Button variant="outline" onClick={fetchFavorites}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Обновить
          </Button>
          <Button onClick={handleAddAllToCart} disabled={!favorites.length}>
            <ShoppingCart className="h-4 w-4 mr-2" />
            Все в корзину
          </Button>
        </div>
      </div>

      {/* Search */}
      <Card className="p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input
            placeholder="Поиск в избранном..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
      </Card>

      {/* Empty state */}
      {filteredFavorites.length === 0 ? (
        <Card className="p-12 text-center">
          <Heart className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">Избранное пусто</p>
          <p className="text-sm text-gray-500 mb-4">Добавьте товары из каталога или нажмите "+100 случайных"</p>
          <div className="flex gap-2 justify-center">
            <Button variant="outline" onClick={() => navigate('/customer/catalog-v12')}>
              Перейти в каталог
            </Button>
            <Button onClick={handleSeedFavorites} disabled={seeding}>
              <Shuffle className="h-4 w-4 mr-2" />
              +100 случайных
            </Button>
          </div>
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
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default CustomerFavoritesV12;
