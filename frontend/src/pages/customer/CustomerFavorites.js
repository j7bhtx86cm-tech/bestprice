import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Heart, Trash2, ShoppingCart, TrendingDown, Search, CheckCircle, AlertCircle } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

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
      const response = await axios.get(`${API}/favorites`, { headers });
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

  const handleCreateOrder = () => {
    const items = favorites.map(f => ({
      favoriteId: f.id,
      productName: f.productName,
      quantity: 1,  // Default to 1 (minimum), not 0
      bestPrice: f.bestPrice,
      unit: f.unit,
      bestSupplier: f.bestSupplier
    }));
    setOrderItems(items);
    setFilteredOrderItems(items);
    setOrderSearchTerm('');
    setShowOrderModal(true);
  };

  const handleSubmitOrder = async () => {
    const itemsToOrder = orderItems.filter(item => item.quantity > 0);
    
    if (itemsToOrder.length === 0) {
      alert('Добавьте товары в заказ');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      await axios.post(
        `${API}/favorites/order`,
        {
          items: itemsToOrder.map(item => ({
            favoriteId: item.favoriteId,
            quantity: item.quantity
          })),
          deliveryAddressId: selectedAddress?.id
        },
        { headers }
      );
      
      alert('Заказ успешно создан!');
      setShowOrderModal(false);
    } catch (error) {
      console.error('Failed to create order:', error);
      alert('Ошибка создания заказа');
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
        {favorites.length > 0 && (
          <Button onClick={handleCreateOrder}>
            <ShoppingCart className="h-4 w-4 mr-2" />
            Создать заказ
          </Button>
        )}
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
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredFavorites.map((favorite) => (
            <Card key={favorite.id} className="p-5 hover:shadow-lg transition-shadow relative">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleRemoveFavorite(favorite.id)}
                className="absolute top-2 right-2 text-red-500 hover:text-red-600"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              
              {/* Main Product Name - Show found product if cheaper match */}
              <div className="mb-4">
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
              <div className="mb-4 p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor={`mode-${favorite.id}`} className="text-sm font-medium text-gray-700">
                    Искать лучшую цену
                  </label>
                  <Switch
                    id={`mode-${favorite.id}`}
                    checked={favorite.mode === 'cheapest'}
                    onCheckedChange={(checked) => handleModeChange(favorite.id, checked ? 'cheapest' : 'exact')}
                  />
                </div>
                <p className="text-xs text-gray-500">
                  {favorite.mode === 'cheapest' 
                    ? 'Система ищет дешевле среди похожих товаров' 
                    : 'Всегда этот продукт от выбранного поставщика'}
                </p>
              </div>

              {/* Found Product Block (when Best Price ON) */}
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
          ))}
        </div>
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
                      step="0.1"
                      placeholder="1"
                      value={orderItems[originalIdx]?.quantity || 1}
                      onChange={(e) => {
                        const newItems = [...orderItems];
                        const value = parseFloat(e.target.value);
                        newItems[originalIdx].quantity = value >= 1 ? value : 1;
                        setOrderItems(newItems);
                      }}
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
                Отправить заказ
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
