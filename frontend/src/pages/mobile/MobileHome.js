import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ShoppingCart, ListOrdered, LogOut } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const MobileHome = () => {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [user, setUser] = useState(null);
  const [restaurant, setRestaurant] = useState(null);

  useEffect(() => {
    fetchUserInfo();
  }, []);

  const fetchUserInfo = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      const response = await axios.get(`${API}/auth/me`, { headers });
      setUser(response.data);
      
      // Get company info
      const companyResponse = await axios.get(`${API}/companies/my`, { headers });
      setRestaurant(companyResponse.data);
    } catch (error) {
      console.error('Failed to fetch user:', error);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/app/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b p-4">
        <div className="max-w-md mx-auto">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-xl font-bold text-blue-600">BestPrice</h1>
              <p className="text-sm text-gray-600">{restaurant?.companyName}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-md mx-auto p-4">
        {/* Welcome */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold mb-1">Здравствуйте{user?.name ? `, ${user.name.split(' ')[0]}` : ''}!</h2>
          <p className="text-gray-600">Выберите действие</p>
        </div>

        {/* Action Buttons */}
        <div className="space-y-4">
          <Button
            onClick={() => navigate('/app/order/new')}
            className="w-full h-20 text-lg flex items-center justify-center gap-3"
            size="lg"
          >
            <ShoppingCart className="h-8 w-8" />
            <span>Создать заказ</span>
          </Button>

          <Button
            onClick={() => navigate('/app/orders')}
            variant="outline"
            className="w-full h-20 text-lg flex items-center justify-center gap-3"
            size="lg"
          >
            <ListOrdered className="h-8 w-8" />
            <span>Мои заказы</span>
          </Button>
        </div>

        {/* Info Card */}
        <Card className="p-4 mt-6 bg-blue-50 border-blue-200">
          <p className="text-sm text-blue-800">
            Используйте номера позиций из вашего каталога для быстрого оформления заказов.
          </p>
        </Card>
      </div>
    </div>
  );
};
