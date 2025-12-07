import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const DAYS_OF_WEEK = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];

export const SupplierSettings = () => {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [formData, setFormData] = useState({
    minOrderAmount: 0,
    deliveryDays: [],
    deliveryTime: '',
    orderReceiveDeadline: '',
    logisticsType: 'own'
  });

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const response = await axios.get(`${API}/supplier-settings/my`);
      setSettings(response.data);
      setFormData({
        minOrderAmount: response.data.minOrderAmount || 0,
        deliveryDays: response.data.deliveryDays || [],
        deliveryTime: response.data.deliveryTime || '',
        orderReceiveDeadline: response.data.orderReceiveDeadline || '',
        logisticsType: response.data.logisticsType || 'own'
      });
    } catch (error) {
      console.error('Failed to fetch settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage('');

    try {
      await axios.put(`${API}/supplier-settings/my`, formData);
      setMessage('Настройки успешно обновлены');
      fetchSettings();
    } catch (error) {
      setMessage('Ошибка при сохранении');
    } finally {
      setSaving(false);
    }
  };

  const toggleDay = (day) => {
    if (formData.deliveryDays.includes(day)) {
      setFormData({
        ...formData,
        deliveryDays: formData.deliveryDays.filter(d => d !== day)
      });
    } else {
      setFormData({
        ...formData,
        deliveryDays: [...formData.deliveryDays, day]
      });
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="supplier-settings-page">
      <h2 className="text-2xl font-bold mb-6">Настройки заказов</h2>

      {message && (
        <Alert className="mb-4" variant={message.includes('успешно') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <Label htmlFor="minOrderAmount">Минимальная сумма заказа (руб.)</Label>
          <Input
            id="minOrderAmount"
            type="number"
            value={formData.minOrderAmount}
            onChange={(e) => setFormData({ ...formData, minOrderAmount: parseFloat(e.target.value) })}
          />
        </div>

        <div>
          <Label>Дни доставки</Label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
            {DAYS_OF_WEEK.map((day) => (
              <div key={day} className="flex items-center space-x-2">
                <Checkbox
                  id={day}
                  checked={formData.deliveryDays.includes(day)}
                  onCheckedChange={() => toggleDay(day)}
                />
                <Label htmlFor={day} className="text-sm cursor-pointer">{day}</Label>
              </div>
            ))}
          </div>
        </div>

        <div>
          <Label htmlFor="deliveryTime">Время доставки</Label>
          <Input
            id="deliveryTime"
            placeholder="напр. 10:00 - 18:00"
            value={formData.deliveryTime}
            onChange={(e) => setFormData({ ...formData, deliveryTime: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="orderReceiveDeadline">Крайний срок приема заказов</Label>
          <Input
            id="orderReceiveDeadline"
            placeholder="напр. 16:00 предыдущего дня"
            value={formData.orderReceiveDeadline}
            onChange={(e) => setFormData({ ...formData, orderReceiveDeadline: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="logisticsType">Тип логистики</Label>
          <Select value={formData.logisticsType} onValueChange={(value) => setFormData({ ...formData, logisticsType: value })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="own">Собственная</SelectItem>
              <SelectItem value="transport company">Транспортная компания</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button type="submit" disabled={saving} data-testid="save-settings-btn">
          {saving ? 'Сохранение...' : 'Сохранить'}
        </Button>
      </form>
    </div>
  );
};