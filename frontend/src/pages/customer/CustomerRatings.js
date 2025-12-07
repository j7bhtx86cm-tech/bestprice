import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Star } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerRatings = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSuppliers();
  }, []);

  const fetchSuppliers = async () => {
    try {
      const response = await axios.get(`${API}/suppliers`);
      setSuppliers(response.data);
    } catch (error) {
      console.error('Failed to fetch suppliers:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRate = (supplierId) => {
    alert(`Оценка поставщика ${supplierId} (функция в разработке)`);
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-ratings-page">
      <h2 className="text-2xl font-bold mb-6">Оценка поставщиков</h2>

      {suppliers.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">Поставщики не найдены</p>
        </Card>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Поставщик</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Контакты</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Текущий рейтинг</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Действия</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {suppliers.map((supplier) => (
                <tr key={supplier.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div>
                      <p className="font-medium">{supplier.companyName}</p>
                      <p className="text-sm text-gray-600">ИНН: {supplier.inn}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <div>
                      <p>{supplier.phone}</p>
                      <p className="text-gray-600">{supplier.email}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                      <span className="font-medium">4.5</span>
                      <span className="text-sm text-gray-600">(12 отзывов)</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRate(supplier.id)}
                      data-testid={`rate-supplier-${supplier.id}`}
                    >
                      <Star className="h-4 w-4 mr-2" />
                      Оценить
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Card className="p-6 mt-6">
        <h3 className="text-lg font-semibold mb-2">О рейтингах</h3>
        <p className="text-gray-600">
          Рейтинг поставщиков формируется на основе отзывов других ресторанов.
          Вы можете оценить поставщика после завершения заказа.
        </p>
      </Card>
    </div>
  );
};