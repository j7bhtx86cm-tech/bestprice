import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const SupplierProfile = () => {
  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [formData, setFormData] = useState({
    actualAddress: '',
    phone: '',
    email: '',
    contactPersonName: '',
    contactPersonPhone: ''
  });

  useEffect(() => {
    fetchCompany();
  }, []);

  const fetchCompany = async () => {
    try {
      const response = await axios.get(`${API}/companies/my`);
      setCompany(response.data);
      setFormData({
        actualAddress: response.data.actualAddress || '',
        phone: response.data.phone || '',
        email: response.data.email || '',
        contactPersonName: response.data.contactPersonName || '',
        contactPersonPhone: response.data.contactPersonPhone || ''
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
      setMessage('Профиль успешно обновлен');
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
    <div data-testid="supplier-profile-page">
      <h2 className="text-2xl font-bold mb-6">Профиль компании</h2>

      {message && (
        <Alert className="mb-4" variant={message.includes('успешно') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-6">
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <Label>ИНН</Label>
            <Input value={company?.inn || ''} disabled />
          </div>
          <div>
            <Label>ОГРН</Label>
            <Input value={company?.ogrn || ''} disabled />
          </div>
        </div>

        <div>
          <Label>Название компании</Label>
          <Input value={company?.companyName || ''} disabled />
        </div>

        <div>
          <Label>Юридический адрес</Label>
          <Input value={company?.legalAddress || ''} disabled />
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="actualAddress">Фактический адрес</Label>
            <Input
              id="actualAddress"
              value={formData.actualAddress}
              onChange={(e) => setFormData({ ...formData, actualAddress: e.target.value })}
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="phone">Телефон</Label>
              <Input
                id="phone"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="contactPersonName">Контактное лицо</Label>
              <Input
                id="contactPersonName"
                value={formData.contactPersonName}
                onChange={(e) => setFormData({ ...formData, contactPersonName: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="contactPersonPhone">Телефон контакта</Label>
              <Input
                id="contactPersonPhone"
                value={formData.contactPersonPhone}
                onChange={(e) => setFormData({ ...formData, contactPersonPhone: e.target.value })}
              />
            </div>
          </div>

          <Button type="submit" disabled={saving} data-testid="save-profile-btn">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </form>
      </div>
    </div>
  );
};