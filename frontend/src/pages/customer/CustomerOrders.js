import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useSearchParams } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Eye, TrendingDown, Award, Filter, X } from 'lucide-react';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const [orders, setOrders] = useState([]);
  const [filteredOrders, setFilteredOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [suppliers, setSuppliers] = useState({});
  const [allProducts, setAllProducts] = useState([]);
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || null);

  useEffect(() => {
    fetchOrdersAndSuppliers();
  }, []);

  useEffect(() => {
    // Update filter from URL parameter
    const status = searchParams.get('status');
    setStatusFilter(status);
  }, [searchParams]);

  useEffect(() => {
    // Filter orders when statusFilter changes
    if (statusFilter) {
      setFilteredOrders(orders.filter(order => order.status === statusFilter));
    } else {
      setFilteredOrders(orders);
    }
  }, [statusFilter, orders]);

  const clearFilter = () => {
    setSearchParams({});
    setStatusFilter(null);
  };

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
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">История заказов</h2>
        {statusFilter && (
          <Button variant="outline" size="sm" onClick={clearFilter}>
            <X className="h-4 w-4 mr-2" />
            Сбросить фильтр: {statusLabels[statusFilter]}
          </Button>
        )}
      </div>

      {orders.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">У вас пока нет заказов</p>
        </Card>
      ) : filteredOrders.length === 0 ? (
        <Card className="p-8 text-center">
          <Filter className="h-12 w-12 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600">Нет заказов со статусом "{statusLabels[statusFilter]}"</p>
          <Button variant="outline" className="mt-4" onClick={clearFilter}>
            Показать все заказы
          </Button>
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
                {filteredOrders.map((order) => (
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
            
            {/* Multi-Supplier Shopping Session Analytics */}
            {(() => {
              const orderTime = new Date(selectedOrder.orderDate).getTime();
              const relatedOrders = orders.filter(o => {
                const oTime = new Date(o.orderDate).getTime();
                return Math.abs(oTime - orderTime) < 60000; // Orders within 1 minute
              });
              
              if (relatedOrders.length > 1) {
                const totalAmount = relatedOrders.reduce((sum, o) => sum + o.amount, 0);
                const supplierNames = [...new Set(relatedOrders.map(o => suppliers[o.supplierCompanyId]?.companyName).filter(Boolean))];
                
                return (
                  <Card className="p-4 bg-blue-50 border-blue-200">
                    <div className="space-y-2">
                      <p className="font-semibold text-blue-900">
                        📦 Единая покупка из {relatedOrders.length} заказов
                      </p>
                      <p className="text-sm text-blue-800">
                        Заказ был разделен между {supplierNames.length} поставщиками: {supplierNames.join(', ')}
                      </p>
                      <div className="flex justify-between items-center pt-2 border-t border-blue-200">
                        <span className="text-sm font-medium text-blue-900">Общая сумма покупки:</span>
                        <span className="text-lg font-bold text-blue-600">{totalAmount.toFixed(2)} ₽</span>
                      </div>
                    </div>
                  </Card>
                );
              }
              return null;
            })()}
            
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
              <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                {selectedOrder.orderDetails.map((item, index) => (
                  <div key={index} className="p-3 bg-white rounded-lg border">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex-1">
                        <p className="font-medium text-base">{item.productName}</p>
                        <p className="text-sm text-gray-500">Артикул: {item.article}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-lg">{item.quantity} {item.unit}</p>
                        <p className="text-sm text-gray-600">{item.price} ₽/{item.unit}</p>
                        <p className="text-sm font-medium text-blue-600 mt-1">
                          {(item.price * item.quantity).toFixed(2)} ₽
                        </p>
                      </div>
                    </div>
                    <div className="pt-2 border-t border-gray-200">
                      <p className="text-xs text-gray-500">
                        Поставщик: <span className="font-medium text-gray-700">
                          {suppliers[selectedOrder.supplierCompanyId]?.companyName || 'Загрузка...'}
                        </span>
                      </p>
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