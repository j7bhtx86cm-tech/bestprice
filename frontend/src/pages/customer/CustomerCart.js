import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
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

// Flag badges mapping (shown ONLY after optimization)
const FLAG_BADGES = {
  'BRAND_REPLACED': { label: 'Бренд заменён', color: 'bg-yellow-100 text-yellow-800', icon: Tag },
  'PACK_TOLERANCE_USED': { label: 'Фасовка ±20%', color: 'bg-blue-100 text-blue-800', icon: Scale },
  'PPU_FALLBACK_USED': { label: 'Расчёт по цене за кг/л', color: 'bg-purple-100 text-purple-800', icon: Scale },
  'MIN_QTY_ROUNDED': { label: 'Округлено до мин. заказа', color: 'bg-gray-100 text-gray-800', icon: Package },
  'STEP_QTY_APPLIED': { label: 'Кратность поставщика', color: 'bg-gray-100 text-gray-800', icon: Package },
  'AUTO_TOPUP_10PCT': { label: 'Кол-во +10% для минималки', color: 'bg-orange-100 text-orange-800', icon: Plus },
  'SUPPLIER_CHANGED': { label: 'Поставщик изменён', color: 'bg-indigo-100 text-indigo-800', icon: Truck },
};

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

// Get category color
const getCategoryColor = (superClass) => {
  if (!superClass) return 'bg-gray-100 text-gray-800';
  if (superClass.startsWith('seafood')) return 'bg-blue-100 text-blue-800';
  if (superClass.startsWith('meat')) return 'bg-red-100 text-red-800';
  if (superClass.startsWith('dairy')) return 'bg-yellow-100 text-yellow-800';
  if (superClass.startsWith('vegetables')) return 'bg-green-100 text-green-800';
  if (superClass.startsWith('fruits')) return 'bg-orange-100 text-orange-800';
  if (superClass.startsWith('canned')) return 'bg-slate-100 text-slate-800';
  return 'bg-gray-100 text-gray-800';
};

// Get unit label
const getUnitLabel = (unitType) => {
  switch(unitType) {
    case 'WEIGHT': return 'кг';
    case 'VOLUME': return 'л';
    default: return 'шт';
  }
};

