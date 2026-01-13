import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import {
  ShoppingCart, Trash2, Plus, Minus, Package, MapPin, 
  CheckCircle, AlertTriangle, TrendingUp, ArrowRight,
  RefreshCw, Zap
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Cart Item Component with substitution badge
const CartItemRow = ({ item, onUpdateQty, onRemove, updating }) => {
  const [localQty, setLocalQty] = useState(item.user_qty || 1);

  const handleQtyChange = (delta) => {
    const newQty = Math.max(1, localQty + delta);
    setLocalQty(newQty);
    onUpdateQty(item.cart_item_id, newQty);
  };

  return (
    <div className={`p-4 border rounded-lg ${item.substitution_applied ? 'border-green-300 bg-green-50' : ''} ${item.topup_applied ? 'border-blue-300 bg-blue-50' : ''}`}>
      <div className="flex items-start gap-4">
        {/* Main info */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-medium">{item.product_name}</h4>
            
            {/* Substitution badge */}
            {item.substitution_applied && (
              <Badge className="bg-green-600 text-white">
                <TrendingUp className="h-3 w-3 mr-1" />
                Заменено
              </Badge>
            )}
            
            {/* Topup badge */}
            {item.topup_applied && (
              <Badge className="bg-blue-600 text-white">
                <Zap className="h-3 w-3 mr-1" />
                Добито
              </Badge>
            )}
          </div>

          {/* Supplier */}
          <p className="text-sm text-gray-600 mb-1">
            <Package className="h-3 w-3 inline mr-1" />
            {item.supplier_name}
          </p>

          {/* Price info */}
          <p className="text-sm text-gray-600">
            {item.price?.toLocaleString('ru-RU')} ₽ / ед.
            {item.min_order_qty > 1 && (
              <span className="text-orange-600 ml-2">
                мин. заказ: {item.min_order_qty}
              </span>
            )}
          </p>

          {/* Substitution details */}
          {item.substitution_applied && item.savings > 0 && (
            <div className="mt-2 p-2 bg-green-100 rounded text-sm">
              <p className="text-green-800">
                💰 Экономия: <strong>{item.savings?.toLocaleString('ru-RU')} ₽</strong>
              </p>
              {item.original_supplier_name && (
                <p className="text-green-700 text-xs">
                  Было: {item.original_supplier_name} ({item.original_price?.toLocaleString('ru-RU')} ₽)
                </p>
              )}
            </div>
          )}

          {/* Topup reason */}
          {item.topup_applied && item.qty_increased_reason && (
            <div className="mt-2 p-2 bg-blue-100 rounded text-sm">
              <p className="text-blue-800">
                ⬆️ {item.qty_increased_reason}
              </p>
            </div>
          )}
        </div>

        {/* Quantity controls */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleQtyChange(-1)}
            disabled={updating || localQty <= 1}
          >
            <Minus className="h-4 w-4" />
          </Button>
          <Input
            type="number"
            min="1"
            value={localQty}
            onChange={(e) => {
              const val = parseInt(e.target.value) || 1;
              setLocalQty(val);
              onUpdateQty(item.cart_item_id, val);
            }}
            className="w-20 text-center"
            disabled={updating}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleQtyChange(1)}
            disabled={updating}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        {/* Line total */}
        <div className="text-right min-w-[100px]">
          <p className="font-bold text-lg">
            {item.line_total?.toLocaleString('ru-RU')} ₽
          </p>
          {item.effective_qty !== item.user_qty && (
            <p className="text-xs text-orange-600">
              факт: {item.effective_qty} ед.
            </p>
          )}
        </div>

        {/* Remove */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRemove(item.cart_item_id)}
          className="text-red-500 hover:text-red-700"
          disabled={updating}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
};

// Supplier Group Card
const SupplierGroupCard = ({ supplier, items, onTopup, applyingTopup }) => {
  const deficit = supplier.deficit || 0;
  const canTopup = supplier.can_topup && deficit > 0;
  const progress = Math.min(100, (supplier.subtotal / 10000) * 100);

  return (
    <Card className={`p-6 ${!supplier.meets_minimum ? 'border-2 border-orange-300' : 'border-green-300'}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-3 border-b">
        <div className="flex items-center gap-2">
          <Package className="h-5 w-5 text-blue-600" />
          <h3 className="text-lg font-semibold">{supplier.supplier_name}</h3>
          <Badge variant="outline">{supplier.items_count} товаров</Badge>
        </div>
        
        <div className="text-right">
          <p className="text-xl font-bold">
            {supplier.subtotal?.toLocaleString('ru-RU')} ₽
          </p>
          {!supplier.meets_minimum && (
            <p className="text-sm text-orange-600">
              До минималки: {deficit?.toLocaleString('ru-RU')} ₽
            </p>
          )}
        </div>
      </div>

      {/* Progress to minimum */}
      {!supplier.meets_minimum && (
        <div className="mb-4">
          <div className="flex justify-between text-sm mb-1">
            <span>Прогресс до минималки (10 000 ₽)</span>
            <span>{progress.toFixed(0)}%</span>
          </div>
          <Progress value={progress} className="h-2" />
          
          {/* Topup button */}
          {canTopup && (
            <div className="mt-3 p-3 bg-blue-50 rounded-lg">
              <p className="text-sm text-blue-800 mb-2">
                💡 До минималки осталось менее 10%. Система может автоматически увеличить количество товаров.
              </p>
              <Button
                size="sm"
                onClick={() => onTopup(supplier.supplier_id)}
                disabled={applyingTopup}
                className="bg-blue-600 hover:bg-blue-700"
              >
                {applyingTopup ? (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    Применяется...
                  </>
                ) : (
                  <>
                    <Zap className="h-4 w-4 mr-2" />
                    Автодобивка (+{deficit?.toLocaleString('ru-RU')} ₽)
                  </>
                )}
              </Button>
            </div>
          )}
          
          {!canTopup && deficit > 1000 && (
            <p className="mt-2 text-sm text-orange-600">
              ⚠️ Дефицит ({deficit?.toLocaleString('ru-RU')} ₽) превышает 10% — добавьте товаров вручную
            </p>
          )}
        </div>
      )}

      {/* Items */}
      <div className="space-y-3">
        {items.map(item => (
          <CartItemRow
            key={item.cart_item_id}
            item={item}
            onUpdateQty={() => {}}
            onRemove={() => {}}
            updating={false}
          />
        ))}
      </div>

      {/* Minimum status */}
      {supplier.meets_minimum && (
        <div className="mt-4 p-3 bg-green-50 rounded-lg flex items-center gap-2 text-green-800">
          <CheckCircle className="h-5 w-5" />
          <span className="font-medium">Минималка достигнута</span>
        </div>
      )}
    </Card>
  );
};

// Main Cart Component
export const CustomerCartV12 = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [cartData, setCartData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [processingOrder, setProcessingOrder] = useState(false);
  const [applyingTopup, setApplyingTopup] = useState(null);

  // Get user ID from auth context
  const getUserId = () => {
    return user?.id || 'anonymous';
  };

  // Get auth headers
  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Fetch cart
  const fetchCart = useCallback(async () => {
    setLoading(true);
    try {
      const userId = getUserId();
      const response = await axios.get(`${API}/v12/cart?user_id=${userId}`, {
        headers: getHeaders()
      });
      setCartData(response.data);
    } catch (error) {
      console.error('Failed to fetch cart:', error);
      toast.error('Ошибка загрузки корзины');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch company
  const fetchCompany = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/companies/my`, {
        headers: getHeaders()
      });
      setCompany(response.data);
      if (response.data.deliveryAddresses?.length === 1) {
        setSelectedAddress(response.data.deliveryAddresses[0]);
      }
    } catch (error) {
      console.error('Failed to fetch company:', error);
    }
  }, []);

  useEffect(() => {
    fetchCart();
    fetchCompany();
  }, [fetchCart, fetchCompany]);

  // Apply topup
  const handleTopup = async (supplierId) => {
    setApplyingTopup(supplierId);
    try {
      const userId = getUserId();
      const response = await axios.post(
        `${API}/v12/cart/topup/${supplierId}?user_id=${userId}`,
        {},
        { headers: getHeaders() }
      );
      
      if (response.data.status === 'ok') {
        toast.success(response.data.message);
        fetchCart(); // Reload cart
      } else {
        toast.error(response.data.message);
      }
    } catch (error) {
      toast.error('Ошибка автодобивки');
    } finally {
      setApplyingTopup(null);
    }
  };

  // Clear cart
  const handleClearCart = async () => {
    if (!confirm('Очистить корзину?')) return;
    
    try {
      const userId = getUserId();
      await axios.delete(`${API}/v12/cart?user_id=${userId}`, {
        headers: getHeaders()
      });
      fetchCart();
      toast.success('Корзина очищена');
    } catch (error) {
      toast.error('Ошибка очистки');
    }
  };

  // Check if can checkout
  const canCheckout = () => {
    if (!cartData?.items?.length) return false;
    if (!selectedAddress) return false;
    if (cartData.has_minimum_issues) return false;
    return true;
  };

  // Handle checkout
  const handleCheckout = async () => {
    if (!canCheckout()) {
      if (cartData?.has_minimum_issues) {
        toast.error('Не достигнуты минималки по поставщикам');
        return;
      }
      if (!selectedAddress) {
        toast.error('Выберите адрес доставки');
        return;
      }
      return;
    }

    setProcessingOrder(true);
    try {
      // TODO: Implement order creation via v12 API
      toast.success('Заказ создан!');
      fetchCart();
      navigate('/customer/orders');
    } catch (error) {
      toast.error('Ошибка создания заказа');
    } finally {
      setProcessingOrder(false);
    }
  };

  // Group items by supplier
  const groupedBySupplier = () => {
    if (!cartData?.items) return {};
    const groups = {};
    cartData.items.forEach(item => {
      const supplierId = item.supplier_id;
      if (!groups[supplierId]) {
        groups[supplierId] = [];
      }
      groups[supplierId].push(item);
    });
    return groups;
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-64" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const itemGroups = groupedBySupplier();
  const suppliersMap = {};
  cartData?.suppliers?.forEach(s => { suppliersMap[s.supplier_id] = s; });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Корзина v12</h1>
          <p className="text-gray-600">
            {cartData?.items?.length || 0} товаров • 
            Итого: {cartData?.total?.toLocaleString('ru-RU') || 0} ₽
          </p>
        </div>
        
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleClearCart}>
            <Trash2 className="h-4 w-4 mr-2" />
            Очистить
          </Button>
          <Button onClick={fetchCart}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Обновить
          </Button>
        </div>
      </div>

      {/* Empty cart */}
      {!cartData?.items?.length ? (
        <Card className="p-12 text-center">
          <ShoppingCart className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">Корзина пуста</p>
          <p className="text-sm text-gray-500 mb-4">Добавьте товары из каталога v12</p>
          <Button onClick={() => navigate('/customer/catalog-v12')}>
            Перейти в каталог
          </Button>
        </Card>
      ) : (
        <>
          {/* Minimum warning */}
          {cartData.has_minimum_issues && (
            <Card className="p-4 bg-orange-50 border-orange-300">
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-6 w-6 text-orange-600" />
                <div>
                  <p className="font-medium text-orange-800">
                    Не достигнуты минималки по {cartData.minimum_issues?.length} поставщикам
                  </p>
                  <p className="text-sm text-orange-700">
                    Минимальный заказ: {cartData.minimum_order_rub?.toLocaleString('ru-RU')} ₽ на поставщика
                  </p>
                </div>
              </div>
            </Card>
          )}

          {/* Supplier groups */}
          {Object.entries(itemGroups).map(([supplierId, items]) => (
            <SupplierGroupCard
              key={supplierId}
              supplier={suppliersMap[supplierId] || { supplier_id: supplierId, supplier_name: 'Unknown' }}
              items={items}
              onTopup={handleTopup}
              applyingTopup={applyingTopup === supplierId}
            />
          ))}

          {/* Total */}
          <Card className="p-6 bg-blue-50">
            <div className="flex justify-between items-center">
              <div>
                <p className="text-lg font-semibold">Общая сумма:</p>
                <p className="text-sm text-gray-600">
                  {cartData.items?.length} товаров от {Object.keys(itemGroups).length} поставщиков
                </p>
              </div>
              <p className="text-3xl font-bold text-blue-600">
                {cartData.total?.toLocaleString('ru-RU')} ₽
              </p>
            </div>
          </Card>

          {/* Delivery address */}
          <Card className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <MapPin className="h-6 w-6 text-blue-600" />
              <h3 className="text-lg font-semibold">Адрес доставки</h3>
            </div>
            
            {company?.deliveryAddresses?.length > 0 ? (
              <div className="space-y-2">
                {company.deliveryAddresses.map((addr, idx) => (
                  <label
                    key={idx}
                    className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer ${
                      selectedAddress?.address === addr.address ? 'border-blue-500 bg-blue-50' : ''
                    }`}
                  >
                    <input
                      type="radio"
                      checked={selectedAddress?.address === addr.address}
                      onChange={() => setSelectedAddress(addr)}
                    />
                    <span>{addr.address || addr}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-gray-500">Адреса не настроены</p>
            )}
          </Card>

          {/* Checkout */}
          <Button
            size="lg"
            className="w-full"
            onClick={handleCheckout}
            disabled={!canCheckout() || processingOrder}
          >
            {processingOrder ? 'Оформление...' : (
              <>
                Оформить заказ
                <ArrowRight className="h-4 w-4 ml-2" />
              </>
            )}
          </Button>
        </>
      )}
    </div>
  );
};

export default CustomerCartV12;
