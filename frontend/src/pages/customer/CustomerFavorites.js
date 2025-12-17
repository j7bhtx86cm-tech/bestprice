import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Heart, Trash2, ShoppingCart, TrendingDown } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerFavorites = () => {
  const [favorites, setFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showOrderModal, setShowOrderModal] = useState(false);
  const [orderItems, setOrderItems] = useState([]);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);

  useEffect(() => {
    fetchFavorites();
    fetchCompanyInfo();
  }, []);

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

  const handleCreateOrder = () => {
    const items = favorites.map(f => ({
      favoriteId: f.id,
      productName: f.productName,
      quantity: 0,
      bestPrice: f.bestPrice,
      unit: f.unit,
      bestSupplier: f.bestSupplier
    }));
    setOrderItems(items);
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

      {favorites.length === 0 ? (
        <Card className="p-12 text-center">
          <Heart className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">У вас пока нет избранных товаров</p>
          <p className="text-sm text-gray-500">Добавляйте товары в избранное из каталога для быстрого заказа</p>
        </Card>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {favorites.map((favorite) => (
            <Card key={favorite.id} className="p-5 hover:shadow-lg transition-shadow relative">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleRemoveFavorite(favorite.id)}
                className="absolute top-2 right-2 text-red-500 hover:text-red-600"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              
              <div className="mb-3">
                <h3 className="font-semibold text-lg mb-1 pr-8">{favorite.productName}</h3>
                <p className="text-sm text-gray-600">Артикул: {favorite.productCode || 'Н/Д'}</p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Лучшая цена:</span>
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
              </div>

              {favorite.suppliers && favorite.suppliers.length > 1 && (
                <div className="mt-3 pt-3 border-t">
                  <p className="text-xs text-gray-500">
                    Доступно у {favorite.suppliers.length} поставщиков
                  </p>
                </div>
              )}
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
            
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {orderItems.map((item, idx) => (
                <div key={idx} className="flex items-center gap-4 p-4 border rounded-lg">
                  <div className="flex-1">
                    <p className="font-medium">{item.productName}</p>
                    <p className="text-sm text-gray-600">
                      {item.bestPrice?.toLocaleString('ru-RU')} ₽ / {item.unit}
                      {item.bestSupplier && ` • ${item.bestSupplier}`}
                    </p>
                  </div>
                  <Input
                    type="number"
                    min="0"
                    step="0.1"
                    placeholder="0"
                    value={item.quantity || ''}
                    onChange={(e) => {
                      const newItems = [...orderItems];
                      newItems[idx].quantity = parseFloat(e.target.value) || 0;
                      setOrderItems(newItems);
                    }}
                    className="w-32"
                  />
                  <span className="text-sm text-gray-600 w-16">{item.unit}</span>
                </div>
              ))}
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
