import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { FileText, Check, X, Eye, Building2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const SupplierDocuments = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [expandedRestaurant, setExpandedRestaurant] = useState(null);

  // Mock data for demonstration - would come from backend
  const [restaurantDocuments] = useState([
    {
      restaurantId: '1',
      restaurantName: 'Ресторан BestPrice',
      inn: '7701234567',
      documents: [
        { id: '1', type: 'Договор аренды', uploadedAt: '2025-12-10', status: 'uploaded' },
        { id: '2', type: 'Устав', uploadedAt: '2025-12-09', status: 'uploaded' }
      ],
      contractStatus: 'pending' // pending, accepted, declined
    },
    {
      restaurantId: '2',
      restaurantName: 'Ресторан Вкусно',
      inn: '7702345678',
      documents: [
        { id: '3', type: 'Договор аренды', uploadedAt: '2025-12-08', status: 'uploaded' }
      ],
      contractStatus: 'accepted'
    }
  ]);

  const [contractStatuses, setContractStatuses] = useState({});

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      // In real app, fetch documents from backend
      // const response = await axios.get(`${API}/supplier/restaurant-documents`, { headers });
      // setDocuments(response.data);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAcceptContract = async (restaurantId) => {
    try {
      // In real app, send to backend
      // await axios.post(`${API}/supplier/accept-contract`, { restaurantId }, { headers });
      
      setContractStatuses({ ...contractStatuses, [restaurantId]: 'accepted' });
      setMessage('success');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('error');
      setTimeout(() => setMessage(''), 3000);
    }
  };

  const handleDeclineContract = async (restaurantId) => {
    if (!window.confirm('Вы уверены, что хотите отклонить сотрудничество с этим рестораном?')) {
      return;
    }
    
    try {
      setContractStatuses({ ...contractStatuses, [restaurantId]: 'declined' });
      setMessage('declined');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('error');
      setTimeout(() => setMessage(''), 3000);
    }
  };

  const getContractStatus = (restaurant) => {
    return contractStatuses[restaurant.restaurantId] || restaurant.contractStatus;
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="supplier-documents-page" className="max-w-6xl mx-auto">
      <h2 className="text-4xl font-bold mb-2">Документы от ресторанов</h2>
      <p className="text-base text-muted-foreground mb-6">
        Просмотр и принятие документов от ресторанов
      </p>

      {message === 'success' && (
        <Alert className="mb-6 bg-green-50 border-green-200">
          <AlertDescription className="text-green-800">
            ✓ Договор принят
          </AlertDescription>
        </Alert>
      )}
      
      {message === 'declined' && (
        <Alert className="mb-6 bg-red-50 border-red-200">
          <AlertDescription className="text-red-800">
            Сотрудничество отклонено
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-4">
        {restaurantDocuments.map((restaurant) => {
          const status = getContractStatus(restaurant);
          
          return (
            <Card key={restaurant.restaurantId} className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                    <Building2 className="w-6 h-6 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold">{restaurant.restaurantName}</h3>
                    <p className="text-sm text-gray-600">ИНН: {restaurant.inn}</p>
                  </div>
                </div>
                
                {status === 'accepted' ? (
                  <Badge className="bg-green-100 text-green-800">
                    <Check className="h-3 w-3 mr-1" />
                    Договор принят
                  </Badge>
                ) : status === 'declined' ? (
                  <Badge className="bg-red-100 text-red-800">
                    <X className="h-3 w-3 mr-1" />
                    Отклонено
                  </Badge>
                ) : (
                  <Badge className="bg-yellow-100 text-yellow-800">
                    ⏳ Ожидает принятия
                  </Badge>
                )}
              </div>

              {/* Documents List */}
              <div className="mb-4">
                <p className="text-sm font-medium mb-2">Документы ({restaurant.documents.length}):</p>
                <div className="space-y-2">
                  {restaurant.documents.map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-blue-600" />
                        <span className="text-sm font-medium">{doc.type}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-gray-600">
                          {new Date(doc.uploadedAt).toLocaleDateString('ru-RU')}
                        </span>
                        <Button variant="ghost" size="sm">
                          <Eye className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              {status === 'pending' && (
                <div className="flex gap-3 pt-4 border-t">
                  <Button
                    onClick={() => handleAcceptContract(restaurant.restaurantId)}
                    className="flex-1"
                  >
                    <Check className="h-4 w-4 mr-2" />
                    Принять договор
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleDeclineContract(restaurant.restaurantId)}
                    className="flex-1"
                  >
                    <X className="h-4 w-4 mr-2" />
                    Отклонить
                  </Button>
                </div>
              )}

              {status === 'accepted' && (
                <div className="pt-4 border-t">
                  <p className="text-sm text-green-700">
                    ✓ Вы приняли договор с этим рестораном. Теперь они могут размещать у вас заказы.
                  </p>
                </div>
              )}

              {status === 'declined' && (
                <div className="pt-4 border-t">
                  <p className="text-sm text-red-700">
                    Вы отклонили сотрудничество с этим рестораном.
                  </p>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      <Card className="p-6 mt-6 bg-blue-50">
        <h3 className="text-lg font-semibold mb-2">О работе с документами</h3>
        <p className="text-sm text-gray-700">
          Просмотрите документы от ресторанов и примите решение о сотрудничестве.
          После принятия договора, ресторан сможет размещать у вас заказы через платформу BestPrice.
        </p>
      </Card>
    </div>
  );
};
