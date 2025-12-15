import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { User, Users, FileText, ShoppingBag, BarChart3, Star, LogOut, Package, Building, Grid3x3, ShoppingCart } from 'lucide-react';

export const CustomerLayout = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  // Check if user is Chef or Staff
  const isChefOrStaff = user?.role === 'chef' || user?.role === 'responsible';
  const isAdmin = user?.role === 'customer';

  // Menu items based on role
  const getMenuItems = () => {
    if (isChefOrStaff) {
      // Simplified menu for Chef/Staff
      return [
        { path: '/customer/my-profile', label: 'Мой профиль', icon: User },
        { path: '/customer/matrix', label: 'Моя матрица', icon: Grid3x3 },
        { path: '/customer/catalog', label: 'Каталог товаров', icon: Package },
        { path: '/customer/orders', label: 'История заказов', icon: ShoppingCart },
      ];
    }
    
    // Full menu for Admin
    return [
      { path: '/customer/catalog', label: 'Каталог товаров', icon: Package },
      { path: '/customer/orders', label: 'История заказов', icon: ShoppingBag },
      { path: '/customer/analytics', label: 'Аналитика', icon: BarChart3 },
      { path: '/customer/profile', label: 'Профиль компании', icon: User },
      { path: '/customer/team', label: 'Ответственные лица', icon: Users },
      { path: '/customer/matrices', label: 'Управление матрицами', icon: Grid3x3 },
      { path: '/customer/documents', label: 'Документы', icon: FileText },
      { path: '/customer/ratings', label: 'Оценка поставщиков', icon: Star },
    ];
  };

  const menuItems = getMenuItems();

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
                      className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                        isActive
                          ? 'bg-blue-50 text-blue-600 font-medium'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                      data-testid={`nav-${item.path.split('/').pop()}`}
                    >
                      <Icon className="h-5 w-5" />
                      {item.label}
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