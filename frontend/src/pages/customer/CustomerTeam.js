import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { User } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerTeam = () => {
  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [formData, setFormData] = useState({
    contactPersonName: '',
    contactPersonPhone: '',
    email: ''
  });

  useEffect(() => {
    fetchCompany();
  }, []);

  const fetchCompany = async () => {
    try {
      const response = await axios.get(`${API}/companies/my`);
      setCompany(response.data);
      setFormData({
        contactPersonName: response.data.contactPersonName || '',
        contactPersonPhone: response.data.contactPersonPhone || '',
        email: response.data.email || ''
      });
    } catch (error) {
      console.error('Failed to fetch company:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage('');

    try {
      await axios.put(`${API}/companies/my`, formData);
      setMessage('Данные ответственного лица обновлены');
      fetchCompany();
    } catch (error) {
      setMessage('Ошибка при сохранении');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-team-page">
      <h2 className="text-2xl font-bold mb-6">Ответственные лица и доступ</h2>

      {message && (
        <Alert className="mb-4" variant={message.includes('обновлены') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <Card className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
            <User className="w-6 h-6 text-blue-600" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Основной контакт</h3>
            <p className="text-sm text-gray-600">Ответственное лицо за работу с платформой</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="contactPersonName">ФИО</Label>
            <Input
              id="contactPersonName"
              value={formData.contactPersonName}
              onChange={(e) => setFormData({ ...formData, contactPersonName: e.target.value })}
              placeholder="Иванов Иван Иванович"
            />
          </div>

          <div>
            <Label htmlFor="contactPersonPhone">Телефон</Label>
            <Input
              id="contactPersonPhone"
              value={formData.contactPersonPhone}
              onChange={(e) => setFormData({ ...formData, contactPersonPhone: e.target.value })}
              placeholder="+7 (999) 123-45-67"
            />
          </div>

          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="contact@company.ru"
            />
          </div>

          <Button type="submit" disabled={saving} data-testid="save-team-btn">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </form>
      </Card>

      <Card className="p-6 mt-6 bg-blue-50 border-blue-200">
        <h3 className="text-lg font-semibold mb-2">Расширенный доступ</h3>
        <p className="text-gray-700">
          В будущих версиях вы сможете добавлять несколько ответственных лиц с разными уровнями доступа
          к функциям платформы.
        </p>
      </Card>
    </div>
  );
};