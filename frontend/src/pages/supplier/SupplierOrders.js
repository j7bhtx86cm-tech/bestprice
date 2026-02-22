import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Package, Eye, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { translateRequestStatus, getStatusBadgeClass } from '@/utils/statusTranslations';
import { shortId, formatRuDate } from '@/utils/formatUtils';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8001';
const API = `${BACKEND_URL}/api`;

export const SupplierOrders = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const userId = user?.id;
  const prevTotalRef = useRef(0);

  const fetchInbox = async (isPoll = false) => {
    if (!userId) return;
    if (!isPoll) {
      setLoading(true);
      setError(null);
    }
    try {
      const response = await axios.get(
        `${API}/v12/supplier/orders/inbox`,
        {
          params: { user_id: userId, status: 'PENDING', limit: 50, offset: 0 },
          headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {},
        }
      );
      if (response.data?.status === 'ok') {
        const newTotal = response.data.total ?? 0;
        if (isPoll && newTotal > prevTotalRef.current && prevTotalRef.current > 0) {
          const delta = newTotal - prevTotalRef.current;
          toast.info(`Появился новый заказ${delta > 1 ? ` (+${delta})` : ''}`);
        }
        prevTotalRef.current = newTotal;
        setItems(response.data.items || []);
        setTotal(newTotal);
      } else {
        setItems([]);
        setTotal(0);
      }
    } catch (err) {
      if (!isPoll) {
        setError(err.response?.data?.detail || err.message || 'Ошибка загрузки');
        setItems([]);
        setTotal(0);
      }
    } finally {
      if (!isPoll) setLoading(false);
    }
  };

  useEffect(() => {
    if (!userId) {
      setLoading(false);
      return;
    }
    fetchInbox(false);
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    const timer = setInterval(() => fetchInbox(true), 12000);
    return () => clearInterval(timer);
  }, [userId]);

  const openOrder = (orderId) => {
    navigate(`/supplier/orders/${orderId || 'detail'}`, { state: { orderId } });
  };

  if (loading) {
    return (
      <div data-testid="supplier-orders-page" className="text-center py-8">
        Загрузка...
      </div>
    );
  }

  return (
    <div data-testid="supplier-orders-page">
      <h2 className="text-4xl font-bold mb-2">Входящие заказы</h2>
      <p className="text-base text-muted-foreground mb-6">Заказы от ресторанов, ожидающие ответа</p>

      {error && (
        <Card className="p-4 mb-4 border-red-200 bg-red-50 text-red-800">
          {error}
        </Card>
      )}

      {!userId ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">Войдите в аккаунт поставщика</p>
        </Card>
      ) : items.length === 0 ? (
        <Card className="p-8 text-center">
          <Package className="h-12 w-12 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600">Входящих заказов нет</p>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Заказ</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Дата</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Ресторан</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Позиций</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Qty</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Статус</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Действия</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
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
                    <td className="px-4 py-3 text-sm">{formatRuDate(row.submitted_at)}</td>
                    <td className="px-4 py-3 text-sm font-medium">{row.customer_company_name || '—'}</td>
                    <td className="px-4 py-3 text-sm">{row.supplier_items_count ?? 0}</td>
                    <td className="px-4 py-3 text-sm">{row.supplier_total_qty ?? 0}</td>
                    <td className="px-4 py-3 text-sm">
                      <Badge className={getStatusBadgeClass(row.request_status)}>{translateRequestStatus(row.request_status)}</Badge>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <Button variant="outline" size="sm" onClick={() => openOrder(row.order_id)}>
                        <Eye className="h-4 w-4 mr-2" />
                        Открыть
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
