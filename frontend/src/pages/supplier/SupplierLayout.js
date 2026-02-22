import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { User, Settings, FileText, ShoppingBag, Star, LogOut, FolderOpen, Building2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8001';
const API = `${BACKEND_URL}/api`;

export const SupplierLayout = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [pendingCount, setPendingCount] = useState(0);
  const userId = user?.id;

  useEffect(() => {
    if (!userId) {
      setPendingCount(0);
      return;
    }
    const fetchCount = async () => {
      try {
        const res = await axios.get(`${API}/v12/supplier/orders/inbox-count`, {
          params: { user_id: userId },
          headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {},
        });
        if (res.data?.status === 'ok' && typeof res.data.pending_count === 'number') {
          setPendingCount(res.data.pending_count);
        }
      } catch (_) {
        setPendingCount(0);
      }
    };
    fetchCount();
    const timer = setInterval(fetchCount, 12000);
    return () => clearInterval(timer);
  }, [userId]);

  const menuItems = [
    { path: '/supplier/profile', label: 'Профиль', icon: User },
    { path: '/supplier/price-list', label: 'Прайс-лист', icon: FileText },
    { path: '/supplier/restaurants', label: 'Мои рестораны', icon: Building2 },
    { path: '/supplier/orders', label: 'Входящие заказы', icon: ShoppingBag, badge: pendingCount },
    { path: '/supplier/settings', label: 'Настройки заказов', icon: Settings },
    { path: '/supplier/documents', label: 'Документы ресторанов', icon: FolderOpen },
    { path: '/supplier/rating', label: 'Рейтинг', icon: Star },
  ];

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-blue-600">BestPrice</h1>
          <Button variant="ghost" onClick={handleLogout} data-testid="logout-btn">
            <LogOut className="mr-2 h-4 w-4" />
            Выйти
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        <div className="flex gap-6">
          <aside className="w-64 flex-shrink-0">
            <nav className="bg-white rounded-lg shadow-sm p-4">
              <div className="space-y-1">
                {menuItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path;
                  return (
                    <button
                      key={item.path}
                      onClick={() => navigate(item.path)}
                      className={`w-full flex items-center justify-between gap-3 px-4 py-3 rounded-lg transition-colors ${
                        isActive
                          ? 'bg-blue-50 text-blue-600 font-medium'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                      data-testid={`nav-${item.path.split('/').pop()}`}
                    >
                      <span className="flex items-center gap-3">
                        <Icon className="h-5 w-5" />
                        {item.label}
                      </span>
                      {typeof item.badge === 'number' && item.badge > 0 && (
                        <Badge variant="secondary" className="bg-amber-100 text-amber-800">
                          {item.badge}
                        </Badge>
                      )}
                    </button>
                  );
                })}
              </div>
            </nav>
          </aside>

          <main className="flex-1">
            <div className="bg-white rounded-lg shadow-sm p-6">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
};