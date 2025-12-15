import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { User, Mail, Phone, Briefcase } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerMyProfile = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [profile, setProfile] = useState({
    name: '',
    email: '',
    phone: '',
    role: ''
  });

  useEffect(() => {
    fetchProfile();
  }, []);

  const fetchProfile = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      // Get current user details
      const response = await axios.get(`${API}/auth/me`, { headers });
      
      // Get full user profile
      const userResponse = await axios.get(`${API}/users/my-profile`, { headers });
      
      setProfile({
        name: userResponse.data.name || '',
        email: userResponse.data.email || '',
        phone: userResponse.data.phone || '',
        role: userResponse.data.role || ''
      });
    } catch (error) {
      console.error('Failed to fetch profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage('');

    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      await axios.put(`${API}/users/my-profile`, {
        phone: profile.phone,
        email: profile.email
      }, { headers });
      
      setMessage('success');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      console.error('Failed to update profile:', error);
      setMessage('error');
      setTimeout(() => setMessage(''), 3000);
    } finally {
      setSaving(false);
    }
  };

  const getRoleLabel = (role) => {
    if (role === 'chef') return 'Повар';
    if (role === 'responsible') return 'Сотрудник';
    return role;
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-4xl font-bold mb-2">Мой профиль</h2>
      <p className="text-base text-muted-foreground mb-6">
        Просмотр и редактирование личной информации
      </p>

      {message === 'success' && (
        <Alert className="mb-6 bg-green-50 border-green-200">
          <AlertDescription className="text-green-800">
            ✓ Данные успешно обновлены
          </AlertDescription>
        </Alert>
      )}
      
      {message === 'error' && (
        <Alert className="mb-6 bg-red-50 border-red-200">
          <AlertDescription className="text-red-800">
            ✗ Ошибка при обновлении
          </AlertDescription>
        </Alert>
      )}

      <Card className="p-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Name - Read Only */}
          <div>
            <Label className="text-sm mb-2 flex items-center gap-2">
              <User className="h-4 w-4" />
              ФИО
            </Label>
            <Input
              value={profile.name}
              disabled
              className="bg-gray-50"
            />
            <p className="text-xs text-gray-500 mt-1">
              Имя не может быть изменено. Обратитесь к администратору.
            </p>
          </div>

          {/* Role - Read Only */}
          <div>
            <Label className="text-sm mb-2 flex items-center gap-2">
              <Briefcase className="h-4 w-4" />
              Должность
            </Label>
            <Input
              value={getRoleLabel(profile.role)}
              disabled
              className="bg-gray-50"
            />
          </div>

          {/* Email - Editable */}
          <div>
            <Label className="text-sm mb-2 flex items-center gap-2">
              <Mail className="h-4 w-4" />
              Email <span className="text-red-500">*</span>
            </Label>
            <Input
              type="email"
              value={profile.email}
              onChange={(e) => setProfile({ ...profile, email: e.target.value })}
              placeholder="ivanov@company.ru"
              required
            />
          </div>

          {/* Phone - Editable */}
          <div>
            <Label className="text-sm mb-2 flex items-center gap-2">
              <Phone className="h-4 w-4" />
              Телефон <span className="text-red-500">*</span>
            </Label>
            <Input
              type="tel"
              value={profile.phone}
              onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
              placeholder="+7 (999) 123-45-67"
              required
            />
          </div>

          <Button type="submit" disabled={saving} className="w-full" size="lg">
            {saving ? 'Сохранение...' : 'Сохранить изменения'}
          </Button>
        </form>
      </Card>

      <Card className="p-6 mt-6 bg-blue-50">
        <h3 className="text-lg font-semibold mb-2">О вашей учетной записи</h3>
        <p className="text-sm text-gray-700">
          Вы можете изменить свой email и телефон. Для изменения имени или должности 
          обратитесь к администратору ресторана.
        </p>
      </Card>
    </div>
  );
};
