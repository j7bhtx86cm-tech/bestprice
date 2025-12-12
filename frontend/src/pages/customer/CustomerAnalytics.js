import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, ShoppingCart, DollarSign, TrendingDown, Package } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

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

export const CustomerAnalytics = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/analytics/customer`, { headers });
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
      <h2 className="text-4xl font-bold mb-2">Аналитика</h2>
      <p className="text-base text-muted-foreground mb-6">Статистика ваших заказов и экономии</p>

      {/* Main Stats */}
      <div className="grid md:grid-cols-3 gap-6 mb-6">
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
              <p className="text-sm text-gray-600 mb-1">Потрачено через BestPrice</p>
              <p className="text-3xl font-bold" data-testid="total-amount">
                {analytics?.totalAmount?.toLocaleString('ru-RU') || 0} ₽
              </p>
            </div>
            <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
              <DollarSign className="w-6 h-6 text-green-600" />
            </div>
          </div>
        </Card>

        <Card className="p-6 bg-gradient-to-br from-green-50 to-green-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-green-700 mb-1 font-medium">Ваша экономия</p>
              <p className="text-3xl font-bold text-green-600" data-testid="savings">
                {analytics?.savings?.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'} ₽
              </p>
              <p className="text-xs text-green-600 mt-1">
                {analytics?.savingsPercentage ? `${analytics.savingsPercentage.toFixed(1)}% экономии` : 'За все время'}
              </p>
            </div>
            <div className="w-12 h-12 bg-green-200 rounded-full flex items-center justify-center">
              <TrendingDown className="w-6 h-6 text-green-700" />
            </div>
          </div>
        </Card>
      </div>

      {/* Savings Comparison Card */}
      {analytics && analytics.optimalCost !== undefined && (
        <Card className="p-6 mb-6 bg-gradient-to-r from-blue-50 to-green-50">
          <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <TrendingDown className="h-5 w-5 text-blue-600" />
            Анализ экономии BestPrice
          </h3>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="p-4 bg-white rounded-lg">
              <p className="text-sm text-gray-600 mb-2">Если бы платили рыночные цены:</p>
              <p className="text-3xl font-bold text-gray-700">
                {analytics.optimalCost?.toLocaleString('ru-RU', { minimumFractionDigits: 2 }) || 0} ₽
              </p>
              <p className="text-xs text-gray-500 mt-1">
                (каждый товар по максимальной цене среди поставщиков)
              </p>
            </div>
            <div className="p-4 bg-white rounded-lg">
              <p className="text-sm text-gray-600 mb-2">Через BestPrice (лучшие цены):</p>
              <p className="text-3xl font-bold text-green-600">
                {analytics.actualCost?.toLocaleString('ru-RU', { minimumFractionDigits: 2 }) || 0} ₽
              </p>
              <div className="mt-2">
                {analytics.savings > 0 ? (
                  <p className="text-sm text-green-600 font-medium">
                    ✓ Экономия: {analytics.savingsPercentage?.toFixed(1) || 0}%
                  </p>
                ) : (
                  <p className="text-sm text-green-600 font-medium">
                    ✓ Вы уже используете лучшие цены!
                  </p>
                )}
              </div>
            </div>
          </div>
          <div className="mt-4 p-3 bg-blue-100 rounded-lg">
            <p className="text-sm text-blue-800">
              <strong>Как считается:</strong> Мы сравниваем, сколько вы заплатили, с тем, сколько стоили бы те же товары по средним рыночным ценам. BestPrice автоматически выбирает самые выгодные предложения от всех поставщиков.
            </p>
          </div>
        </Card>
      )}

      {/* Orders by Status */}
      <Card className="p-6 mb-6">
        <h3 className="text-xl font-semibold mb-4">Заказы по статусу</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <button
            onClick={() => navigate('/customer/orders?status=new')}
            className="text-center p-4 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors cursor-pointer"
          >
            <p className="text-2xl font-bold text-blue-600">{analytics?.ordersByStatus?.new || 0}</p>
            <p className="text-sm text-gray-600 mt-1">Новые</p>
          </button>
          <button
            onClick={() => navigate('/customer/orders?status=confirmed')}
            className="text-center p-4 bg-green-50 rounded-lg hover:bg-green-100 transition-colors cursor-pointer"
          >
            <p className="text-2xl font-bold text-green-600">{analytics?.ordersByStatus?.confirmed || 0}</p>
            <p className="text-sm text-gray-600 mt-1">Подтверждены</p>
          </button>
          <button
            onClick={() => navigate('/customer/orders?status=partial')}
            className="text-center p-4 bg-yellow-50 rounded-lg hover:bg-yellow-100 transition-colors cursor-pointer"
          >
            <p className="text-2xl font-bold text-yellow-600">{analytics?.ordersByStatus?.partial || 0}</p>
            <p className="text-sm text-gray-600 mt-1">Частичные</p>
          </button>
          <button
            onClick={() => navigate('/customer/orders?status=declined')}
            className="text-center p-4 bg-red-50 rounded-lg hover:bg-red-100 transition-colors cursor-pointer"
          >
            <p className="text-2xl font-bold text-red-600">{analytics?.ordersByStatus?.declined || 0}</p>
            <p className="text-sm text-gray-600 mt-1">Отклонены</p>
          </button>
        </div>
      </Card>

      {/* Recent Orders */}
      {analytics?.recentOrders && analytics.recentOrders.length > 0 && (
        <Card className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-xl font-semibold">Последние заказы</h3>
            <button
              onClick={() => navigate('/customer/orders')}
              className="text-sm text-blue-600 hover:text-blue-700"
            >
              Смотреть все →
            </button>
          </div>
          <div className="space-y-3">
            {analytics.recentOrders.map((order, index) => (
              <div key={order.id || index} className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                    <Package className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="font-medium">Заказ от {new Date(order.orderDate).toLocaleDateString('ru-RU')}</p>
                    <p className="text-sm text-gray-600">{order.orderDetails?.length || 0} товаров</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-semibold">{order.amount?.toLocaleString('ru-RU')} ₽</p>
                  <Badge className={`${statusColors[order.status]} mt-1`}>
                    {statusLabels[order.status] || order.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Info Card */}
      <Card className="p-6 mt-6 bg-blue-50">
        <div className="flex gap-3">
          <TrendingUp className="w-5 h-5 text-blue-600 mt-0.5" />
          <div>
            <h3 className="text-lg font-semibold mb-2 text-blue-900">О расчете экономии</h3>
            <p className="text-sm text-blue-800">
              Экономия рассчитывается как разница между средней рыночной ценой и ценой, которую вы заплатили. 
              Используя BestPrice, вы автоматически выбираете самые выгодные предложения от поставщиков.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
};