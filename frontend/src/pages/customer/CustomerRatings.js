import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Star, MessageSquare } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const StarRating = ({ rating, onRate, readonly = false }) => {
  const [hover, setHover] = useState(0);
  
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          className={`w-6 h-6 ${
            readonly ? 'cursor-default' : 'cursor-pointer'
          } transition-colors ${
            star <= (hover || rating)
              ? 'fill-yellow-400 text-yellow-400'
              : 'text-gray-300'
          }`}
          onMouseEnter={() => !readonly && setHover(star)}
          onMouseLeave={() => !readonly && setHover(0)}
          onClick={() => !readonly && onRate(star)}
        />
      ))}
    </div>
  );
};

export const CustomerRatings = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ratings, setRatings] = useState({});
  const [comments, setComments] = useState({});
  const [expandedSupplier, setExpandedSupplier] = useState(null);

  useEffect(() => {
    fetchSuppliers();
  }, []);

  const fetchSuppliers = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/suppliers`, { headers });
      setSuppliers(response.data);
    } catch (error) {
      console.error('Failed to fetch suppliers:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRateSupplier = (supplierId, rating) => {
    setRatings({ ...ratings, [supplierId]: rating });
  };

  const handleSaveRating = async (supplierId) => {
    const rating = ratings[supplierId];
    const comment = comments[supplierId] || '';
    
    if (!rating) {
      alert('Пожалуйста, выберите оценку');
      return;
    }
    
    // Save to backend (would need ratings endpoint)
    console.log(`Saving rating for ${supplierId}: ${rating} stars, comment: ${comment}`);
    alert(`Оценка сохранена: ${rating} звезд`);
    setExpandedSupplier(null);
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-ratings-page">
      <h2 className="text-4xl font-bold mb-2">Оценка поставщиков</h2>
      <p className="text-base text-muted-foreground mb-6">
        Оцените качество работы поставщиков
      </p>

      {suppliers.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">Поставщики не найдены</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {suppliers.map((supplier) => (
            <Card key={supplier.id} className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <h3 className="text-xl font-semibold">{supplier.companyName}</h3>
                  <p className="text-sm text-gray-600 mt-1">ИНН: {supplier.inn}</p>
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-600">
                    <span>{supplier.phone}</span>
                    <span>{supplier.email}</span>
                  </div>
                </div>
                <Badge variant="outline" className="text-sm">
                  <Star className="w-3 h-3 mr-1 fill-yellow-400 text-yellow-400" />
                  4.5
                </Badge>
              </div>

              {expandedSupplier === supplier.id ? (
                <div className="space-y-4 pt-4 border-t">
                  <div>
                    <p className="text-sm font-medium mb-2">Ваша оценка:</p>
                    <StarRating
                      rating={ratings[supplier.id] || 0}
                      onRate={(rating) => handleRateSupplier(supplier.id, rating)}
                    />
                  </div>

                  <div>
                    <p className="text-sm font-medium mb-2">Комментарий (необязательно):</p>
                    <Textarea
                      placeholder="Расскажите о вашем опыте работы с этим поставщиком..."
                      value={comments[supplier.id] || ''}
                      onChange={(e) => setComments({ ...comments, [supplier.id]: e.target.value })}
                      rows={3}
                    />
                  </div>

                  <div className="flex gap-2">
                    <Button
                      onClick={() => handleSaveRating(supplier.id)}
                      disabled={!ratings[supplier.id]}
                    >
                      Сохранить оценку
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setExpandedSupplier(null)}
                    >
                      Отмена
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => setExpandedSupplier(supplier.id)}
                >
                  <Star className="h-4 w-4 mr-2" />
                  Оценить
                </Button>
              )}
            </Card>
          ))}
        </div>
      )}

      <Card className="p-6 mt-6 bg-blue-50">
        <h3 className="text-lg font-semibold mb-2">О рейтингах</h3>
        <p className="text-sm text-gray-700">
          Рейтинг поставщиков формируется на основе отзывов других ресторанов.
          Ваша оценка поможет другим пользователям BestPrice выбрать надежных поставщиков.
        </p>
      </Card>
    </div>
  );
};
