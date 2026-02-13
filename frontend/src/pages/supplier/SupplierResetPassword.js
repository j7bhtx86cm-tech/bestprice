import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { PasswordInput } from '@/components/PasswordInput';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
const API = `${BACKEND_URL}/api`;

export const SupplierResetPassword = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) setError('Отсутствует токен сброса пароля');
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (newPassword !== confirmPassword) {
      setError('Пароли не совпадают');
      return;
    }
    if (newPassword.length < 6) {
      setError('Пароль должен быть не менее 6 символов');
      return;
    }
    setLoading(true);
    try {
      await axios.post(`${API}/auth/reset-password`, { token, newPassword });
      setSuccess(true);
      setTimeout(() => navigate('/supplier/auth'), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка сброса пароля');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <Card className="w-full max-w-md p-8">
          <Alert variant="destructive">
            <AlertDescription>Недействительная ссылка. Запросите сброс пароля заново.</AlertDescription>
          </Alert>
          <Button className="mt-4 w-full" variant="outline" onClick={() => navigate('/supplier/auth')}>
            На страницу входа
          </Button>
        </Card>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <Card className="w-full max-w-md p-8 text-center">
          <p className="text-green-600 font-medium">Пароль успешно изменён.</p>
          <p className="text-sm text-gray-600 mt-2">Перенаправление на страницу входа...</p>
          <Button className="mt-4" variant="outline" onClick={() => navigate('/supplier/auth')}>
            Войти сейчас
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <Card className="w-full max-w-md p-8">
        <h1 className="text-xl font-bold text-blue-600 mb-2 text-center">Новый пароль</h1>
        <p className="text-gray-600 text-sm text-center mb-6">Введите новый пароль для аккаунта поставщика</p>
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="newPassword">Новый пароль</Label>
            <PasswordInput id="newPassword" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required minLength={6} />
          </div>
          <div>
            <Label htmlFor="confirmPassword">Подтверждение пароля</Label>
            <PasswordInput id="confirmPassword" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required minLength={6} />
          </div>
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Сохранение...' : 'Установить пароль'}
          </Button>
        </form>
        <Button variant="ghost" className="w-full mt-4" onClick={() => navigate('/supplier/auth')}>
          Назад к входу
        </Button>
      </Card>
    </div>
  );
};
