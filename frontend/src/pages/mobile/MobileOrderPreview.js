import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Check, Edit, AlertTriangle, Loader2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const MobileOrderPreview = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchPreview();
  }, []);

  const fetchPreview = async () => {
    try {
      const itemsStr = sessionStorage.getItem('mobile_order_items');
      if (!itemsStr) {
        navigate('/app/order/new');
        return;
      }

      const items = JSON.parse(itemsStr);
      
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      const response = await axios.post(`${API}/mobile/orders/preview`, { items }, { headers });
      setPreview(response.data);
    } catch (error) {
      console.error('Preview failed:', error);
      setError('Не удалось загрузить предпросмотр заказа');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      const itemsStr = sessionStorage.getItem('mobile_order_items');
      const items = JSON.parse(itemsStr);
      
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      const response = await axios.post(`${API}/mobile/orders/confirm`, { items }, { headers });
      
      sessionStorage.removeItem('mobile_order_items');
      navigate(`/app/order/success?total=${response.data.total_orders}`);
    } catch (error) {
      console.error('Order confirmation failed:', error);
      setError('Не удалось создать заказ. Попробуйте снова.');
    } finally {
      setConfirming(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-32">
      {/* Header */}
      <div className="bg-white border-b p-4 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto">
          <h1 className="text-xl font-bold">Предпросмотр заказа</h1>
        </div>
      </div>

      <div className="max-w-2xl mx-auto p-4 space-y-4">
        {/* Errors */}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {preview?.errors && preview.errors.length > 0 && (
          <Alert variant="destructive">
            <AlertDescription>
              <p className="font-medium mb-2">Не удалось обработать:</p>
              <ul className="list-disc pl-4 space-y-1">
                {preview.errors.map((err, i) => (
                  <li key={i} className="text-sm">{err}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {/* Warnings */}
        {preview?.warnings && preview.warnings.length > 0 && (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              <ul className="space-y-1">
                {preview.warnings.map((warn, i) => (
                  <li key={i} className="text-sm">{warn}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {/* Items */}
        {preview?.positions && preview.positions.length > 0 && (
          <div className="space-y-3">
            {preview.positions.map((item, index) => (
              <Card key={index} className="p-4">
                <div className="space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium">{item.product_name}</p>
                      <p className="text-sm text-gray-600">Позиция: {item.position_number}</p>
                    </div>
                    <Badge variant="outline">{item.supplier_name}</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <p className="text-gray-600">Количество:</p>
                      <p className="font-medium">{item.qty} {item.unit}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-gray-600">Цена:</p>
                      <p className="font-medium">{item.price_per_unit} ₽/{item.unit}</p>
                    </div>
                  </div>
                  <div className="pt-2 border-t flex justify-between items-center">
                    <span className="text-sm text-gray-600">Итого:</span>
                    <span className="text-lg font-bold">{item.total.toFixed(2)} ₽</span>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Total */}
        {preview && (
          <Card className="p-4 bg-blue-50 border-blue-200">
            <div className="flex justify-between items-center">
              <div>
                <p className="text-sm text-gray-600">Всего товаров:</p>
                <p className="text-lg font-semibold">{preview.positions?.length || 0}</p>
              </div>
              <div className="text-right">
                <p className="text-sm text-gray-600">Сумма заказа:</p>
                <p className="text-2xl font-bold text-blue-600">{preview.total_amount?.toFixed(2) || 0} ₽</p>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Bottom Actions */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t p-4 space-y-2">
        <Button
          onClick={handleConfirm}
          disabled={confirming || !preview?.positions || preview.positions.length === 0}
          className="w-full h-12"
          size="lg"
        >
          {confirming ? (
            <>
              <Loader2 className="h-5 w-5 mr-2 animate-spin" />
              Оформление...
            </>
          ) : (
            <>
              <Check className="h-5 w-5 mr-2" />
              Подтвердить заказ
            </>
          )}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/app/order/new')}
          className="w-full h-12"
        >
          <Edit className="h-5 w-5 mr-2" />
          Редактировать
        </Button>
      </div>
    </div>
  );
};
