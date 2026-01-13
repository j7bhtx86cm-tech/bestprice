import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ShoppingCart, Trash2, Plus, Minus, Package, MapPin, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerCart = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [cartItems, setCartItems] = useState([]);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [processingOrder, setProcessingOrder] = useState(false);
  const [loading, setLoading] = useState(true);

  const getUserId = () => user?.id || 'anonymous';
  
  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Load cart from API
  const loadCart = useCallback(async () => {
    setLoading(true);
    try {
      const userId = getUserId();
      if (!userId || userId === 'anonymous') {
        setLoading(false);
        return;
      }
      
      const response = await axios.get(`${API}/v12/cart?user_id=${userId}`, {
        headers: getHeaders()
      });
      setCartItems(response.data.items || []);
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
      loadCart();
    }
    fetchCompanyInfo();
  }, [loadCart, fetchCompanyInfo, user]);

  // Update quantity
  const updateQuantity = async (item, delta) => {
    const currentQty = item.effective_qty || item.user_qty || 1;
    const newQty = Math.max(1, currentQty + delta);
    
    // Update locally first
    const updated = cartItems.map(i => 
      i.cart_item_id === item.cart_item_id 
        ? { ...i, user_qty: newQty, effective_qty: newQty, line_total: newQty * i.price }
        : i
    );
    setCartItems(updated);
    
    // Update on server
    try {
      const userId = getUserId();
      await axios.put(`${API}/v12/cart/${item.cart_item_id}?user_id=${userId}&qty=${newQty}`, {}, {
        headers: getHeaders()
      });
    } catch (error) {
      // Reload cart on error
      loadCart();
      toast.error('Ошибка обновления количества');
    }
  };

  // Remove item
  const removeItem = async (cartItemId) => {
    try {
      const userId = getUserId();
      await axios.delete(`${API}/v12/cart/${cartItemId}?user_id=${userId}`, {
        headers: getHeaders()
      });
      setCartItems(cartItems.filter(i => i.cart_item_id !== cartItemId));
      toast.success('Удалено из корзины');
    } catch (error) {
      toast.error('Ошибка удаления');
    }
  };

  // Group by supplier
  const groupBySupplier = () => {
    const groups = {};
    cartItems.forEach(item => {
      const supplier = item.supplier_name || 'Unknown';
      if (!groups[supplier]) {
        groups[supplier] = { items: [], supplierId: item.supplier_id };
      }
      groups[supplier].items.push(item);
    });
    return groups;
  };

  // Get total
  const getCartTotal = () => {
    return cartItems.reduce((sum, item) => sum + (item.line_total || item.price * (item.effective_qty || 1)), 0);
  };

  // Handle checkout
  const handleCheckout = async () => {
    if (cartItems.length === 0) {
      toast.error('Корзина пуста');
      return;
    }

    if (!selectedAddress) {
      toast.error('Выберите адрес доставки');
      return;
    }

    setProcessingOrder(true);
    try {
      const headers = getHeaders();

      // Group items by supplier
      const ordersBySupplier = {};
      cartItems.forEach(item => {
        const supplierId = item.supplier_id;
        if (!ordersBySupplier[supplierId]) {
          ordersBySupplier[supplierId] = { items: [] };
        }
        ordersBySupplier[supplierId].items.push({
          productName: item.product_name,
          article: '',
          quantity: item.effective_qty || item.user_qty || 1,
          price: item.price,
          unit: item.unit_type === 'WEIGHT' ? 'кг' : item.unit_type === 'VOLUME' ? 'л' : 'шт'
        });
      });

      // Create orders for each supplier
      for (const [supplierId, data] of Object.entries(ordersBySupplier)) {
        const amount = data.items.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        await axios.post(`${API}/orders`, {
          supplierCompanyId: supplierId,
          amount: amount,
          orderDetails: data.items,
          deliveryAddress: selectedAddress
        }, { headers });
      }

      // Clear cart
      const userId = getUserId();
      await axios.delete(`${API}/v12/cart?user_id=${userId}`, { headers: getHeaders() });
      
      toast.success('✓ Заказ успешно создан!');
      setCartItems([]);
      navigate('/customer/orders');
    } catch (error) {
      console.error('Order error:', error);
      toast.error('Ошибка создания заказа');
    } finally {
      setProcessingOrder(false);
    }
  };

  const supplierGroups = groupBySupplier();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div>
      {/* Header with checkout button */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Корзина</h2>
          <p className="text-base text-muted-foreground">
            Проверьте товары перед оформлением заказа
          </p>
        </div>
        {cartItems.length > 0 && (
          <Button 
            onClick={handleCheckout} 
            disabled={processingOrder || !selectedAddress} 
            size="lg"
            data-testid="checkout-btn"
          >
            <ShoppingCart className="h-4 w-4 mr-2" />
            {processingOrder ? 'Оформление...' : `Оформить заказ (${cartItems.length})`}
          </Button>
        )}
      </div>

      {cartItems.length === 0 ? (
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
          {/* Group by Supplier */}
          {Object.entries(supplierGroups).map(([supplier, data]) => (
            <Card key={supplier} className="p-6">
              <div className="flex items-center gap-2 mb-4 pb-3 border-b">
                <Package className="h-5 w-5 text-blue-600" />
                <h3 className="text-lg font-semibold">{supplier}</h3>
                <Badge className="ml-auto">
                  {data.items.length} товаров
                </Badge>
              </div>

              <div className="space-y-3">
                {data.items.map((item) => {
                  const quantity = item.effective_qty || item.user_qty || 1;
                  return (
                    <div key={item.cart_item_id} className="flex items-center gap-4 p-4 border rounded-lg">
                      <div className="flex-1">
                        <p className="font-medium">{item.product_name}</p>
                        <p className="text-sm text-gray-600">
                          {item.price?.toLocaleString('ru-RU')} ₽ / {item.unit_type === 'WEIGHT' ? 'кг' : item.unit_type === 'VOLUME' ? 'л' : 'шт'}
                        </p>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => updateQuantity(item, -1)}
                        >
                          <Minus className="h-4 w-4" />
                        </Button>
                        <Input
                          type="number"
                          min="1"
                          step="1"
                          value={quantity}
                          onChange={(e) => {
                            const val = parseInt(e.target.value) || 1;
                            updateQuantity(item, val - quantity);
                          }}
                          className="w-20 text-center"
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => updateQuantity(item, 1)}
                        >
                          <Plus className="h-4 w-4" />
                        </Button>
                      </div>

                      <div className="text-right w-24">
                        <p className="font-semibold">
                          {(item.price * quantity).toLocaleString('ru-RU')} ₽
                        </p>
                      </div>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeItem(item.cart_item_id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  );
                })}
              </div>

              <div className="mt-4 pt-4 border-t flex justify-between items-center">
                <span className="font-medium">Итого у {supplier}:</span>
                <span className="text-xl font-bold">
                  {data.items.reduce((sum, i) => sum + (i.price * (i.effective_qty || i.user_qty || 1)), 0).toLocaleString('ru-RU')} ₽
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
                  {cartItems.length} товаров от {Object.keys(supplierGroups).length} поставщиков
                </p>
              </div>
              <p className="text-3xl font-bold text-blue-600">
                {getCartTotal().toLocaleString('ru-RU')} ₽
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
            disabled={processingOrder || !selectedAddress} 
            size="lg"
            className="w-full"
            data-testid="checkout-btn-bottom"
          >
            <ShoppingCart className="h-4 w-4 mr-2" />
            {processingOrder ? 'Оформление...' : `Оформить заказ (${cartItems.length})`}
          </Button>
        </div>
      )}
    </div>
  );
};

export default CustomerCart;
