import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  ShoppingCart, Trash2, Plus, Minus, Package, MapPin, 
  RefreshCw, AlertTriangle, CheckCircle, ArrowRight,
  Tag, Scale, Truck
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Flag badges mapping
const FLAG_BADGES = {
  'BRAND_REPLACED': { label: 'Бренд заменён', color: 'bg-yellow-100 text-yellow-800', icon: Tag },
  'PACK_TOLERANCE_USED': { label: 'Фасовка ±20%', color: 'bg-blue-100 text-blue-800', icon: Scale },
  'PPU_FALLBACK_USED': { label: 'Расчёт по цене за кг/л', color: 'bg-purple-100 text-purple-800', icon: Scale },
  'MIN_QTY_ROUNDED': { label: 'Округлено до мин. заказа', color: 'bg-gray-100 text-gray-800', icon: Package },
  'STEP_QTY_APPLIED': { label: 'Кратность поставщика', color: 'bg-gray-100 text-gray-800', icon: Package },
  'AUTO_TOPUP_10PCT': { label: 'Кол-во +10% для минималки', color: 'bg-orange-100 text-orange-800', icon: Plus },
  'SUPPLIER_CHANGED': { label: 'Поставщик изменён', color: 'bg-indigo-100 text-indigo-800', icon: Truck },
};

// Flag Badge Component
const FlagBadge = ({ flag }) => {
  const config = FLAG_BADGES[flag];
  if (!config) return null;
  
  const Icon = config.icon;
  return (
    <Badge className={`${config.color} text-xs mr-1 mb-1`}>
      <Icon className="h-3 w-3 mr-1" />
      {config.label}
    </Badge>
  );
};

