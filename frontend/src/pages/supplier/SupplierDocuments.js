import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { FileText, Check, X, Building2, ChevronDown, ChevronUp } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

async function handleViewDownload(docId, token) {
  const url = `${API}/documents/${docId}/download`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error('Сессия истекла. Войдите снова.');
    if (res.status === 403) throw new Error('Нет доступа к документу.');
    throw new Error(`Ошибка ${res.status}`);
  }
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('pdf')) {
    window.open(blobUrl, '_blank');
  } else {
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = res.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/)?.[1] || `document-${docId}`;
    a.click();
    URL.revokeObjectURL(blobUrl);
  }
}

export const SupplierDocuments = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [viewError, setViewError] = useState('');
  const [expandedRequisites, setExpandedRequisites] = useState({});
  const [restaurantDocuments, setRestaurantDocuments] = useState([]);

  const toggleRequisites = (restaurantId) => {
    setExpandedRequisites(prev => ({ ...prev, [restaurantId]: !prev[restaurantId] }));
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/supplier/restaurant-documents`, { headers });
      setRestaurantDocuments(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAcceptContract = async (restaurantId) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.post(`${API}/supplier/accept-contract`, { restaurantId }, { headers });
      setMessage('success');
      setTimeout(() => setMessage(''), 3000);
      fetchDocuments();
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
      setMessage('declined');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('error');
      setTimeout(() => setMessage(''), 3000);
    }
  };

  const getContractStatus = (restaurant) => {
    return restaurant.contractStatus;
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
      {viewError && (
        <Alert className="mb-6 bg-red-50 border-red-200">
          <AlertDescription className="text-red-800">{viewError}</AlertDescription>
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

              {/* Restaurant requisites: 4-field preview always + expandable full */}
              {(() => {
                const preview = restaurant.restaurantRequisitesPreview || {};
                const full = restaurant.restaurantRequisitesFull || {};
                const previewKeys = ['companyName', 'inn', 'phone', 'email'];
                const hasPreview = Object.keys(preview).length > 0;
                const hasFull = full && Object.keys(full).length > 0;
                const hasAny = hasPreview || hasFull;
                const expanded = expandedRequisites[restaurant.restaurantId];

                const val = (obj, k) => (obj && obj[k] != null && obj[k] !== '') ? obj[k] : '—';

                if (!hasAny) {
                  return <div className="mb-4 text-sm text-slate-500 italic">Реквизиты не заполнены</div>;
                }
                return (
                  <div className="mb-4">
                    <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-sm text-slate-700">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 mb-2">
                        {previewKeys.map(k => (
                          <div key={k}>
                            <span className="font-medium">{k === 'companyName' ? 'Название' : k === 'inn' ? 'ИНН' : k === 'phone' ? 'Телефон' : 'Email'}:</span>{' '}
                            {val(preview, k)}
                          </div>
                        ))}
                      </div>
                      {hasFull && (
                        <Button
                          variant="link"
                          className="text-blue-600 p-0 h-auto font-medium"
                          onClick={() => toggleRequisites(restaurant.restaurantId)}
                        >
                          {expanded ? (
                            <><ChevronUp className="h-4 w-4 inline mr-1" /> Скрыть реквизиты</>
                          ) : (
                            <><ChevronDown className="h-4 w-4 inline mr-1" /> Показать реквизиты</>
                          )}
                        </Button>
                      )}
                    </div>
                    {expanded && hasFull && (
                      <div className="mt-2 p-4 bg-slate-50 rounded-lg border border-slate-200">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-slate-600">
                          <div><span className="font-medium">Юр. название:</span> {val(full, 'companyName')}</div>
                          <div><span className="font-medium">ИНН:</span> {val(full, 'inn')}</div>
                          <div><span className="font-medium">ОГРН:</span> {val(full, 'ogrn')}</div>
                          <div className="sm:col-span-2"><span className="font-medium">Юр. адрес:</span> {val(full, 'legalAddress')}</div>
                          <div className="sm:col-span-2"><span className="font-medium">Факт. адрес:</span> {val(full, 'actualAddress')}</div>
                          <div><span className="font-medium">Телефон:</span> {val(full, 'phone')}</div>
                          <div><span className="font-medium">Email:</span> {val(full, 'email')}</div>
                          <div><span className="font-medium">Номер ЭДО:</span> {val(full, 'edoNumber')}</div>
                          <div><span className="font-medium">GUID:</span> {val(full, 'guid')}</div>
                          <div><span className="font-medium">Контакт:</span> {val(full, 'contactPersonName')}</div>
                          <div><span className="font-medium">Должность:</span> {val(full, 'contactPersonPosition')}</div>
                          <div><span className="font-medium">Телефон контакта:</span> {val(full, 'contactPersonPhone')}</div>
                          <div className="sm:col-span-2">
                            <span className="font-medium">Адреса доставки:</span>{' '}
                            {Array.isArray(full.deliveryAddresses) && full.deliveryAddresses.length > 0
                              ? full.deliveryAddresses.map((a) => (a.address || a.name || '').trim()).filter(Boolean).join('; ') || '—'
                              : '—'}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Documents List — clickable buttons */}
              <div className="mb-4">
                <p className="text-sm font-medium mb-2">Документы ({restaurant.documents.length}):</p>
                <div className="space-y-2">
                  {restaurant.documents.map((doc) => (
                    <Button
                      key={doc.id}
                      variant="outline"
                      className="w-full justify-start h-auto py-3 px-4 text-left font-normal"
                      onClick={async () => {
                        setViewError('');
                        try {
                          await handleViewDownload(doc.id, localStorage.getItem('token'));
                        } catch (e) {
                          setViewError(e?.message || 'Ошибка просмотра');
                          setTimeout(() => setViewError(''), 4000);
                        }
                      }}
                    >
                      <FileText className="h-4 w-4 mr-2 flex-shrink-0 text-blue-600" />
                      <span className="text-sm font-medium">{doc.type}</span>
                    </Button>
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
