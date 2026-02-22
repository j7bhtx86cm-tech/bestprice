import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { ArrowLeft, CheckCircle, Send, Loader2, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { translateRequestStatus, translateItemStatus, getStatusBadgeClass } from '@/utils/statusTranslations';
import { shortId } from '@/utils/formatUtils';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8001';
const API = `${BACKEND_URL}/api`;

export const SupplierOrderDetail = () => {
  const navigate = useNavigate();
  const { orderId } = useParams();
  const { user } = useAuth();
  const userId = user?.id;

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [order, setOrder] = useState(null);
  const [request, setRequest] = useState(null);
  const [customer, setCustomer] = useState(null);
  const [items, setItems] = useState([]);
  const [itemDecisions, setItemDecisions] = useState({});

  useEffect(() => {
    if (!userId || !orderId) {
      setLoading(false);
      return;
    }
    fetchDetail();
  }, [userId, orderId]);

  const fetchDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API}/v12/supplier/orders/${orderId}`, {
        params: { user_id: userId },
        headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {},
      });
      if (res.data?.status === 'ok') {
        setOrder(res.data.order || null);
        setRequest(res.data.request || null);
        setCustomer(res.data.customer || {});
        const list = res.data.items || [];
        setItems(list);
        const initial = {};
        list.forEach((it) => {
          initial[it.id] = { reject: false, reason_text: '' };
        });
        setItemDecisions(initial);
      } else {
        setError('Не удалось загрузить заказ');
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  };

  const setReject = (itemId, reject, reasonText = '') => {
    setItemDecisions((prev) => ({
      ...prev,
      [itemId]: { ...(prev[itemId] || {}), reject, reason_text: reasonText || (prev[itemId]?.reason_text || '') },
    }));
  };

  const handleConfirmAll = async () => {
    if (!userId || !orderId) return;
    setSubmitting(true);
    try {
      const res = await axios.post(
        `${API}/v12/supplier/orders/${orderId}/respond`,
        { decision: 'CONFIRM_ALL', comment: null },
        { params: { user_id: userId }, headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {} }
      );
      if (res.data?.status === 'ok') {
        toast.success(`Ответ отправлен: ${translateRequestStatus(res.data.request_status)}`);
        fetchDetail();
      } else {
        toast.error(res.data?.detail || 'Ошибка отправки');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Ошибка отправки');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendCustom = async () => {
    if (!userId || !orderId) return;
    const payload = items.map((it) => {
      const dec = itemDecisions[it.id];
      if (dec?.reject) {
        return { item_id: it.id, decision: 'REJECT', reason_code: 'OUT_OF_STOCK', reason_text: dec.reason_text || 'Не указана причина' };
      }
      return { item_id: it.id, decision: 'CONFIRM' };
    });
    const hasReject = payload.some((p) => p.decision === 'REJECT');
    if (hasReject && payload.some((p) => p.decision === 'REJECT' && !(itemDecisions[p.item_id]?.reason_text?.trim()))) {
      toast.error('Укажите причину отклонения для отклоённых позиций');
      return;
    }
    setSubmitting(true);
    try {
      const res = await axios.post(
        `${API}/v12/supplier/orders/${orderId}/respond`,
        { decision: 'CUSTOM', comment: null, items: payload },
        { params: { user_id: userId }, headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {} }
      );
      if (res.data?.status === 'ok') {
        toast.success(`Ответ отправлен: ${translateRequestStatus(res.data.request_status)}`);
        fetchDetail();
      } else {
        toast.error(res.data?.detail || 'Ошибка отправки');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Ошибка отправки');
    } finally {
      setSubmitting(false);
    }
  };

  const isPending = request?.status === 'PENDING';
  const canRespond = isPending && items.length > 0;

  if (loading) {
    return (
      <div data-testid="supplier-order-detail" className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !order) {
    return (
      <div data-testid="supplier-order-detail">
        <Button variant="ghost" size="sm" onClick={() => navigate('/supplier/orders')} className="mb-4">
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
    <div data-testid="supplier-order-detail">
      <Button variant="ghost" size="sm" onClick={() => navigate('/supplier/orders')} className="mb-4">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Назад к списку
      </Button>

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
      <p className="text-muted-foreground mb-4">
        Ресторан: <strong>{customer.name || '—'}</strong>
      </p>
      <p className="mb-4">
        Статус заявки:{' '}
        <Badge className={getStatusBadgeClass(request.status)}>
          {translateRequestStatus(request.status)}
        </Badge>
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Товар</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Кол-во</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Ед.</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Статус</th>
              {canRespond && (
                <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Отклонить</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((it) => (
              <tr key={it.id}>
                <td className="px-4 py-2 text-sm">{it.name_snapshot || '—'}</td>
                <td className="px-4 py-2 text-sm">{it.qty}</td>
                <td className="px-4 py-2 text-sm">{it.unit || 'шт'}</td>
                <td className="px-4 py-2 text-sm">
                  <Badge className={getStatusBadgeClass(it.status)} variant="outline">{translateItemStatus(it.status)}</Badge>
                </td>
                {canRespond && it.status === 'PENDING' && (
                  <td className="px-4 py-2">
                    <div className="flex flex-col gap-1">
                      <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={itemDecisions[it.id]?.reject || false}
                          onCheckedChange={(checked) => setReject(it.id, !!checked)}
                        />
                        Отклонить
                      </label>
                      {itemDecisions[it.id]?.reject && (
                        <Input
                          placeholder="Причина отклонения (обязательно)"
                          value={itemDecisions[it.id]?.reason_text || ''}
                          onChange={(e) => setReject(it.id, true, e.target.value)}
                          className="max-w-xs"
                        />
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canRespond && (
        <div className="flex flex-wrap gap-3">
          <Button onClick={handleConfirmAll} disabled={submitting}>
            <CheckCircle className="h-4 w-4 mr-2" />
            Подтвердить всё
          </Button>
          <Button variant="secondary" onClick={handleSendCustom} disabled={submitting}>
            <Send className="h-4 w-4 mr-2" />
            Отправить ответ
          </Button>
        </div>
      )}
    </div>
  );
};
