import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Heart, Trash2, ShoppingCart, TrendingDown, Search, CheckCircle, AlertCircle, GripVertical } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Sortable Item Component
function SortableItem({ favorite, onRemove, onBrandCriticalChange, addToCart, isAdding }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: favorite.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // brandCritical: true means STRICT brand matching, false means ANY brand
  const brandCritical = favorite.brandMode === 'STRICT';

  return (
    <div ref={setNodeRef} style={style} className={isDragging ? 'z-50' : ''}>
      <Card className={`p-5 hover:shadow-lg transition-all relative ${
        isDragging ? 'shadow-2xl scale-105 cursor-grabbing' : 'hover:border-2 hover:border-blue-300'
      }`}>
        {/* Drag Handle */}
        <div
          {...attributes}
          {...listeners}
          className="absolute top-2 left-2 cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600 touch-none"
        >
          <GripVertical className="h-5 w-5" />
        </div>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRemove(favorite.id)}
          className="absolute top-2 right-2 text-red-500 hover:text-red-600 z-10"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
        
        {/* Main Product Name */}
        <div className="mb-4 ml-6">
          <h3 className="font-semibold text-lg mb-1 pr-8">
            {favorite.productName}
          </h3>
          <p className="text-sm text-gray-600">Артикул: {favorite.productCode || 'Н/Д'}</p>
        </div>

        {/* Brand Critical Toggle - only for branded products */}
        {favorite.isBranded && (
          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <label htmlFor={`brand-${favorite.id}`} className="text-sm font-medium text-gray-700">
                ☑ Бренд критичен
              </label>
              <Switch
                id={`brand-${favorite.id}`}
                checked={brandCritical}
                onCheckedChange={(checked) => onBrandCriticalChange(favorite.id, checked)}
              />
            </div>
            <p className="text-xs text-gray-500">
              {brandCritical 
                ? `Только ${favorite.brand || 'этот'} бренд, поставщик может меняться` 
                : 'Допускаются аналоги — выбор по максимальному совпадению + минимальной цене'}
            </p>
          </div>
        )}

        {/* Add to cart button */}
        <div className="pt-2">
          <Button
            onClick={() => addToCart(favorite)}
            className="w-full"
            variant="default"
            disabled={isAdding === favorite.id}
          >
            {isAdding === favorite.id ? (
              <>
                <span className="animate-spin mr-2">⏳</span>
                Поиск лучшей цены...
              </>
            ) : (
              <>
                <ShoppingCart className="h-4 w-4 mr-2" />
                Добавить в корзину
              </>
            )}
          </Button>
        </div>
      </Card>
    </div>
  );
}

