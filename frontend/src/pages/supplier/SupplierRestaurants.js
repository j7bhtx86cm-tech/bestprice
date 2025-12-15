import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Building2, Ban, CheckCircle, Package } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const SupplierRestaurants = () => {
  const [restaurants, setRestaurants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [selectedRestaurant, setSelectedRestaurant] = useState(null);
  const [showReasonModal, setShowReasonModal] = useState(false);
  const [unavailabilityReason, setUnavailabilityReason] = useState('');

  useEffect(() => {
    fetchRestaurants();
  }, []);

  const fetchRestaurants = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/supplier/restaurants`, { headers });
      setRestaurants(response.data);
    } catch (error) {
      console.error('Failed to fetch restaurants:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDisableOrders = (restaurant) => {
    setSelectedRestaurant(restaurant);
    setUnavailabilityReason('');
    setShowReasonModal(true);
  };

  const handleEnableOrders = async (restaurantId) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      await axios.put(
        `${API}/supplier/restaurants/${restaurantId}/availability`,
        {
          ordersEnabled: true,
          unavailabilityReason: null
        },
        { headers }
      );
      
      setMessage('success|Заказы от ресторана снова доступны');
      setTimeout(() => setMessage(''), 3000);
      fetchRestaurants();
    } catch (error) {
      console.error('Failed to enable orders:', error);
      setMessage('error|Ошибка обновления');
      setTimeout(() => setMessage(''), 3000);
    }
  };

  const handleSubmitReason = async () => {
    if (!unavailabilityReason.trim()) {
      alert('Пожалуйста, укажите причину');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      await axios.put(
        `${API}/supplier/restaurants/${selectedRestaurant.id}/availability`,
        {
          ordersEnabled: false,
          unavailabilityReason: unavailabilityReason
        },
        { headers }
      );
      
      setShowReasonModal(false);
      setSelectedRestaurant(null);
      setUnavailabilityReason('');
      setMessage('success|Заказы от ресторана отключены');
      setTimeout(() => setMessage(''), 3000);
      fetchRestaurants();
    } catch (error) {
      console.error('Failed to disable orders:', error);
      setMessage('error|Ошибка обновления');
      setTimeout(() => setMessage(''), 3000);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  const [messageType, messageText] = message.split('|');

  return (
    <div>
      <h2 className="text-4xl font-bold mb-2">Мои рестораны</h2>
      <p className="text-base text-muted-foreground mb-6">
        Управление доступностью заказов для каждого ресторана
      </p>

      {messageType === 'success' && (
        <Alert className="mb-6 bg-green-50 border-green-200">
          <AlertDescription className="text-green-800">
            ✓ {messageText}
          </AlertDescription>
        </Alert>
      )}
      
      {messageType === 'error' && (
        <Alert className="mb-6 bg-red-50 border-red-200">
          <AlertDescription className="text-red-800">
            ✗ {messageText}
          </AlertDescription>
        </Alert>
      )}

      {restaurants.length === 0 ? (
        <Card className="p-12 text-center">
          <Building2 className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600">Пока нет ресторанов, сделавших заказы</p>
        </Card>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {restaurants.map((restaurant) => (
            <Card key={restaurant.id} className="p-6">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <Building2 className="w-6 h-6 text-blue-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-lg truncate">{restaurant.name}</h3>
                  {restaurant.inn && (
                    <p className="text-sm text-gray-600">ИНН: {restaurant.inn}</p>
                  )}
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between py-2 border-t">
                  <span className="text-sm text-gray-600">Заказов:</span>
                  <span className="font-medium">{restaurant.orderCount}</span>
                </div>

                <div className="flex items-center justify-between py-2">
                  <span className="text-sm text-gray-600">Статус заказов:</span>
                  {restaurant.ordersEnabled ? (
                    <Badge className="bg-green-100 text-green-800">
                      <CheckCircle className="h-3 w-3 mr-1 inline" />
                      Доступны
                    </Badge>
                  ) : (
                    <Badge className="bg-red-100 text-red-800">
                      <Ban className="h-3 w-3 mr-1 inline" />
                      Недоступны
                    </Badge>
                  )}
                </div>

                {!restaurant.ordersEnabled && restaurant.unavailabilityReason && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded">
                    <p className="text-xs text-red-800">
                      <strong>Причина:</strong> {restaurant.unavailabilityReason}
                    </p>
                  </div>
                )}

                <div className="pt-3 border-t">
                  {restaurant.ordersEnabled ? (
                    <Button
                      variant="outline"
                      className="w-full text-red-600 hover:text-red-700 hover:bg-red-50"
                      onClick={() => handleDisableOrders(restaurant)}
                    >
                      <Ban className="h-4 w-4 mr-2" />
                      Отключить заказы
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      className="w-full text-green-600 hover:text-green-700 hover:bg-green-50"
                      onClick={() => handleEnableOrders(restaurant.id)}
                    >
                      <CheckCircle className="h-4 w-4 mr-2" />
                      Включить заказы
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Reason Modal */}
      <Dialog open={showReasonModal} onOpenChange={setShowReasonModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Отключить заказы от ресторана</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <p className="text-sm text-gray-600 mb-4">
                Ресторан: <strong>{selectedRestaurant?.name}</strong>
              </p>
              <label className="text-sm font-medium mb-2 block">
                Укажите причину отключения заказов <span className="text-red-500">*</span>
              </label>
              <textarea
                value={unavailabilityReason}
                onChange={(e) => setUnavailabilityReason(e.target.value)}
                placeholder="Например: Временная приостановка поставок, технические причины..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[100px]"
                required
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => {
                  setShowReasonModal(false);
                  setSelectedRestaurant(null);
                  setUnavailabilityReason('');
                }}
              >
                Отмена
              </Button>
              <Button
                className="flex-1 bg-red-600 hover:bg-red-700"
                onClick={handleSubmitReason}
                disabled={!unavailabilityReason.trim()}
              >
                Отключить заказы
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
