import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Trash2, Plus, MapPin, Phone } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerProfile = () => {
  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [formData, setFormData] = useState({
    actualAddress: '',
    phone: '',
    email: '',
    contactPersonName: '',
    contactPersonPhone: '',
    deliveryAddresses: [{ address: '', phone: '', additionalPhone: '' }]
  });

  useEffect(() => {
    fetchCompany();
  }, []);

  const fetchCompany = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/companies/my`, { headers });
      setCompany(response.data);
      
      // Handle both old string format and new object format for delivery addresses
      let deliveryAddresses = [{ address: '', phone: '', additionalPhone: '' }];
      if (response.data.deliveryAddresses && response.data.deliveryAddresses.length > 0) {
        deliveryAddresses = response.data.deliveryAddresses.map(addr => {
          if (typeof addr === 'string') {
            // Convert old string format to new object format
            return { address: addr, phone: '', additionalPhone: '' };
          }
          return addr;
        });
      }
      
      setFormData({
        actualAddress: response.data.actualAddress || '',
        phone: response.data.phone || '',
        email: response.data.email || '',
        contactPersonName: response.data.contactPersonName || '',
        contactPersonPhone: response.data.contactPersonPhone || '',
        deliveryAddresses: deliveryAddresses
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
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      // Filter out empty delivery addresses
      const cleanedData = {
        ...formData,
        deliveryAddresses: formData.deliveryAddresses.filter(addr => addr.address.trim() !== '')
      };
      
      await axios.put(`${API}/companies/my`, cleanedData, { headers });
      setMessage('success');
      fetchCompany();
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('error');
      setTimeout(() => setMessage(''), 3000);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const addDeliveryAddress = () => {
    setFormData({
      ...formData,
      deliveryAddresses: [...formData.deliveryAddresses, { address: '', phone: '', additionalPhone: '' }]
    });
  };

  const removeDeliveryAddress = (index) => {
    const newAddresses = formData.deliveryAddresses.filter((_, i) => i !== index);
    setFormData({
      ...formData,
      deliveryAddresses: newAddresses.length > 0 ? newAddresses : [{ address: '', phone: '', additionalPhone: '' }]
    });
  };

  const updateDeliveryAddress = (index, field, value) => {
    const newAddresses = [...formData.deliveryAddresses];
    newAddresses[index] = {
      ...newAddresses[index],
      [field]: value
    };
    setFormData({
      ...formData,
      deliveryAddresses: newAddresses
    });
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-profile-page" className="max-w-4xl mx-auto">
      <h2 className="text-4xl font-bold mb-2">Профиль компании</h2>
      <p className="text-base text-muted-foreground mb-6">Управление информацией о вашей компании</p>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Company Info Card */}
        <Card className="p-6">
          <h3 className="text-xl font-semibold mb-4">Основная информация</h3>
          
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <Label className="text-sm font-medium text-gray-700 mb-2">Название компании</Label>
              <Input
                value={company?.companyName || ''}
                disabled
                className="bg-gray-50"
              />
              <p className="text-xs text-gray-500 mt-1">Неизменяемое поле</p>
            </div>

            <div>
              <Label className="text-sm font-medium text-gray-700 mb-2">ИНН</Label>
              <Input
                value={company?.inn || ''}
                disabled
                className="bg-gray-50"
              />
              <p className="text-xs text-gray-500 mt-1">Неизменяемое поле</p>
            </div>

            <div>
              <Label htmlFor="phone" className="text-sm font-medium text-gray-700 mb-2">Телефон</Label>
              <Input
                id="phone"
                name="phone"
                type="tel"
                value={formData.phone}
                onChange={handleChange}
                placeholder="+7 (999) 123-45-67"
              />
            </div>

            <div>
              <Label htmlFor="email" className="text-sm font-medium text-gray-700 mb-2">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                value={formData.email}
                onChange={handleChange}
                placeholder="company@example.com"
              />
            </div>

            <div className="md:col-span-2">
              <Label htmlFor="actualAddress" className="text-sm font-medium text-gray-700 mb-2">Фактический адрес</Label>
              <Input
                id="actualAddress"
                name="actualAddress"
                value={formData.actualAddress}
                onChange={handleChange}
                placeholder="Город, улица, дом"
              />
            </div>
          </div>
        </Card>

        {/* Contact Person Card */}
        <Card className="p-6">
          <h3 className="text-xl font-semibold mb-4">Контактное лицо</h3>
          
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <Label htmlFor="contactPersonName" className="text-sm font-medium text-gray-700 mb-2">ФИО</Label>
              <Input
                id="contactPersonName"
                name="contactPersonName"
                value={formData.contactPersonName}
                onChange={handleChange}
                placeholder="Иванов Иван Иванович"
              />
            </div>

            <div>
              <Label htmlFor="contactPersonPhone" className="text-sm font-medium text-gray-700 mb-2">Телефон</Label>
              <Input
                id="contactPersonPhone"
                name="contactPersonPhone"
                type="tel"
                value={formData.contactPersonPhone}
                onChange={handleChange}
                placeholder="+7 (999) 123-45-67"
              />
            </div>
          </div>
        </Card>

        {/* Delivery Addresses Card */}
        <Card className="p-6">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h3 className="text-xl font-semibold">Адреса доставки</h3>
              <p className="text-sm text-muted-foreground mt-1">Добавьте адреса для доставки заказов</p>
            </div>
            <Button
              type="button"
              onClick={addDeliveryAddress}
              variant="outline"
              size="sm"
            >
              <Plus className="h-4 w-4 mr-2" />
              Добавить адрес
            </Button>
          </div>

          <div className="space-y-4">
            {formData.deliveryAddresses.map((deliveryAddr, index) => (
              <Card key={index} className="p-4 bg-gray-50">
                <div className="flex justify-between items-start mb-3">
                  <div className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-gray-500" />
                    <h4 className="font-medium">Адрес {index + 1}</h4>
                  </div>
                  {formData.deliveryAddresses.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeDeliveryAddress(index)}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                <div className="space-y-3">
                  <div>
                    <Label className="text-sm font-medium text-gray-700 mb-1">Адрес доставки</Label>
                    <Input
                      value={deliveryAddr.address}
                      onChange={(e) => updateDeliveryAddress(index, 'address', e.target.value)}
                      placeholder="Город, улица, дом, офис"
                    />
                  </div>

                  <div className="grid md:grid-cols-2 gap-3">
                    <div>
                      <Label className="text-sm font-medium text-gray-700 mb-1">
                        <Phone className="h-3 w-3 inline mr-1" />
                        Телефон
                      </Label>
                      <Input
                        type="tel"
                        value={deliveryAddr.phone}
                        onChange={(e) => updateDeliveryAddress(index, 'phone', e.target.value)}
                        placeholder="+7 (999) 123-45-67"
                      />
                    </div>

                    <div>
                      <Label className="text-sm font-medium text-gray-700 mb-1">
                        <Phone className="h-3 w-3 inline mr-1" />
                        Доп. телефон (необязательно)
                      </Label>
                      <Input
                        type="tel"
                        value={deliveryAddr.additionalPhone || ''}
                        onChange={(e) => updateDeliveryAddress(index, 'additionalPhone', e.target.value)}
                        placeholder="+7 (999) 987-65-43"
                      />
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </Card>

        {/* Action Buttons */}
        <div className="flex gap-4">
          <Button type="submit" disabled={saving} className="flex-1">
            {saving ? 'Сохранение...' : 'Сохранить изменения'}
          </Button>
        </div>

        {/* Success/Error Messages */}
        {message === 'success' && (
          <Alert className="bg-green-50 border-green-200">
            <AlertDescription className="text-green-800">
              ✓ Профиль успешно обновлен
            </AlertDescription>
          </Alert>
        )}
        
        {message === 'error' && (
          <Alert className="bg-red-50 border-red-200">
            <AlertDescription className="text-red-800">
              ✗ Ошибка при сохранении профиля
            </AlertDescription>
          </Alert>
        )}
      </form>
    </div>
  );
};
