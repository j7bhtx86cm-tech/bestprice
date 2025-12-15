import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Eye, Package, MapPin, Phone } from 'lucide-react';

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

export const SupplierOrders = () => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [customers, setCustomers] = useState({});

  useEffect(() => {
    fetchOrders();
    fetchCustomers();
  }, []);

  const fetchOrders = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/orders/my`, { headers });
      setOrders(response.data);
    } catch (error) {
      console.error('Failed to fetch orders:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCustomers = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      // Get all customer companies
      const response = await axios.get(`${API}/suppliers`, { headers });
      // Note: We'd need a customers endpoint, but for now use what we have
    } catch (error) {
      console.error('Failed to fetch customers:', error);
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

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="supplier-orders-page">
      <h2 className="text-4xl font-bold mb-2">Полученные заказы</h2>
      <p className="text-base text-muted-foreground mb-6">Управление заказами от ресторанов</p>

      {orders.length === 0 ? (
        <Card className="p-8 text-center">
          <Package className="h-12 w-12 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600">Пока нет заказов</p>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Дата и время</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Клиент</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Товаров</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Сумма</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Статус</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Действия</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {orders.map((order) => (
                  <React.Fragment key={order.id}>
                    <tr className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm">
                        {new Date(order.orderDate).toLocaleDateString('ru-RU')}
                        {' '}
                        <span className="text-gray-500">
                          {new Date(order.orderDate).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm font-medium">
                        {customers[order.customerCompanyId]?.companyName || 'Клиент'}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {order.orderDetails?.length || 0} позиций
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
                          onClick={() => {
                            if (selectedOrder?.id === order.id) {
                              setSelectedOrder(null);
                            } else {
                              fetchOrderDetails(order.id);
                            }
                          }}
                        >
                          <Eye className="h-4 w-4 mr-2" />
                          {selectedOrder?.id === order.id ? 'Скрыть' : 'Подробнее'}
                        </Button>
                      </td>
                    </tr>
                    
                    {/* Inline Order Details */}
                    {selectedOrder?.id === order.id && (
                      <tr>
                        <td colSpan="6" className="px-4 py-4 bg-gray-50">
                          <Card className="p-6">
                            <div className="flex justify-between items-start mb-4">
                              <h3 className="text-xl font-semibold">Детали заказа</h3>
                              <Button variant="ghost" size="sm" onClick={() => setSelectedOrder(null)}>
                                Закрыть
                              </Button>
                            </div>
                            
                            <div className="space-y-4">
                              {/* Order Info */}
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <p className="text-sm text-gray-600">Дата и время заказа</p>
                                  <p className="font-medium">
                                    {new Date(selectedOrder.orderDate).toLocaleDateString('ru-RU')}
                                    {' '}
                                    {new Date(selectedOrder.orderDate).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-sm text-gray-600">Статус</p>
                                  <Badge className={statusColors[selectedOrder.status]}>
                                    {statusLabels[selectedOrder.status]}
                                  </Badge>
                                </div>
                              </div>

                              {/* Delivery Address */}
                              {selectedOrder.deliveryAddress && (
                                <Card className="p-4 bg-blue-50 border-blue-200">
                                  <div className="flex items-start gap-3">
                                    <MapPin className="h-5 w-5 text-blue-600 mt-0.5" />
                                    <div>
                                      <p className="font-medium text-blue-900">Адрес доставки</p>
                                      <p className="text-sm text-blue-800 mt-1">{selectedOrder.deliveryAddress.address}</p>
                                      {selectedOrder.deliveryAddress.phone && (
                                        <div className="flex items-center gap-2 mt-2 text-sm text-blue-700">
                                          <Phone className="h-3 w-3" />
                                          <span>{selectedOrder.deliveryAddress.phone}</span>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </Card>
                              )}

                              {/* Order Items */}
                              <div>
                                <p className="text-sm text-gray-600 mb-3 font-medium">Состав заказа</p>
                                <div className="space-y-2">
                                  {selectedOrder.orderDetails?.map((item, index) => (
                                    <div key={index} className="p-4 bg-white rounded-lg border">
                                      <div className="flex justify-between items-start">
                                        <div className="flex-1">
                                          <p className="font-medium text-base">{item.productName}</p>
                                          <p className="text-sm text-gray-500">Артикул: {item.article || 'Н/Д'}</p>
                                          <p className="text-sm text-gray-600 mt-1">
                                            {item.quantity} {item.unit} × {item.price.toLocaleString('ru-RU')} ₽
                                          </p>
                                        </div>
                                        <div className="text-right">
                                          <p className="text-lg font-semibold text-blue-600">
                                            {(item.price * item.quantity).toLocaleString('ru-RU')} ₽
                                          </p>
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {/* Total */}
                              <div className="pt-4 border-t flex justify-between items-center">
                                <p className="text-lg font-semibold">Итого к поставке:</p>
                                <p className="text-2xl font-bold text-blue-600">{selectedOrder.amount.toLocaleString('ru-RU')} ₽</p>
                              </div>
                            </div>
                          </Card>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
