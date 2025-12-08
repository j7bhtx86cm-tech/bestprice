import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Eye, TrendingDown, Award } from 'lucide-react';

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

export const CustomerOrders = () => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [suppliers, setSuppliers] = useState({});
  const [allProducts, setAllProducts] = useState([]);

  useEffect(() => {
    fetchOrdersAndSuppliers();
  }, []);

  const fetchOrdersAndSuppliers = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};

      // Fetch orders
      const ordersResponse = await axios.get(`${API}/orders/my`, { headers });
      setOrders(ordersResponse.data);

      // Fetch all suppliers
      const suppliersResponse = await axios.get(`${API}/suppliers`, { headers });
      const suppliersMap = {};
      suppliersResponse.data.forEach(supplier => {
        suppliersMap[supplier.id] = supplier;
      });
      setSuppliers(suppliersMap);

      // Fetch all products for price comparison
      const allProductsList = [];
      for (const supplier of suppliersResponse.data) {
        const priceListResponse = await axios.get(`${API}/suppliers/${supplier.id}/price-lists`, { headers });
        allProductsList.push(...priceListResponse.data.map(p => ({ ...p, supplierId: supplier.id })));
      }
      setAllProducts(allProductsList);
    } catch (error) {
      console.error('Failed to fetch orders:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchOrderDetails = async (orderId) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/orders/${orderId}`, { headers });
      setSelectedOrder(response.data);
    } catch (error) {
      console.error('Failed to fetch order details:', error);
    }
  };

  // Calculate savings by comparing ordered price to the average market price
  const calculateSavings = (order) => {
    if (!order || !order.orderDetails) return 0;

    let totalSavings = 0;

    order.orderDetails.forEach(item => {
      // Find all products with the same name and unit
      const similarProducts = allProducts.filter(p => 
        p.productName.toLowerCase() === item.productName.toLowerCase() && 
        p.unit.toLowerCase() === item.unit.toLowerCase()
      );

      if (similarProducts.length > 1) {
        // Calculate average price
        const avgPrice = similarProducts.reduce((sum, p) => sum + p.price, 0) / similarProducts.length;
        
        // Savings = (avg price - paid price) * quantity
        const itemSavings = (avgPrice - item.price) * item.quantity;
        
        if (itemSavings > 0) {
          totalSavings += itemSavings;
        }
      }
    });

    return totalSavings;
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-orders-page">
      <h2 className="text-2xl font-bold mb-6">История заказов</h2>

      {orders.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">У вас пока нет заказов</p>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Дата</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Поставщик</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Сумма</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Статус</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Действия</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm">
                      {new Date(order.orderDate).toLocaleDateString('ru-RU')}
                    </td>
                    <td className="px-4 py-3 text-sm font-medium">
                      {suppliers[order.supplierCompanyId]?.companyName || 'Загрузка...'}
                    </td>
                    <td className="px-4 py-3 text-sm font-medium">
                      {order.amount.toLocaleString('ru-RU')} ₽
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <Badge className={statusColors[order.status] || 'bg-gray-100 text-gray-800'}>
                        {statusLabels[order.status] || order.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => fetchOrderDetails(order.id)}
                        data-testid={`view-order-${order.id}`}
                      >
                        <Eye className="h-4 w-4 mr-2" />
                        Подробнее
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selectedOrder && (
        <Card className="p-6 mt-6">
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-xl font-semibold">Детали заказа</h3>
            <Button variant="ghost" size="sm" onClick={() => setSelectedOrder(null)}>Закрыть</Button>
          </div>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-600">Дата заказа</p>
                <p className="font-medium">{new Date(selectedOrder.orderDate).toLocaleDateString('ru-RU')}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Статус</p>
                <Badge className={statusColors[selectedOrder.status]}>
                  {statusLabels[selectedOrder.status]}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-gray-600">Поставщик</p>
                <p className="font-medium">{suppliers[selectedOrder.supplierCompanyId]?.companyName || 'Загрузка...'}</p>
              </div>
              {selectedOrder.deliveryAddress && (
                <div>
                  <p className="text-sm text-gray-600">Адрес доставки</p>
                  <p className="font-medium">{selectedOrder.deliveryAddress.address}</p>
                  {selectedOrder.deliveryAddress.phone && (
                    <p className="text-sm text-gray-600 mt-1">Тел: {selectedOrder.deliveryAddress.phone}</p>
                  )}
                  {selectedOrder.deliveryAddress.additionalPhone && (
                    <p className="text-sm text-gray-600">Доп. тел: {selectedOrder.deliveryAddress.additionalPhone}</p>
                  )}
                </div>
              )}
            </div>
            
            {/* Savings Banner */}
            {calculateSavings(selectedOrder) > 0 && (
              <Card className="p-4 bg-green-50 border-green-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="rounded-full bg-green-100 p-2">
                      <TrendingDown className="h-5 w-5 text-green-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-green-900">Ваша экономия</p>
                      <p className="text-xs text-green-700">По сравнению со средней рыночной ценой</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold text-green-600">
                      {calculateSavings(selectedOrder).toFixed(2)} ₽
                    </p>
                  </div>
                </div>
              </Card>
            )}
            
            <div>
              <p className="text-sm text-gray-600 mb-2">Состав заказа</p>
              <div className="bg-gray-50 rounded-lg p-4">
                {selectedOrder.orderDetails.map((item, index) => (
                  <div key={index} className="flex justify-between items-center py-2 border-b last:border-b-0">
                    <div>
                      <p className="font-medium">{item.productName}</p>
                      <p className="text-sm text-gray-600">{item.article}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">{item.quantity} {item.unit}</p>
                      <p className="text-sm text-gray-600">{item.price} ₽/{item.unit}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="pt-4 border-t">
              <div className="flex justify-between items-center">
                <p className="text-lg font-semibold">Итого:</p>
                <p className="text-2xl font-bold">{selectedOrder.amount.toLocaleString('ru-RU')} ₽</p>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};