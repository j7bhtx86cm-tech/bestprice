import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Building2, Store } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const DEV_AUTH_BYPASS = process.env.REACT_APP_DEV_AUTH_BYPASS === '1';

export const AuthPage = () => {
  const navigate = useNavigate();
  const { devLogin } = useAuth();
  const [devLoading, setDevLoading] = useState(null);

  const handleDevLogin = async (role) => {
    if (!DEV_AUTH_BYPASS) return;
    try {
      setDevLoading(role);
      await devLogin(role);
      navigate(role === 'supplier' ? '/supplier/price-list' : '/customer');
    } catch (e) {
      console.error('DEV login failed:', e);
      setDevLoading(null);
    } finally {
      setDevLoading(null);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-blue-600 mb-2">BestPrice</h1>
          <p className="text-gray-600">Выберите тип аккаунта</p>
        </div>
        
        <div className="grid gap-4">
          <Card
            className="p-6 cursor-pointer hover:shadow-lg transition-shadow"
            onClick={() => navigate('/supplier/auth')}
            data-testid="select-supplier-card"
          >
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
                <Building2 className="w-8 h-8 text-blue-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-semibold mb-1">Я поставщик</h3>
                <p className="text-gray-600 text-sm">
                  Поставляю продукты для ресторанов
                </p>
              </div>
            </div>
          </Card>
          
          <Card
            className="p-6 cursor-pointer hover:shadow-lg transition-shadow"
            onClick={() => navigate('/customer/auth')}
            data-testid="select-customer-card"
          >
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center">
                <Store className="w-8 h-8 text-green-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-semibold mb-1">Я ресторан</h3>
                <p className="text-gray-600 text-sm">
                  Закупаю продукты для своего заведения
                </p>
              </div>
            </div>
          </Card>
        </div>
        
        <div className="mt-6 text-center space-y-2">
          {DEV_AUTH_BYPASS && (
            <div className="flex justify-center gap-2 pb-2">
              <Button
                variant="outline"
                size="sm"
                className="text-xs text-amber-700 border-amber-300"
                onClick={() => handleDevLogin('supplier')}
                disabled={!!devLoading}
                data-testid="dev-login-supplier-btn"
              >
                {devLoading === 'supplier' ? '...' : 'DEV: Войти как поставщик'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-xs text-amber-700 border-amber-300"
                onClick={() => handleDevLogin('customer')}
                disabled={!!devLoading}
                data-testid="dev-login-customer-btn"
              >
                {devLoading === 'customer' ? '...' : 'DEV: Войти как ресторан'}
              </Button>
            </div>
          )}
          <Button variant="ghost" onClick={() => navigate('/')} data-testid="back-to-home-btn">
            Вернуться на главную
          </Button>
        </div>
      </div>
    </div>
  );
};
