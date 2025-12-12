import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ChevronRight, Package } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const statusColors = {
  new: 'bg-blue-100 text-blue-800',
  confirmed: 'bg-green-100 text-green-800',
  declined: 'bg-red-100 text-red-800',
  partial: 'bg-yellow-100 text-yellow-800'
};

const statusLabels = {
  new: 'Новый',
  confirmed: 'Подтвержден',
  declined: 'Отклонен',
  partial: 'Частичный'
};

export const MobileOrders = () => {
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    fetchOrders();
  }, []);

  const fetchOrders = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      const response = await axios.get(`${API}/orders/my`, { headers });
      setOrders(response.data);
    } catch (error) {
      console.error('Failed to fetch orders:', error);
    } finally {
      setLoading(false);
    }
  };

  const getFilteredOrders = () => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

    switch (filter) {
      case 'today':
        return orders.filter(o => new Date(o.orderDate) >= today);
      case 'week':
        return orders.filter(o => new Date(o.orderDate) >= weekAgo);
      default:
        return orders;
    }
  };

  const filteredOrders = getFilteredOrders();

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b p-4">
        <div className="max-w-2xl mx-auto">
          <h1 className="text-xl font-bold mb-4">Мои заказы</h1>
          
          {/* Filters */}
          <div className="flex gap-2 overflow-x-auto">
            {[
              { key: 'all', label: 'Все' },
              { key: 'today', label: 'Сегодня' },
              { key: 'week', label: 'Неделя' }
            ].map(f => (
              <Button
                key={f.key}
                onClick={() => setFilter(f.key)}
                variant={filter === f.key ? 'default' : 'outline'}
                size="sm"
                className="whitespace-nowrap"
              >
                {f.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto p-4">
        {filteredOrders.length === 0 ? (
          <Card className="p-8 text-center">
            <Package className="h-12 w-12 mx-auto mb-4 text-gray-400" />
            <p className="text-gray-600">Заказов нет</p>
          </Card>
        ) : (
          <div className="space-y-3">
            {filteredOrders.map((order) => (
              <Card
                key={order.id}
                className="p-4 cursor-pointer hover:shadow-md transition-shadow"
                onClick={() => navigate(`/app/orders/${order.id}`)}
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <p className="font-medium">Заказ №{order.id.slice(0, 8)}</p>
                    <p className="text-sm text-gray-600">
                      {new Date(order.orderDate).toLocaleDateString('ru-RU')}
                      {' '}
                      {new Date(order.orderDate).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                  <Badge className={statusColors[order.status]}>
                    {statusLabels[order.status]}
                  </Badge>
                </div>
                
                <div className="flex items-center justify-between pt-2 border-t">
                  <div>
                    <p className="text-sm text-gray-600">Товаров: {order.orderDetails?.length || 0}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-bold">{order.amount.toFixed(2)} ₽</span>
                    <ChevronRight className="h-5 w-5 text-gray-400" />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        <div className="h-20"></div>
      </div>

      {/* Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t p-4">
        <Button
          onClick={() => navigate('/app/home')}
          variant="outline"
          className="w-full h-12"
        >
          Назад
        </Button>
      </div>
    </div>
  );
};