export const CustomerFavorites = () => {
  const [favorites, setFavorites] = useState([]);
  const [filteredFavorites, setFilteredFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [addingToCart, setAddingToCart] = useState(null); // Track which item is being added
  const [draggedItem, setDraggedItem] = useState(null);

  useEffect(() => {
    fetchFavorites();
    fetchCompanyInfo();
  }, []);

  useEffect(() => {
    // Filter favorites when search term changes
    if (searchTerm.trim()) {
      const filtered = favorites.filter(f =>
        f.productName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (f.productCode && f.productCode.toLowerCase().includes(searchTerm.toLowerCase()))
      );
      setFilteredFavorites(filtered);
    } else {
      setFilteredFavorites(favorites);
    }
  }, [searchTerm, favorites]);

  const fetchCompanyInfo = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/companies/my`, { headers });
      setCompany(response.data);
      if (response.data.deliveryAddresses?.length === 1) {
        setSelectedAddress(response.data.deliveryAddresses[0]);
      }
    } catch (error) {
      console.error('Failed to fetch company:', error);
    }
  };

  const fetchFavorites = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/favorites`, { headers });  // Simple endpoint, no matching
      setFavorites(response.data);
      setFilteredFavorites(response.data);
    } catch (error) {
      console.error('Failed to fetch favorites:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveFavorite = async (favoriteId) => {
    if (!confirm('Удалить из избранного?')) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.delete(`${API}/favorites/${favoriteId}`, { headers });
      fetchFavorites();
    } catch (error) {
      console.error('Failed to remove favorite:', error);
    }
  };

  // NEW: Handler for brand critical toggle (inverted logic from old brandMode)
  const onBrandCriticalChange = async (favoriteId, brandCritical) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      // brandCritical=true means STRICT, brandCritical=false means ANY
      const brandMode = brandCritical ? 'STRICT' : 'ANY';
      await axios.put(`${API}/favorites/${favoriteId}/brand-mode`, { brandMode }, { headers });
      fetchFavorites();
    } catch (error) {
      console.error('Failed to update brand mode:', error);
    }
  };

  // NEW: Automatic best price search when adding to cart
  const addToCart = async (favorite) => {
    // Check if already in cart
    const existingCart = JSON.parse(localStorage.getItem('catalogCart') || '[]');
    const alreadyInCart = existingCart.some(item => item.favoriteId === favorite.id);
    
    if (alreadyInCart) {
      alert('Этот товар уже в корзине');
      return;
    }

    setAddingToCart(favorite.id);

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};

      // Call backend to automatically find best price
      const response = await axios.post(`${API}/cart/resolve-favorite`, {
        productId: favorite.productId,
        productName: favorite.productName,
        brandCritical: favorite.brandMode === 'STRICT',  // NEW: use brandCritical
        isBranded: favorite.isBranded || false,
        brand: favorite.brand || null
      }, { headers });

      // Create cart item with ALREADY RESOLVED price and supplier
      const cartItem = {
        cartId: `fav_${favorite.id}_${Date.now()}`,
        source: 'favorites',
        favoriteId: favorite.id,
        productId: response.data.productId || favorite.productId,
        productName: response.data.productName,  // Use resolved product name
        quantity: 1,
        unit: favorite.unit,
        price: response.data.price,  // Already have price!
        supplier: response.data.supplier,  // Already have supplier!
        supplierId: response.data.supplierId,
        resolved: true,  // Mark as already resolved
        brandCritical: favorite.brandMode === 'STRICT'
      };

      // Add to cart
      existingCart.push(cartItem);
      localStorage.setItem('catalogCart', JSON.stringify(existingCart));
      
      alert(`✓ Добавлено: ${response.data.productName}\nЦена: ${response.data.price.toLocaleString('ru-RU')} ₽\nПоставщик: ${response.data.supplier}`);
    } catch (error) {
      console.error('Failed to resolve best price:', error);
      alert('Ошибка при поиске лучшей цены. Попробуйте еще раз.');
    } finally {
      setAddingToCart(null);
    }
  };

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = async (event) => {
    const { active, over } = event;
    
    if (!over || active.id === over.id) return;

    const oldIndex = filteredFavorites.findIndex(f => f.id === active.id);
    const newIndex = filteredFavorites.findIndex(f => f.id === over.id);
    
    // Reorder locally for immediate feedback
    const reordered = arrayMove(filteredFavorites, oldIndex, newIndex);
    setFilteredFavorites(reordered);

    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      // Send new order to backend
      const orderMap = reordered.map((fav, index) => ({
        id: fav.id,
        displayOrder: index
      }));
      
      await axios.post(`${API}/favorites/reorder`, { favorites: orderMap }, { headers });
      
      // Refresh from server
      fetchFavorites();
    } catch (error) {
      console.error('Failed to reorder:', error);
      // Revert on error
      fetchFavorites();
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Избранное</h2>
          <p className="text-base text-muted-foreground">
            Быстрый заказ часто используемых товаров • При добавлении автоматически ищется лучшая цена
          </p>
        </div>
      </div>

      {/* Search */}
      {favorites.length > 0 && (
        <div className="mb-6">
          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Поиск по названию или артикулу..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          {searchTerm && (
            <p className="text-sm text-muted-foreground mt-2">
              Найдено: {filteredFavorites.length} из {favorites.length}
            </p>
          )}
        </div>
      )}

      {filteredFavorites.length === 0 && searchTerm ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">Товары не найдены</p>
        </Card>
      ) : favorites.length === 0 ? (
        <Card className="p-12 text-center">
          <Heart className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">У вас пока нет избранных товаров</p>
          <p className="text-sm text-gray-500">Добавляйте товары в избранное из каталога для быстрого заказа</p>
        </Card>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={filteredFavorites.map(f => f.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredFavorites.map((favorite) => (
                <SortableItem
                  key={favorite.id}
                  favorite={favorite}
                  onRemove={handleRemoveFavorite}
                  onBrandCriticalChange={onBrandCriticalChange}
                  addToCart={addToCart}
                  isAdding={addingToCart}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Create Order Modal */}
    </div>
  );
};
