import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { CheckCircle, Plus, ListOrdered, Home } from 'lucide-react';

export const MobileOrderSuccess = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const totalOrders = searchParams.get('total') || '1';

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <Card className="max-w-md w-full p-6 text-center">
        <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="w-12 h-12 text-green-600" />
        </div>
        
        <h2 className="text-2xl font-bold mb-2">Заказ создан!</h2>
        <p className="text-gray-600 mb-6">
          {totalOrders === '1' 
            ? 'Ваш заказ успешно размещен'
            : `Создано ${totalOrders} заказов для разных поставщиков`
          }
        </p>

        <div className="space-y-3">
          <Button
            onClick={() => navigate('/app/orders')}
            className="w-full h-12"
            size="lg"
          >
            <ListOrdered className="h-5 w-5 mr-2" />
            Мои заказы
          </Button>

          <Button
            onClick={() => navigate('/app/order/new')}
            variant="outline"
            className="w-full h-12"
          >
            <Plus className="h-5 w-5 mr-2" />
            Новый заказ
          </Button>

          <Button
            onClick={() => navigate('/app/home')}
            variant="ghost"
            className="w-full h-12"
          >
            <Home className="h-5 w-5 mr-2" />
            На главную
          </Button>
        </div>
      </Card>
    </div>
  );
};
