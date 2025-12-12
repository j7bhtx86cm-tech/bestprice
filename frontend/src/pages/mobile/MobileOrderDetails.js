import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Package } from 'lucide-react';

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

export const MobileOrderDetails = () => {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [supplier, setSupplier] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOrderDetails();
  }, [orderId]);

  const fetchOrderDetails = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      const response = await axios.get(`${API}/orders/${orderId}`, { headers });
      setOrder(response.data);
      
      // Get supplier info
      if (response.data.supplierCompanyId) {
        const supplierResponse = await axios.get(
          `${API}/companies/${response.data.supplierCompanyId}`,
          { headers }
        );
        setSupplier(supplierResponse.data);
      }
    } catch (error) {
      console.error('Failed to fetch order:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  if (!order) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="p-8 text-center">
          <Package className="h-12 w-12 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-4">Заказ не найден</p>
          <Button onClick={() => navigate('/app/orders')}>Назад к заказам</Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-white border-b p-4 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto">
          <Button variant="ghost" size="sm" onClick={() => navigate('/app/orders')} className="mb-2">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Назад
          </Button>
          <h1 className="text-xl font-bold">Заказ №{order.id.slice(0, 8)}</h1>
        </div>
      </div>

      <div className="max-w-2xl mx-auto p-4 space-y-4">
        {/* Order Info */}
        <Card className="p-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-600">Дата и время</p>
              <p className="font-medium">
                {new Date(order.orderDate).toLocaleDateString('ru-RU')}
              </p>
              <p className="text-sm">
                {new Date(order.orderDate).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Статус</p>
              <Badge className={statusColors[order.status]}>
                {statusLabels[order.status]}
              </Badge>
            </div>
          </div>
          
          {supplier && (
            <div className="mt-4 pt-4 border-t">
              <p className="text-sm text-gray-600">Поставщик</p>
              <p className="font-medium">{supplier.companyName}</p>
            </div>
          )}
        </Card>

        {/* Items */}
        <Card className="p-4">
          <h3 className="font-semibold mb-3">Состав заказа</h3>
          <div className="space-y-3">
            {order.orderDetails.map((item, index) => (
              <div key={index} className="pb-3 border-b last:border-b-0">
                <p className="font-medium mb-1">{item.productName}</p>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">{item.quantity} {item.unit}</span>
                  <span className="font-medium">{item.price} ₽/{item.unit}</span>
                </div>
                <div className="flex justify-between text-sm mt-1">
                  <span className="text-gray-600">Артикул: {item.article}</span>
                  <span className="font-semibold text-blue-600">
                    {(item.price * item.quantity).toFixed(2)} ₽
                  </span>
                </div>
              </div>
            ))}
          </div>
          
          <div className="mt-4 pt-4 border-t flex justify-between items-center">
            <span className="font-semibold">Итого:</span>
            <span className="text-2xl font-bold">{order.amount.toFixed(2)} ₽</span>
          </div>
        </Card>
      </div>
    </div>
  );
};
