import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate, useLocation } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Eye, CheckCircle, Package, RefreshCw, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';
import { translateOrderStatus, getStatusBadgeClass } from '@/utils/statusTranslations';
import { shortId, formatRuDate } from '@/utils/formatUtils';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8001';
const API = `${BACKEND_URL}/api`;

export const CustomerOrders = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showSuccessBanner, setShowSuccessBanner] = useState(false);
  const [checkoutInfo, setCheckoutInfo] = useState(null);
  const userId = user?.id;

  const fetchOrders = async (isPoll = false, forRefresh = false) => {
    if (!userId) return;
    if (!isPoll && !forRefresh) setLoading(true);
    try {
      const res = await axios.get(`${API}/v12/customer/orders`, {
        params: { user_id: userId, status: 'ANY', limit: 50 },
        headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {},
      });
      if (res.data?.status === 'ok') {
        setItems(res.data.items || []);
        setTotal(res.data.total ?? 0);
      } else {
        setItems([]);
        setTotal(0);
      }
    } catch (err) {
      setItems([]);
      setTotal(0);
    } finally {
      if (!isPoll && !forRefresh) setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (!userId) return;
    setRefreshing(true);
    try {
      await fetchOrders(false, true);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (location.state?.fromCheckout) {
      setShowSuccessBanner(true);
      setCheckoutInfo(location.state.checkoutInfo);
      setTimeout(() => setShowSuccessBanner(false), 10000);
    }
    if (userId) fetchOrders(false);
    else setLoading(false);
  }, [userId, location.state]);

  useEffect(() => {
    if (!userId) return;
    const timer = setInterval(() => fetchOrders(true), 15000);
    return () => clearInterval(timer);
  }, [userId]);

  if (loading) {
    return (
      <div data-testid="customer-orders-page" className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div data-testid="customer-orders-page">
      {showSuccessBanner && checkoutInfo && (
        <Card className="mb-6 p-6 bg-green-50 border-2 border-green-300" data-testid="checkout-success-banner">
          <div className="flex items-start gap-4">
            <CheckCircle className="h-10 w-10 text-green-600 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">✓ Заказ отправлен поставщикам</h3>
              <p className="text-green-700">Поставщики получат заказ и подтвердят его.</p>
            </div>
          </div>
        </Card>
      )}

      <div className="flex items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">История заказов</h2>
          <p className="text-base text-muted-foreground">{total} заказов</p>
        </div>
        {userId && (
          <Button variant="outline" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Обновляю…' : 'Обновить'}
          </Button>
        )}
      </div>

      {!userId ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">Войдите в аккаунт</p>
        </Card>
      ) : items.length === 0 ? (
        <Card className="p-12 text-center">
          <Package className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600">Заказов нет</p>
        </Card>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Заказ</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Дата</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Статус заказа</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Поставщиков</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Позиций</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((row) => (
                <tr key={row.order_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm">
                    <span className="font-mono">{shortId(row.order_id)}</span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 ml-1 inline"
                      onClick={() => {
                        if (row.order_id && navigator.clipboard?.writeText) {
                          navigator.clipboard.writeText(row.order_id);
                          toast.success('ID скопирован');
                        }
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                  <td className="px-4 py-3 text-sm">{formatRuDate(row.created_at)}</td>
                  <td className="px-4 py-3 text-sm">
                    <Badge className={getStatusBadgeClass(row.order_status)} variant="outline">
                      {translateOrderStatus(row.order_status, 'customer')}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {row.suppliers_total ?? 0} (ожид. ответа: {row.suppliers_breakdown?.PENDING ?? 0})
                  </td>
                  <td className="px-4 py-3 text-sm">{row.items_total ?? 0}</td>
                  <td className="px-4 py-3 text-sm">
                    <Button variant="outline" size="sm" onClick={() => navigate(`/customer/orders/${row.order_id}`)}>
                      <Eye className="h-4 w-4 mr-2" />
                      Открыть
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default CustomerOrders;