export const CustomerCart = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [plan, setPlan] = useState(null);
  const [intents, setIntents] = useState([]);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [processingOrder, setProcessingOrder] = useState(false);
  const [loading, setLoading] = useState(true);

  const getUserId = () => user?.id || 'anonymous';
  
  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Load cart plan from optimizer
  const loadPlan = useCallback(async () => {
    setLoading(true);
    try {
      const userId = getUserId();
      if (!userId || userId === 'anonymous') {
        setLoading(false);
        return;
      }
      
      // Get optimized plan
      const planResponse = await axios.get(`${API}/v12/cart/plan?user_id=${userId}`, {
        headers: getHeaders()
      });
      setPlan(planResponse.data);
      
      // Also get raw intents
      const intentsResponse = await axios.get(`${API}/v12/cart/intents?user_id=${userId}`, {
        headers: getHeaders()
      });
      setIntents(intentsResponse.data.intents || []);
      
    } catch (error) {
      console.error('Failed to fetch cart plan:', error);
      toast.error('Ошибка загрузки корзины');
    } finally {
      setLoading(false);
    }
  }, [user]);

  const fetchCompanyInfo = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/companies/my`, { headers: getHeaders() });
      setCompany(response.data);
      if (response.data.deliveryAddresses?.length === 1) {
        setSelectedAddress(response.data.deliveryAddresses[0]);
      }
    } catch (error) {
      console.error('Failed to fetch company:', error);
    }
  }, []);

  useEffect(() => {
    if (user?.id) {
      loadPlan();
    }
    fetchCompanyInfo();
  }, [loadPlan, fetchCompanyInfo, user]);

  // Update quantity
  const updateQuantity = async (referenceId, newQty) => {
    if (newQty < 1) return;
    
    try {
      const userId = getUserId();
      await axios.put(`${API}/v12/cart/intent/${referenceId}?user_id=${userId}`, 
        { qty: newQty },
        { headers: getHeaders() }
      );
      // Reload plan to see optimizer results
      loadPlan();
    } catch (error) {
      console.error('Update error:', error);
      toast.error('Ошибка обновления количества');
    }
  };

  // Remove item
  const removeItem = async (referenceId) => {
    try {
      const userId = getUserId();
      await axios.delete(`${API}/v12/cart/intent/${referenceId}?user_id=${userId}`, {
        headers: getHeaders()
      });
      loadPlan();
      toast.success('Удалено из корзины');
    } catch (error) {
      toast.error('Ошибка удаления');
    }
  };

  // Clear cart
  const clearCart = async () => {
    if (!confirm('Очистить корзину?')) return;
    
    try {
      const userId = getUserId();
      await axios.delete(`${API}/v12/cart/intents?user_id=${userId}`, {
        headers: getHeaders()
      });
      loadPlan();
      toast.success('Корзина очищена');
    } catch (error) {
      toast.error('Ошибка очистки');
    }
  };

  // Handle checkout
  const handleCheckout = async () => {
    if (!plan || !plan.success) {
      toast.error(plan?.blocked_reason || 'Невозможно оформить заказ');
      return;
    }

    if (!selectedAddress) {
      toast.error('Выберите адрес доставки');
      return;
    }

    setProcessingOrder(true);
    try {
      const userId = getUserId();
      const response = await axios.post(
        `${API}/v12/cart/checkout?user_id=${userId}`,
        {},
        { headers: getHeaders() }
      );
      
      if (response.data.status === 'ok') {
        toast.success(`✓ Создано ${response.data.orders?.length || 0} заказов на сумму ${response.data.total?.toLocaleString('ru-RU')}₽`);
        // Navigate with checkout info for success banner
        navigate('/customer/orders', {
          state: {
            fromCheckout: true,
            checkoutInfo: {
              ordersCount: response.data.orders?.length || 0,
              total: response.data.total,
              orders: response.data.orders
            }
          }
        });
      } else {
        toast.error(response.data.message || 'Ошибка создания заказа');
      }
    } catch (error) {
      console.error('Checkout error:', error);
      toast.error('Ошибка создания заказа');
    } finally {
      setProcessingOrder(false);
    }
  };

  // Find intent for reference
  const findIntent = (referenceId) => {
    return intents.find(i => i.reference_id === referenceId);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  const hasItems = plan?.suppliers?.length > 0 || intents.length > 0;
  const canCheckout = plan?.success && hasItems;

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Корзина</h2>
          <p className="text-base text-muted-foreground">
            Оптимизированный план закупки
          </p>
        </div>
        <div className="flex gap-2">
          {hasItems && (
            <Button variant="outline" onClick={clearCart}>
              <Trash2 className="h-4 w-4 mr-2" />
              Очистить
            </Button>
          )}
          {hasItems && (
            <Button 
              onClick={handleCheckout} 
              disabled={processingOrder || !canCheckout || !selectedAddress} 
              size="lg"
              data-testid="checkout-btn"
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              {processingOrder ? 'Оформление...' : `Оформить заказ`}
            </Button>
          )}
        </div>
      </div>

      {/* Blocked Warning */}
      {plan && !plan.success && plan.blocked_reason && (
        <Card className="p-4 mb-6 border-2 border-red-300 bg-red-50">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-6 w-6 text-red-600 mt-0.5" />
            <div>
              <h3 className="font-semibold text-red-800">Невозможно оформить заказ</h3>
              <p className="text-red-700 mt-1">{plan.blocked_reason}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Unmatched Items Warning */}
      {plan?.unmatched_intents?.length > 0 && (
        <Card className="p-4 mb-6 border-2 border-yellow-300 bg-yellow-50">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-6 w-6 text-yellow-600 mt-0.5" />
            <div>
              <h3 className="font-semibold text-yellow-800">Некоторые товары не найдены</h3>
              <p className="text-yellow-700 mt-1">
                {plan.unmatched_intents.length} позиций не удалось подобрать у поставщиков
              </p>
            </div>
          </div>
        </Card>
      )}

      {!hasItems ? (
        <Card className="p-12 text-center">
          <ShoppingCart className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">Корзина пуста</p>
          <p className="text-sm text-gray-500 mb-4">Добавьте товары из каталога или избранного</p>
          <div className="flex gap-2 justify-center">
            <Button variant="outline" onClick={() => navigate('/customer/catalog')}>
              Перейти в каталог
            </Button>
            <Button variant="outline" onClick={() => navigate('/customer/favorites')}>
              Перейти в избранное
            </Button>
          </div>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Suppliers */}
          {plan?.suppliers?.map((supplier) => (
            <Card key={supplier.supplier_id} className="p-6">
              {/* Supplier Header */}
              <div className="flex items-center justify-between mb-4 pb-3 border-b">
                <div className="flex items-center gap-2">
                  <Package className="h-5 w-5 text-blue-600" />
                  <h3 className="text-lg font-semibold">{supplier.supplier_name}</h3>
                  <Badge className="ml-2">
                    {supplier.items?.length || 0} товаров
                  </Badge>
                </div>
                
                {/* Minimum Status */}
                <div className="flex items-center gap-3">
                  {supplier.meets_minimum ? (
                    <div className="flex items-center text-green-600">
                      <CheckCircle className="h-4 w-4 mr-1" />
                      <span className="text-sm">Минималка выполнена</span>
                    </div>
                  ) : (
                    <div className="flex items-center text-red-600">
                      <AlertTriangle className="h-4 w-4 mr-1" />
                      <span className="text-sm">
                        Не хватает {supplier.deficit?.toLocaleString('ru-RU')}₽ до минималки
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Items */}
              <div className="space-y-3">
                {supplier.items?.map((item, idx) => {
                  const intent = findIntent(item.reference_id);
                  const userQty = intent?.qty || item.user_qty;
                  
                  return (
                    <div key={idx} className="flex items-start gap-4 p-4 border rounded-lg">
                      <div className="flex-1">
                        <p className="font-medium">{item.product_name}</p>
                        <p className="text-sm text-gray-600">
                          {item.price?.toLocaleString('ru-RU')} ₽ / 
                          {item.unit_type === 'WEIGHT' ? 'кг' : item.unit_type === 'VOLUME' ? 'л' : 'шт'}
                        </p>
                        
                        {/* Flags */}
                        {item.flags?.length > 0 && (
                          <div className="mt-2 flex flex-wrap">
                            {item.flags.map((flag, i) => (
                              <FlagBadge key={i} flag={flag} />
                            ))}
                          </div>
                        )}
                        
                        {/* Qty difference indicator */}
                        {item.final_qty !== userQty && (
                          <p className="text-xs text-orange-600 mt-1">
                            Запрошено: {userQty}, будет заказано: {item.final_qty}
                          </p>
                        )}
                      </div>
                      
                      {/* Quantity Controls */}
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => updateQuantity(item.reference_id, Math.max(1, userQty - 1))}
                        >
                          <Minus className="h-4 w-4" />
                        </Button>
                        <Input
                          type="number"
                          min="1"
                          step="1"
                          value={userQty}
                          onChange={(e) => {
                            const val = parseInt(e.target.value) || 1;
                            updateQuantity(item.reference_id, val);
                          }}
                          className="w-20 text-center"
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => updateQuantity(item.reference_id, userQty + 1)}
                        >
                          <Plus className="h-4 w-4" />
                        </Button>
                      </div>

                      {/* Line Total */}
                      <div className="text-right w-28">
                        <p className="font-semibold">
                          {item.line_total?.toLocaleString('ru-RU')} ₽
                        </p>
                      </div>

                      {/* Remove Button */}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeItem(item.reference_id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  );
                })}
              </div>

              {/* Supplier Subtotal */}
              <div className="mt-4 pt-4 border-t flex justify-between items-center">
                <div>
                  <span className="font-medium">Итого у {supplier.supplier_name}:</span>
                  <span className="text-sm text-gray-500 ml-2">
                    (мин. заказ: {supplier.min_order_amount?.toLocaleString('ru-RU')}₽)
                  </span>
                </div>
                <span className={`text-xl font-bold ${supplier.meets_minimum ? 'text-green-600' : 'text-red-600'}`}>
                  {supplier.subtotal?.toLocaleString('ru-RU')} ₽
                </span>
              </div>
            </Card>
          ))}

          {/* Total */}
          <Card className="p-6 bg-blue-50">
            <div className="flex justify-between items-center">
              <div>
                <p className="text-lg font-semibold">Общая сумма заказа:</p>
                <p className="text-sm text-gray-600">
                  {intents.length} позиций от {plan?.suppliers?.length || 0} поставщиков
                </p>
              </div>
              <p className="text-3xl font-bold text-blue-600">
                {plan?.total?.toLocaleString('ru-RU')} ₽
              </p>
            </div>
          </Card>

          {/* Delivery Address Selection */}
          <Card className="p-6 border-2 border-blue-200">
            <div className="flex items-start gap-3 mb-4">
              <MapPin className="h-6 w-6 text-blue-600 mt-1" />
              <div className="flex-1">
                <h3 className="text-lg font-semibold mb-1">Адрес доставки</h3>
                <p className="text-sm text-gray-600">Выберите ресторан для доставки заказа</p>
              </div>
            </div>
            
            {!company?.deliveryAddresses || company.deliveryAddresses.length === 0 ? (
              <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">
                  ⚠️ Адреса доставки не настроены. Добавьте адреса в профиле компании.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {company.deliveryAddresses.map((addr, idx) => (
                  <label
                    key={idx}
                    className={`flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all ${
                      selectedAddress?.address === addr.address 
                        ? 'border-blue-500 bg-blue-50' 
                        : 'border-gray-200 hover:border-blue-300'
                    }`}
                  >
                    <input
                      type="radio"
                      name="deliveryAddress"
                      className="mt-1"
                      checked={selectedAddress?.address === addr.address}
                      onChange={() => setSelectedAddress(addr)}
                    />
                    <div className="flex-1">
                      <p className="font-medium">{addr.name || `Адрес ${idx + 1}`}</p>
                      <p className="text-sm text-gray-600">{addr.address}</p>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </Card>

          {/* Bottom checkout button */}
          <Button 
            onClick={handleCheckout} 
            disabled={processingOrder || !canCheckout || !selectedAddress} 
            size="lg"
            className="w-full"
            data-testid="checkout-btn-bottom"
          >
            <ShoppingCart className="h-4 w-4 mr-2" />
            {processingOrder ? 'Оформление...' : `Оформить заказ (${plan?.total?.toLocaleString('ru-RU')} ₽)`}
          </Button>
        </div>
      )}
    </div>
  );
};

export default CustomerCart;
