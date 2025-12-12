import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Smartphone } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const MobileLogin = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  const [loginData, setLoginData] = useState({
    email: '',
    password: ''
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const success = await login(loginData.email, loginData.password);
      if (success) {
        navigate('/app/home');
      } else {
        setError('Неверный логин или пароль');
      }
    } catch (err) {
      setError('Ошибка входа. Попробуйте снова.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-500 to-blue-600 flex items-center justify-center px-4">
      <Card className="w-full max-w-md p-6">
        <div className="text-center mb-6">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Smartphone className="w-8 h-8 text-blue-600" />
          </div>
          <h1 className="text-2xl font-bold mb-2">BestPrice</h1>
          <p className="text-gray-600">Вход для ответственных лиц</p>
        </div>

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="email" className="text-base">Email или телефон</Label>
            <Input
              id="email"
              type="text"
              value={loginData.email}
              onChange={(e) => setLoginData({ ...loginData, email: e.target.value })}
              placeholder="manager@restaurant.ru"
              className="h-12 text-base"
              required
            />
          </div>

          <div>
            <Label htmlFor="password" className="text-base">Пароль</Label>
            <Input
              id="password"
              type="password"
              value={loginData.password}
              onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
              placeholder="••••••••"
              className="h-12 text-base"
              required
            />
          </div>

          <Button 
            type="submit" 
            disabled={loading} 
            className="w-full h-12 text-base"
            size="lg"
          >
            {loading ? 'Вход...' : 'Войти'}
          </Button>

          <button
            type="button"
            className="text-sm text-blue-600 w-full text-center mt-2"
            onClick={() => alert('Свяжитесь с администратором')}
          >
            Забыли пароль?
          </button>
        </form>
      </Card>
    </div>
  );
};
