import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useSearchParams, useLocation } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  Eye, CheckCircle, Package, Truck, Clock, 
  AlertTriangle, Tag, Scale, Plus, ChevronDown, ChevronUp
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const statusColors = {
  pending: 'bg-blue-100 text-blue-800',
  confirmed: 'bg-green-100 text-green-800',
  declined: 'bg-red-100 text-red-800',
  delivered: 'bg-gray-100 text-gray-800',
  processing: 'bg-yellow-100 text-yellow-800'
};

const statusLabels = {
  pending: 'Ожидает подтверждения',
  confirmed: 'Подтвержден',
  declined: 'Отклонен',
  delivered: 'Доставлен',
  processing: 'В обработке'
};

const statusIcons = {
  pending: Clock,
  confirmed: CheckCircle,
  declined: AlertTriangle,
  delivered: Truck,
  processing: Package
};

// Flag badges for order items
const FLAG_BADGES = {
  'BRAND_REPLACED': { label: 'Бренд заменён', color: 'bg-yellow-100 text-yellow-700', icon: Tag },
  'PACK_TOLERANCE_USED': { label: 'Фасовка ±20%', color: 'bg-blue-100 text-blue-700', icon: Scale },
  'PPU_FALLBACK_USED': { label: 'Расчёт по PPU', color: 'bg-purple-100 text-purple-700', icon: Scale },
  'MIN_QTY_ROUNDED': { label: 'Мин. заказ', color: 'bg-gray-100 text-gray-700', icon: Package },
  'AUTO_TOPUP_10PCT': { label: '+10% для минималки', color: 'bg-orange-100 text-orange-700', icon: Plus },
  'SUPPLIER_CHANGED': { label: 'Поставщик изменён', color: 'bg-indigo-100 text-indigo-700', icon: Truck },
};

