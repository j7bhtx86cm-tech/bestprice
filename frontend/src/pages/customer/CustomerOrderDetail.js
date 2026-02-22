import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, RefreshCw, Loader2, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { translateOrderStatus, translateRequestStatus, translateItemStatus, getStatusBadgeClass } from '@/utils/statusTranslations';
import { shortId, formatRuDate } from '@/utils/formatUtils';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8001';
const API = `${BACKEND_URL}/api`;

export const CustomerOrderDetail = () => {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = user?.id;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [order, setOrder] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [itemsBySupplier, setItemsBySupplier] = useState([]);
  const prevStatusRef = useRef(null);

  const fetchDetail = async (isPoll = false) => {
    if (!userId || !orderId) return;
    if (!isPoll) {
      setLoading(true);
      setError(null);
    }
    try {
      const res = await axios.get(`${API}/v12/customer/orders/${orderId}`, {
        params: { user_id: userId },
        headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {},
      });
      if (res.data?.status === 'ok') {
        const newOrder = res.data.order || null;
        const newStatus = newOrder?.status;
        if (isPoll && prevStatusRef.current != null && newStatus !== prevStatusRef.current) {
          toast.info(`Статус заказа обновился: ${translateOrderStatus(newStatus, 'customer')}`);
        }
        prevStatusRef.current = newStatus;
        setOrder(newOrder);
        setSuppliers(res.data.suppliers || []);
        setItemsBySupplier(res.data.items_by_supplier || []);
      } else {
        if (!isPoll) setError('Не удалось загрузить заказ');
      }
    } catch (err) {
      if (!isPoll) setError(err.response?.data?.detail || err.message || 'Ошибка загрузки');
    } finally {
      if (!isPoll) setLoading(false);
    }
  };

  useEffect(() => {
    if (!userId || !orderId) {
      setLoading(false);
      return;
    }
    fetchDetail(false);
  }, [userId, orderId]);

  useEffect(() => {
    if (!userId || !orderId) return;
    const timer = setInterval(() => fetchDetail(true), 12000);
    return () => clearInterval(timer);
  }, [userId, orderId]);

  if (loading) {
    return (
      <div data-testid="customer-order-detail" className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !order) {
    return (
      <div data-testid="customer-order-detail">
        <Button variant="ghost" size="sm" onClick={() => navigate('/customer/orders')} className="mb-4">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Назад к списку
        </Button>
        <Card className="p-6 border-destructive/50">
          <p className="text-destructive">{error || 'Заказ не найден'}</p>
        </Card>
      </div>
    );
  }

  return (
    <div data-testid="customer-order-detail">
      <div className="flex items-center gap-3 mb-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/customer/orders')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Назад к списку
        </Button>
        <Button variant="outline" size="sm" onClick={() => fetchDetail(false)}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Обновить
        </Button>
      </div>

      <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
        Заказ <span className="font-mono">{shortId(order.id)}</span>
        {order.id && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => {
              if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(order.id);
                toast.success('ID скопирован');
              }
            }}
          >
            <Copy className="h-4 w-4" />
          </Button>
        )}
      </h2>
      {order.created_at && <p className="text-sm text-muted-foreground mb-4">{formatRuDate(order.created_at)}</p>}
      <p className="mb-4">
        Статус заказа: <Badge className={getStatusBadgeClass(order.status)} variant="outline">{translateOrderStatus(order.status, 'customer')}</Badge>
      </p>

      <section className="mb-6">
        <h3 className="text-lg font-semibold mb-3">Поставщики</h3>
        <ul className="space-y-2">
          {suppliers.map((s) => (
            <li key={s.supplier_company_id} className="flex items-center gap-2">
              <span className="font-medium">{s.supplier_name || '—'}</span>
              <Badge className={getStatusBadgeClass(s.request_status)}>
                {translateRequestStatus(s.request_status)}
              </Badge>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="text-lg font-semibold mb-3">Позиции по поставщикам</h3>
        <div className="space-y-6">
          {itemsBySupplier.map((block) => (
            <Card key={block.supplier_company_id} className="p-4">
              <p className="font-medium mb-3">{block.supplier_name || '—'}</p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2">Товар</th>
                      <th className="text-left py-2">Кол-во</th>
                      <th className="text-left py-2">Ед.</th>
                      <th className="text-left py-2">Статус</th>
                      <th className="text-left py-2">Причина отклонения</th>
                    </tr>
                  </thead>
                  <tbody>
                    {block.items?.map((it) => (
                      <tr key={it.id} className="border-b last:border-0">
                        <td className="py-2">{it.name_snapshot || '—'}</td>
                        <td className="py-2">{it.qty}</td>
                        <td className="py-2">{it.unit || 'шт'}</td>
                        <td className="py-2">
                          <Badge className={getStatusBadgeClass(it.status)} variant="outline">{translateItemStatus(it.status)}</Badge>
                        </td>
                        <td className="py-2 text-muted-foreground">
                          {it.reason_text ? it.reason_text : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
};
