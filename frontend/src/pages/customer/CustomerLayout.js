import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { User, Users, FileText, ShoppingBag, BarChart3, Star, LogOut, Package, Building, Grid3x3, ShoppingCart, Heart } from 'lucide-react';

export const CustomerLayout = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [cartCount, setCartCount] = useState(0);

  // Check if user is Chef or Staff
  const isChefOrStaff = user?.role === 'chef' || user?.role === 'responsible';
  const isAdmin = user?.role === 'customer';

  useEffect(() => {
    // Update cart count on route change
    updateCartCount();
    
    // Listen for storage changes (when items added from other tabs/pages)
    const handleStorageChange = () => updateCartCount();
    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('cartUpdated', handleStorageChange);
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('cartUpdated', handleStorageChange);
    };
  }, [location]);

  const updateCartCount = () => {
    const catalogCart = JSON.parse(localStorage.getItem('catalogCart') || '[]');
    const favoriteCart = JSON.parse(localStorage.getItem('favoriteCart') || '[]');
    setCartCount(catalogCart.length + favoriteCart.length);
  };

  // Menu items based on role
  const getMenuItems = () => {
    if (isChefOrStaff) {
      // Simplified menu for Chef/Staff
      return [
        { path: '/customer/my-profile', label: 'Мой профиль', icon: User },
        { path: '/customer/matrix', label: 'Моя матрица', icon: Grid3x3 },
        { path: '/customer/favorites', label: 'Избранное', icon: Heart },
        { path: '/customer/cart', label: 'Корзина', icon: ShoppingCart },
        { path: '/customer/catalog', label: 'Каталог товаров', icon: Package },
        { path: '/customer/orders', label: 'История заказов', icon: ShoppingCart },
      ];
    }
    
    // Full menu for Admin (removed Matrix Management)
    return [
      { path: '/customer/catalog', label: 'Каталог товаров', icon: Package },
      { path: '/customer/favorites', label: 'Избранное', icon: Heart },
      { path: '/customer/cart', label: 'Корзина', icon: ShoppingCart },
      { path: '/customer/orders', label: 'История заказов', icon: ShoppingBag },
      { path: '/customer/analytics', label: 'Аналитика', icon: BarChart3 },
      { path: '/customer/profile', label: 'Профиль компании', icon: Building },
      { path: '/customer/team', label: 'Ответственные лица', icon: Users },
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
          <div className="flex items-center gap-4">
            {/* Cart Icon */}
            <button
              onClick={() => navigate('/customer/cart')}
              className="relative p-2 hover:bg-gray-100 rounded-full transition-colors"
            >
              <ShoppingCart className="h-6 w-6 text-gray-700" />
              {cartCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full h-5 w-5 flex items-center justify-center">
                  {cartCount}
                </span>
              )}
            </button>
            <Button variant="ghost" onClick={handleLogout} data-testid="logout-btn">
              <LogOut className="mr-2 h-4 w-4" />
              Выйти
            </Button>
          </div>
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