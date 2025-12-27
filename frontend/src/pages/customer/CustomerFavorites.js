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
function SortableItem({ favorite, onRemove, onModeChange }) {
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
            {favorite.mode === 'cheapest' && favorite.foundProduct && favorite.hasCheaperMatch
              ? favorite.foundProduct.name
              : favorite.productName}
          </h3>
          {favorite.mode === 'cheapest' && favorite.foundProduct && favorite.hasCheaperMatch && (
            <p className="text-xs text-gray-500 mb-1">
              Оригинал: {favorite.productName}
            </p>
          )}
          <p className="text-sm text-gray-600">Артикул: {favorite.productCode || 'Н/Д'}</p>
        </div>

        {/* Mode Toggle Switch */}
        <div className="mb-4 p-3 bg-gray-50 rounded-lg space-y-3">
          {/* Search for best price toggle */}
          <div className="flex items-center justify-between">
            <label htmlFor={`mode-${favorite.id}`} className="text-sm font-medium text-gray-700">
              Искать лучшую цену
            </label>
            <Switch
              id={`mode-${favorite.id}`}
              checked={favorite.mode === 'cheapest'}
              onCheckedChange={(checked) => onModeChange(favorite.id, checked ? 'cheapest' : 'exact')}
            />
          </div>
          
          {/* NEW: Strict brand toggle - only show if mode is cheapest */}
          {favorite.mode === 'cheapest' && (
            <div className="flex items-center justify-between pt-2 border-t border-gray-200">
              <label htmlFor={`brand-${favorite.id}`} className="text-sm font-medium text-gray-700">
                Сохранить производителя
              </label>
              <Switch
                id={`brand-${favorite.id}`}
                checked={favorite.strictBrand || false}
                onCheckedChange={(checked) => onBrandStrictChange(favorite.id, checked)}
              />
            </div>
          )}
          
          <p className="text-xs text-gray-500">
            {favorite.mode === 'cheapest' 
              ? (favorite.strictBrand 
                  ? 'Поиск только у текущего производителя' 
                  : 'Система ищет дешевле среди похожих товаров')
              : 'Всегда этот продукт от выбранного поставщика'}
          </p>
        </div>

        {/* Found Product Block */}
        {favorite.mode === 'cheapest' && favorite.foundProduct && favorite.hasCheaperMatch && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-start gap-2">
              <CheckCircle className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
              <div className="flex-1 text-sm">
                <p className="font-medium text-green-900 mb-1">Найден дешевле!</p>
                <p className="text-gray-700">{favorite.foundProduct.name}</p>
                {favorite.foundProduct.brand && (
                  <p className="text-xs text-gray-600">Бренд: {favorite.foundProduct.brand}</p>
                )}
                {favorite.foundProduct.pack_weight_kg && (
                  <p className="text-xs text-gray-600">Фасовка: {favorite.foundProduct.pack_weight_kg} кг</p>
                )}
                {favorite.foundProduct.pack_volume_l && (
                  <p className="text-xs text-gray-600">Объем: {favorite.foundProduct.pack_volume_l} л</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Fallback Message */}
        {favorite.mode === 'cheapest' && favorite.fallbackMessage && (
          <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-blue-600 mt-0.5" />
              <p className="text-sm text-blue-800">{favorite.fallbackMessage}</p>
            </div>
          </div>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">
              {favorite.mode === 'cheapest' ? 'Лучшая цена:' : 'Цена:'}
            </span>
            <span className="font-bold text-green-600 text-lg">
              {favorite.bestPrice?.toLocaleString('ru-RU')} ₽
            </span>
          </div>
          
          {favorite.bestSupplier && (
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <TrendingDown className="h-4 w-4 text-green-600" />
              <span>{favorite.bestSupplier}</span>
            </div>
          )}
          
          {/* NEW: Add to cart button */}
          <div className="pt-2">
            <Button
              onClick={() => addToCart(favorite)}
              className="w-full"
              variant="outline"
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              Добавить в корзину
            </Button>
          </div>
          
          <div className="text-xs text-gray-500">
            Ед. изм: {favorite.unit}
          </div>

          {favorite.mode === 'cheapest' && favorite.matchCount > 1 && (
            <div className="pt-2 border-t">
              <p className="text-xs text-gray-500">
                Найдено {favorite.matchCount} похожих товаров
              </p>
            </div>
          )}
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
  const [orderSearchTerm, setOrderSearchTerm] = useState('');
  const [showOrderModal, setShowOrderModal] = useState(false);
  const [orderItems, setOrderItems] = useState([]);
  const [filteredOrderItems, setFilteredOrderItems] = useState([]);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
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

  useEffect(() => {
    // Filter order items when search term changes
    if (orderSearchTerm.trim()) {
      const filtered = orderItems.filter(item =>
        item.productName.toLowerCase().includes(orderSearchTerm.toLowerCase())
      );
      setFilteredOrderItems(filtered);
    } else {
      setFilteredOrderItems(orderItems);
    }
  }, [orderSearchTerm, orderItems]);

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
      const response = await axios.get(`${API}/favorites/v2`, { headers });
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

  const onBrandStrictChange = async (favoriteId, strictBrand) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.put(`${API}/favorites/${favoriteId}/brand-strict`, { strictBrand }, { headers });
      fetchFavorites(); // Reload to get updated matches
    } catch (error) {
      console.error('Failed to update brand strictness:', error);
    }
  };

  const addToCart = (favorite) => {
    const cartItem = {
      cartId: `fav_${favorite.id}_${Date.now()}`,
      favoriteId: favorite.id,
      productName: favorite.productName,
      quantity: 1,
      price: favorite.bestPrice || favorite.originalPrice || 0,
      unit: favorite.unit,
      bestSupplier: favorite.bestSupplier
    };

    // Get existing cart
    const existingCart = JSON.parse(localStorage.getItem('favoriteCart') || '[]');
    
    // Check if already in cart
    const alreadyInCart = existingCart.some(item => item.favoriteId === favorite.id);
    
    if (alreadyInCart) {
      alert('Этот товар уже в корзине');
      return;
    }

    // Add to cart
    existingCart.push(cartItem);
    localStorage.setItem('favoriteCart', JSON.stringify(existingCart));
    
    alert('Товар добавлен в корзину!');
  };

  const handleModeChange = async (favoriteId, newMode) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.put(`${API}/favorites/${favoriteId}/mode`, { mode: newMode }, { headers });
      fetchFavorites(); // Refresh to show updated mode
    } catch (error) {
      console.error('Failed to update mode:', error);
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

  const handleCreateOrder = () => {
    // Try to load saved quantities from localStorage
    const savedQuantities = localStorage.getItem('favoriteOrderQuantities');
    const quantitiesMap = savedQuantities ? JSON.parse(savedQuantities) : {};
    
    const items = favorites.map(f => ({
      favoriteId: f.id,
      productName: f.productName,
      quantity: quantitiesMap[f.id] || 1,  // Load saved quantity or default to 1
      bestPrice: f.bestPrice,
      unit: f.unit,
      bestSupplier: f.bestSupplier
    }));
    setOrderItems(items);
    setFilteredOrderItems(items);
    setOrderSearchTerm('');
    setShowOrderModal(true);
  };

  const updateQuantity = (favoriteId, value) => {
    const newValue = parseInt(value) || 1;  // Only integers, min 1
    const finalValue = Math.max(1, newValue);
    
    const newItems = [...orderItems];
    const idx = newItems.findIndex(i => i.favoriteId === favoriteId);
    if (idx !== -1) {
      newItems[idx].quantity = finalValue;
      setOrderItems(newItems);
      
      // Save to localStorage
      const quantitiesMap = {};
      newItems.forEach(item => {
        quantitiesMap[item.favoriteId] = item.quantity;
      });
      localStorage.setItem('favoriteOrderQuantities', JSON.stringify(quantitiesMap));
    }
  };

  const handleSubmitOrder = async () => {
    const itemsToOrder = orderItems.filter(item => item.quantity > 0);
    
    if (itemsToOrder.length === 0) {
      alert('Выберите товары');
      return;
    }

    try {
      // Instead of creating order, save to localStorage as cart
      const existingCart = JSON.parse(localStorage.getItem('favoriteCart') || '[]');
      
      // Add items to cart
      const newCartItems = itemsToOrder.map(item => ({
        cartId: `fav_${item.favoriteId}_${Date.now()}`,
        favoriteId: item.favoriteId,
        productName: item.productName,
        quantity: item.quantity,
        price: item.bestPrice,
        unit: item.unit,
        supplier: item.bestSupplier,
        addedAt: new Date().toISOString()
      }));
      
      const updatedCart = [...existingCart, ...newCartItems];
      localStorage.setItem('favoriteCart', JSON.stringify(updatedCart));
      
      // Clear saved quantities
      localStorage.removeItem('favoriteOrderQuantities');
      
      alert(`✓ ${itemsToOrder.length} товаров добавлено в корзину!`);
      setShowOrderModal(false);
      
      // Optional: Navigate to catalog or show cart
      // window.location.href = '/customer/catalog';
    } catch (error) {
      console.error('Failed to add to cart:', error);
      alert('Ошибка добавления в корзину');
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
            Быстрый заказ часто используемых товаров
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Global Best Price Toggle */}
          {favorites.length > 0 && (
            <div className="flex items-center gap-3 p-3 border rounded-lg bg-white">
              <div className="text-right">
                <p className="text-sm font-medium">Искать лучшую цену для всех</p>
                <p className="text-xs text-gray-500">Включить для всех товаров</p>
              </div>
              <Switch
                checked={favorites.every(f => f.mode === 'cheapest')}
                onCheckedChange={async (checked) => {
                  const mode = checked ? 'cheapest' : 'exact';
                  const token = localStorage.getItem('token');
                  const headers = token ? { Authorization: `Bearer ${token}` } : {};
                  
                  // Update all favorites
                  for (const fav of favorites) {
                    try {
                      await axios.put(`${API}/favorites/${fav.id}/mode`, { mode }, { headers });
                    } catch (err) {
                      console.error('Failed to update mode:', err);
                    }
                  }
                  
                  // Refresh
                  fetchFavorites();
                }}
              />
            </div>
          )}
          {favorites.length > 0 && (
            <Button onClick={handleCreateOrder}>
              <ShoppingCart className="h-4 w-4 mr-2" />
              В корзину
            </Button>
          )}
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
                  onModeChange={handleModeChange}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Create Order Modal */}
      <Dialog open={showOrderModal} onOpenChange={setShowOrderModal}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Заказ из избранного</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <p className="text-sm text-muted-foreground">
              Укажите количество для каждого товара. Система автоматически выберет лучшую цену.
            </p>
            
            {/* Search in Order Modal */}
            <div className="relative">
              <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Поиск товара..."
                value={orderSearchTerm}
                onChange={(e) => setOrderSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            {orderSearchTerm && (
              <p className="text-sm text-muted-foreground">
                Показано: {filteredOrderItems.length} из {orderItems.length}
              </p>
            )}
            
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {filteredOrderItems.map((item, idx) => {
                const originalIdx = orderItems.findIndex(i => i.favoriteId === item.favoriteId);
                return (
                  <div key={item.favoriteId} className="flex items-center gap-4 p-4 border rounded-lg">
                    <div className="flex-1">
                      <p className="font-medium">{item.productName}</p>
                      <p className="text-sm text-gray-600">
                        {item.bestPrice?.toLocaleString('ru-RU')} ₽ / {item.unit}
                        {item.bestSupplier && ` • ${item.bestSupplier}`}
                      </p>
                    </div>
                    <Input
                      type="number"
                      min="1"
                      step="1"
                      placeholder="1"
                      value={orderItems[originalIdx]?.quantity || 1}
                      onChange={(e) => updateQuantity(item.favoriteId, e.target.value)}
                      className="w-32"
                    />
                    <span className="text-sm text-gray-600 w-16">{item.unit}</span>
                  </div>
                );
              })}
            </div>

            <div className="flex gap-2 pt-4 border-t">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setShowOrderModal(false)}
              >
                Отмена
              </Button>
              <Button
                className="flex-1"
                onClick={handleSubmitOrder}
              >
                <ShoppingCart className="h-4 w-4 mr-2" />
                В корзину
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
