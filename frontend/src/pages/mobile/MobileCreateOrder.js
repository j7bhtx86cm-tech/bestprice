import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, Trash2, ArrowRight, X } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const MobileCreateOrder = () => {
  const navigate = useNavigate();
  const [positionNumber, setPositionNumber] = useState('');
  const [quantity, setQuantity] = useState('');
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');

  const addItem = () => {
    if (!positionNumber || !quantity) {
      setError('Заполните позицию и количество');
      return;
    }

    const qty = parseFloat(quantity);
    if (qty <= 0) {
      setError('Количество должно быть больше 0');
      return;
    }

    setItems([...items, { position_number: positionNumber, qty }]);
    setPositionNumber('');
    setQuantity('');
    setError('');
  };

  const removeItem = (index) => {
    setItems(items.filter((_, i) => i !== index));
  };

  const handlePreview = () => {
    if (items.length === 0) {
      setError('Добавьте хотя бы один товар');
      return;
    }
    
    // Store items in sessionStorage and navigate
    sessionStorage.setItem('mobile_order_items', JSON.stringify(items));
    navigate('/app/order/preview');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addItem();
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b p-4 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-bold">Новый заказ</h1>
          <Button variant="ghost" size="sm" onClick={() => navigate('/app/home')}>
            <X className="h-5 w-5" />
          </Button>
        </div>
      </div>

      <div className="max-w-2xl mx-auto p-4 space-y-4">
        {/* Add Item Card */}
        <Card className="p-4">
          <h3 className="font-semibold mb-4">Добавить товар</h3>
          
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium mb-1 block">Номер позиции</label>
              <Input
                type="text"
                inputMode="numeric"
                value={positionNumber}
                onChange={(e) => setPositionNumber(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Например: 15"
                className="h-12 text-lg"
                autoFocus
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1 block">Количество</label>
              <Input
                type="number"
                step="0.1"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Например: 3"
                className="h-12 text-lg"
              />
            </div>

            <p className="text-xs text-gray-500">
              Введите номер позиции из каталога и количество (в кг или шт, как в каталоге)
            </p>

            <Button onClick={addItem} className="w-full h-12" size="lg">
              <Plus className="h-5 w-5 mr-2" />
              Добавить в список
            </Button>
          </div>
        </Card>

        {/* Items List */}
        {items.length > 0 && (
          <Card className="p-4">
            <h3 className="font-semibold mb-3">Список товаров ({items.length})</h3>
            <div className="space-y-2">
              {items.map((item, index) => (
                <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium">Позиция: {item.position_number}</p>
                    <p className="text-sm text-gray-600">Количество: {item.qty}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeItem(index)}
                    className="text-red-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Bottom Actions */}
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t p-4 space-y-2">
          <Button
            onClick={handlePreview}
            disabled={items.length === 0}
            className="w-full h-12"
            size="lg"
          >
            Просмотр заказа
            <ArrowRight className="h-5 w-5 ml-2" />
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate('/app/home')}
            className="w-full h-12"
          >
            Отмена
          </Button>
        </div>

        {/* Spacer for fixed bottom */}
        <div className="h-32"></div>
      </div>
    </div>
  );
};