const FlagBadge = ({ flag }) => {
  const config = FLAG_BADGES[flag];
  if (!config) return null;
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs ${config.color} mr-1`}>
      <Icon className="h-3 w-3 mr-1" />
      {config.label}
    </span>
  );
};

export const CustomerOrders = () => {
  const location = useLocation();
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedOrder, setExpandedOrder] = useState(null);
  const [showSuccessBanner, setShowSuccessBanner] = useState(false);
  const [checkoutInfo, setCheckoutInfo] = useState(null);

  const getUserId = () => user?.id || 'anonymous';
  
  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  useEffect(() => {
    // Check if we came from checkout
    if (location.state?.fromCheckout) {
      setShowSuccessBanner(true);
      setCheckoutInfo(location.state.checkoutInfo);
      // Auto-hide after 10 seconds
      setTimeout(() => setShowSuccessBanner(false), 10000);
    }
    
    fetchOrders();
  }, [location.state]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const userId = getUserId();
      const response = await axios.get(`${API}/v12/orders?user_id=${userId}`, {
        headers: getHeaders()
      });
      setOrders(response.data.orders || []);
    } catch (error) {
      console.error('Failed to fetch orders:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleOrder = (orderId) => {
    setExpandedOrder(expandedOrder === orderId ? null : orderId);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Group orders by session (orders created within 1 minute)
  const groupOrdersBySession = (orders) => {
    if (!orders.length) return [];
    
    const sessions = [];
    let currentSession = null;
    
    orders.forEach(order => {
      const orderTime = new Date(order.created_at).getTime();
      
      if (!currentSession || orderTime < currentSession.startTime - 60000) {
        // New session
        currentSession = {
          id: order.created_at,
          startTime: orderTime,
          orders: [order],
          total: order.amount,
        };
        sessions.push(currentSession);
      } else {
        // Same session
        currentSession.orders.push(order);
        currentSession.total += order.amount;
      }
    });
    
    return sessions;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const sessions = groupOrdersBySession(orders);

  return (
    <div data-testid="customer-orders-page">
      {/* Success Banner */}
      {showSuccessBanner && (
        <Card className="mb-6 p-6 bg-green-50 border-2 border-green-300" data-testid="checkout-success-banner">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0">
              <CheckCircle className="h-10 w-10 text-green-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">
                ✓ Заказы успешно созданы!
              </h3>
              {checkoutInfo && (
                <div className="space-y-1 text-green-700">
                  <p>Создано заказов: <strong>{checkoutInfo.ordersCount}</strong></p>
                  <p>Общая сумма: <strong>{checkoutInfo.total?.toLocaleString('ru-RU')} ₽</strong></p>
                </div>
              )}
              <p className="mt-2 text-sm text-green-600">
                Поставщики получили ваши заказы и скоро подтвердят их.
              </p>
            </div>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => setShowSuccessBanner(false)}
              className="text-green-700 hover:text-green-900"
            >
              ✕
            </Button>
          </div>
        </Card>
      )}

      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">История заказов</h2>
          <p className="text-base text-muted-foreground">
            {orders.length} заказов
          </p>
        </div>
      </div>

      {orders.length === 0 ? (
        <Card className="p-12 text-center">
          <Package className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">У вас пока нет заказов</p>
          <p className="text-sm text-gray-500">Добавьте товары в корзину и оформите заказ</p>
        </Card>
      ) : (
        <div className="space-y-6">
          {sessions.map((session) => (
            <Card key={session.id} className="overflow-hidden">
              {/* Session Header (if multiple orders) */}
              {session.orders.length > 1 && (
                <div className="px-6 py-4 bg-blue-50 border-b">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Package className="h-5 w-5 text-blue-600" />
                      <span className="font-semibold text-blue-800">
                        Единый заказ от {formatDate(session.orders[0].created_at)}
                      </span>
                      <Badge className="bg-blue-100 text-blue-800">
                        {session.orders.length} поставщиков
                      </Badge>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-blue-600">Общая сумма</p>
                      <p className="text-xl font-bold text-blue-800">
                        {session.total.toLocaleString('ru-RU')} ₽
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Orders in session */}
              <div className="divide-y">
                {session.orders.map((order) => {
                  const StatusIcon = statusIcons[order.status] || Clock;
                  const isExpanded = expandedOrder === order.id;
                  
                  return (
                    <div key={order.id} className="p-6">
                      {/* Order Header */}
                      <div 
                        className="flex items-center justify-between cursor-pointer"
                        onClick={() => toggleOrder(order.id)}
                      >
                        <div className="flex items-center gap-4">
                          <div className="flex-shrink-0">
                            <div className={`p-3 rounded-full ${statusColors[order.status]?.replace('text-', 'bg-').split(' ')[0]}`}>
                              <StatusIcon className="h-5 w-5" />
                            </div>
                          </div>
                          <div>
                            <p className="font-semibold text-lg">{order.supplier_name}</p>
                            <p className="text-sm text-gray-500">
                              {formatDate(order.created_at)} • {order.items_count} позиций
                            </p>
                          </div>
                        </div>
                        
                        <div className="flex items-center gap-4">
                          <Badge className={statusColors[order.status]}>
                            {statusLabels[order.status]}
                          </Badge>
                          <p className="text-xl font-bold">
                            {order.amount.toLocaleString('ru-RU')} ₽
                          </p>
                          {isExpanded ? (
                            <ChevronUp className="h-5 w-5 text-gray-400" />
                          ) : (
                            <ChevronDown className="h-5 w-5 text-gray-400" />
                          )}
                        </div>
                      </div>

                      {/* Order Details (expanded) */}
                      {isExpanded && (
                        <div className="mt-6 pt-6 border-t">
                          <h4 className="font-semibold mb-4">Состав заказа</h4>
                          <div className="space-y-3">
                            {order.items?.map((item, idx) => (
                              <div key={idx} className="p-4 bg-gray-50 rounded-lg">
                                <div className="flex justify-between items-start">
                                  <div className="flex-1">
                                    <p className="font-medium">{item.productName}</p>
                                    <p className="text-sm text-gray-500">
                                      Артикул: {item.article}
                                    </p>
                                    {/* Flags */}
                                    {item.flags?.length > 0 && (
                                      <div className="mt-2">
                                        {item.flags.map((flag, i) => (
                                          <FlagBadge key={i} flag={flag} />
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                  <div className="text-right">
                                    <p className="font-semibold">
                                      {item.quantity} {item.unit}
                                    </p>
                                    <p className="text-sm text-gray-500">
                                      {item.price?.toLocaleString('ru-RU')} ₽/{item.unit}
                                    </p>
                                    <p className="font-bold text-blue-600 mt-1">
                                      {(item.price * item.quantity).toLocaleString('ru-RU')} ₽
                                    </p>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                          
                          {/* Order Total */}
                          <div className="mt-4 pt-4 border-t flex justify-between items-center">
                            <span className="text-lg font-semibold">Итого по заказу:</span>
                            <span className="text-2xl font-bold">
                              {order.amount.toLocaleString('ru-RU')} ₽
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default CustomerOrders;