export const CustomerCart = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  
  // TWO-PHASE CART STATE
  const [cartItems, setCartItems] = useState([]);  // Raw items (exact add-to-cart)
  const [optimizedPlan, setOptimizedPlan] = useState(null);  // Shown only after "Optimize" click
  const [showOptimized, setShowOptimized] = useState(false);  // Toggle between raw/optimized view
  
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [processingOrder, setProcessingOrder] = useState(false);
  const [loading, setLoading] = useState(true);
  const [optimizing, setOptimizing] = useState(false);

  const getUserId = () => user?.id || 'anonymous';
  
  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Load RAW cart items (no optimization!)
  const loadRawCart = useCallback(async () => {
    setLoading(true);
    try {
      const userId = getUserId();
      if (!userId || userId === 'anonymous') {
        setLoading(false);
        return;
      }
      
      // Get RAW intents - exactly what user added
      const response = await axios.get(`${API}/v12/cart/intents?user_id=${userId}`, {
        headers: getHeaders()
      });
      
      const items = response.data.intents || [];
      setCartItems(items);
      
      // Reset optimized view when cart changes
      setShowOptimized(false);
      setOptimizedPlan(null);
      
    } catch (error) {
      console.error('Failed to fetch cart:', error);
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
      loadRawCart();
    }
    fetchCompanyInfo();
  }, [loadRawCart, fetchCompanyInfo, user]);

  // Update quantity (raw, no optimization)
  const updateQuantity = async (supplierItemId, newQty) => {
    if (newQty < 1) return;
    
    try {
      const userId = getUserId();
      await axios.put(`${API}/v12/cart/intent/${supplierItemId}?user_id=${userId}`, 
        { qty: newQty },
        { headers: getHeaders() }
      );
      loadRawCart();
    } catch (error) {
      console.error('Update error:', error);
      toast.error('Ошибка обновления количества');
    }
  };

  // Remove item
  const removeItem = async (supplierItemId) => {
    try {
      const userId = getUserId();
      await axios.delete(`${API}/v12/cart/intent/${supplierItemId}?user_id=${userId}`, {
        headers: getHeaders()
      });
      loadRawCart();
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
      loadRawCart();
      toast.success('Корзина очищена');
    } catch (error) {
      toast.error('Ошибка очистки');
    }
  };

  // PHASE 2: Run optimizer (only when user clicks "Оформить заказ")
  const runOptimization = async () => {
    setOptimizing(true);
    try {
      const userId = getUserId();
      const response = await axios.get(`${API}/v12/cart/plan?user_id=${userId}`, {
        headers: getHeaders()
      });
      setOptimizedPlan(response.data);
      setShowOptimized(true);
    } catch (error) {
      console.error('Optimization failed:', error);
      toast.error('Ошибка оптимизации');
    } finally {
      setOptimizing(false);
    }
  };

  // Handle checkout
  const handleCheckout = async () => {
    // First run optimization if not done
    if (!showOptimized || !optimizedPlan) {
      await runOptimization();
      return; // Show optimization result first, user confirms again
    }
    
    if (!optimizedPlan.success) {
      toast.error(optimizedPlan.blocked_reason || 'Невозможно оформить заказ');
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

  // Cancel optimization view, go back to raw cart
  const cancelOptimization = () => {
    setShowOptimized(false);
    setOptimizedPlan(null);
  };

  // Calculate raw cart totals
  const rawTotal = cartItems.reduce((sum, item) => {
    return sum + (item.price || 0) * (item.qty || 1);
  }, 0);

  // Group raw items by supplier
  const groupedBySupplier = cartItems.reduce((acc, item) => {
    const supplierId = item.supplier_id || 'unknown';
    if (!acc[supplierId]) {
      acc[supplierId] = {
        supplier_name: item.supplier_name || 'Неизвестный поставщик',
        items: []
      };
    }
    acc[supplierId].items.push(item);
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  const hasItems = cartItems.length > 0;

  // ============ OPTIMIZED VIEW (after clicking "Оформить заказ") ============
  if (showOptimized && optimizedPlan) {
    return (
      <div>
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-4xl font-bold mb-2">Подтверждение заказа</h2>
            <p className="text-base text-muted-foreground">
              Оптимизированный план закупки с учётом минималок поставщиков
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={cancelOptimization}>
              ← Назад в корзину
            </Button>
            <Button 
              onClick={handleCheckout} 
              disabled={processingOrder || !optimizedPlan.success || !selectedAddress} 
              size="lg"
              data-testid="confirm-checkout-btn"
            >
              <CheckCircle className="h-4 w-4 mr-2" />
              {processingOrder ? 'Оформление...' : 'Подтвердить заказ'}
            </Button>
          </div>
        </div>

        {/* Blocked Warning */}
        {!optimizedPlan.success && optimizedPlan.blocked_reason && (
          <Card className="p-4 mb-6 border-2 border-red-300 bg-red-50">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-6 w-6 text-red-600 mt-0.5" />
              <div>
                <h3 className="font-semibold text-red-800">Невозможно оформить заказ</h3>
                <p className="text-red-700 mt-1">{optimizedPlan.blocked_reason}</p>
              </div>
            </div>
          </Card>
        )}

        {/* Delivery Address */}
        {company?.deliveryAddresses?.length > 0 && (
          <Card className="p-4 mb-6">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <MapPin className="h-4 w-4" />
              Адрес доставки
            </h3>
            <div className="space-y-2">
              {company.deliveryAddresses.map((addr, idx) => (
                <div 
                  key={idx}
                  onClick={() => setSelectedAddress(addr)}
                  className={`p-3 rounded-lg cursor-pointer transition-colors ${
                    selectedAddress === addr 
                      ? 'bg-blue-50 border-2 border-blue-500' 
                      : 'bg-gray-50 border-2 border-transparent hover:bg-gray-100'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <div className={`w-4 h-4 rounded-full border-2 ${
                      selectedAddress === addr ? 'bg-blue-500 border-blue-500' : 'border-gray-300'
                    }`} />
                    <span>{addr}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Optimized Suppliers (with badges) */}
        {optimizedPlan.suppliers?.map((supplier) => (
          <Card key={supplier.supplier_id} className="p-6 mb-4">
            <div className="flex items-center justify-between mb-4 pb-3 border-b">
              <div className="flex items-center gap-2">
                <Package className="h-5 w-5 text-blue-600" />
                <h3 className="text-lg font-semibold">{supplier.supplier_name}</h3>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold">{supplier.subtotal?.toLocaleString('ru-RU')}₽</div>
                {!supplier.meets_minimum && (
                  <Badge className="bg-red-100 text-red-800 text-xs">
                    Минималка: {supplier.min_order_amount?.toLocaleString('ru-RU')}₽
                  </Badge>
                )}
              </div>
            </div>

            <div className="space-y-3">
              {supplier.items?.map((item, idx) => (
                <div key={idx} className="flex items-center gap-4 py-2 border-b last:border-0">
                  <div className="flex-1">
                    <div className="font-medium">{item.product_name}</div>
                    <div className="text-sm text-gray-500">
                      {item.price?.toLocaleString('ru-RU')}₽ × {item.final_qty} {getUnitLabel(item.unit_type)}
                    </div>
                    {/* FLAGS SHOWN HERE - ONLY IN OPTIMIZED VIEW */}
                    {item.flags?.length > 0 && (
                      <div className="mt-1 flex flex-wrap">
                        {item.flags.map((flag, i) => (
                          <FlagBadge key={i} flag={flag} />
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-right font-semibold">
                    {item.line_total?.toLocaleString('ru-RU')}₽
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}

        {/* Total */}
        <Card className="p-6 bg-gray-50">
          <div className="flex justify-between items-center text-xl font-bold">
            <span>Итого:</span>
            <span>{optimizedPlan.total?.toLocaleString('ru-RU')}₽</span>
          </div>
        </Card>
      </div>
    );
  }

  // ============ RAW CART VIEW (before checkout) ============
  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Корзина</h2>
          <p className="text-base text-muted-foreground">
            {cartItems.length} {cartItems.length === 1 ? 'товар' : 'товаров'} на сумму {rawTotal.toLocaleString('ru-RU')}₽
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
              disabled={optimizing || !hasItems} 
              size="lg"
              data-testid="checkout-btn"
            >
              {optimizing ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Расчёт...
                </>
              ) : (
                <>
                  <ArrowRight className="h-4 w-4 mr-2" />
                  Оформить заказ
                </>
              )}
            </Button>
          )}
        </div>
      </div>

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
          {/* Items grouped by supplier */}
          {Object.entries(groupedBySupplier).map(([supplierId, group]) => (
            <Card key={supplierId} className="p-6">
              {/* Supplier Header */}
              <div className="flex items-center gap-2 mb-4 pb-3 border-b">
                <Package className="h-5 w-5 text-blue-600" />
                <h3 className="text-lg font-semibold">{group.supplier_name}</h3>
              </div>

              {/* Items */}
              <div className="space-y-3">
                {group.items.map((item) => (
                  <div 
                    key={item.supplier_item_id} 
                    className={`flex items-center gap-4 py-3 border-b last:border-0 ${
                      !item.is_available ? 'opacity-50' : ''
                    }`}
                  >
                    {/* Category Badge */}
                    <Badge className={`${getCategoryColor(item.super_class)} text-xs`}>
                      {item.super_class?.split('.')[0] || 'other'}
                    </Badge>

                    {/* Product Info */}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{item.product_name}</div>
                      <div className="text-sm text-gray-500">
                        {item.price?.toLocaleString('ru-RU')}₽ / {getUnitLabel(item.unit_type)}
                      </div>
                      {!item.is_available && (
                        <div className="text-xs text-red-500 mt-1">
                          {item.unavailable_reason || 'Товар недоступен'}
                        </div>
                      )}
                    </div>

                    {/* Quantity Controls - EXACT qty, no auto-changes */}
                    <div className="flex items-center gap-2">
                      <Button 
                        variant="outline" 
                        size="icon" 
                        className="h-8 w-8"
                        onClick={() => updateQuantity(item.supplier_item_id, (item.qty || 1) - 1)}
                        disabled={!item.is_available || (item.qty || 1) <= 1}
                      >
                        <Minus className="h-4 w-4" />
                      </Button>
                      
                      <span className="w-12 text-center font-medium">
                        {item.qty || 1}
                      </span>
                      
                      <Button 
                        variant="outline" 
                        size="icon" 
                        className="h-8 w-8"
                        onClick={() => updateQuantity(item.supplier_item_id, (item.qty || 1) + 1)}
                        disabled={!item.is_available}
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>

                    {/* Line Total */}
                    <div className="text-right w-24">
                      <div className="font-semibold">
                        {((item.price || 0) * (item.qty || 1)).toLocaleString('ru-RU')}₽
                      </div>
                    </div>

                    {/* Remove */}
                    <Button 
                      variant="ghost" 
                      size="icon"
                      className="text-red-500 hover:text-red-700"
                      onClick={() => removeItem(item.supplier_item_id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </Card>
          ))}

          {/* Raw Total */}
          <Card className="p-6 bg-gray-50">
            <div className="flex justify-between items-center">
              <div>
                <div className="text-lg text-gray-600">Итого в корзине:</div>
                <div className="text-sm text-gray-500">
                  * Финальная сумма может измениться с учётом минималок поставщиков
                </div>
              </div>
              <div className="text-2xl font-bold">
                {rawTotal.toLocaleString('ru-RU')}₽
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

export default CustomerCart;
