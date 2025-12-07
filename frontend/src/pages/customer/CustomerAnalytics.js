import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { TrendingUp, ShoppingCart, DollarSign } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerAnalytics = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    try {
      const response = await axios.get(`${API}/analytics/customer`);
      setAnalytics(response.data);
    } catch (error) {
      console.error('Failed to fetch analytics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-analytics-page">
      <h2 className="text-2xl font-bold mb-6">Аналитика</h2>

      <div className="grid md:grid-cols-3 gap-6">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 mb-1">Всего заказов</p>
              <p className="text-3xl font-bold" data-testid="total-orders">
                {analytics?.totalOrders || 0}
              </p>
            </div>
            <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
              <ShoppingCart className="w-6 h-6 text-blue-600" />
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 mb-1">Общая сумма</p>
              <p className="text-3xl font-bold" data-testid="total-amount">
                {analytics?.totalAmount?.toLocaleString('ru-RU') || 0} ₽
              </p>
            </div>
            <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
              <DollarSign className="w-6 h-6 text-green-600" />
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 mb-1">Экономия</p>
              <p className="text-3xl font-bold text-green-600" data-testid="savings">
                {analytics?.savings?.toLocaleString('ru-RU') || 0} ₽
              </p>
              <p className="text-xs text-gray-500 mt-1">~15% от общей суммы</p>
            </div>
            <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center">
              <TrendingUp className="w-6 h-6 text-purple-600" />
            </div>
          </div>
        </Card>
      </div>

      <Card className="p-6 mt-6">
        <h3 className="text-lg font-semibold mb-4">О расчете экономии</h3>
        <p className="text-gray-600">
          Экономия рассчитывается как примерная разница между рыночными ценами и ценами на платформе BestPrice.
          Средняя экономия составляет около 15% от общей суммы заказов.
        </p>
      </Card>
    </div>
  );
};