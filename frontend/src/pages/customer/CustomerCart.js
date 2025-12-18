import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ShoppingCart, Trash2, Plus, Minus, Package, MapPin } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerCart = () => {
  const navigate = useNavigate();
  const [cartItems, setCartItems] = useState([]);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [showAddressModal, setShowAddressModal] = useState(false);
  const [processingOrder, setProcessingOrder] = useState(false);

  useEffect(() => {
    loadCart();
    fetchCompanyInfo();
  }, []);

  const loadCart = () => {
    // Load from catalog cart + favorite cart
    const catalogCart = JSON.parse(localStorage.getItem('catalogCart') || '[]');
    const favoriteCart = JSON.parse(localStorage.getItem('favoriteCart') || '[]');
    
    // Merge both carts
    const allItems = [...catalogCart, ...favoriteCart];
    setCartItems(allItems);
  };

  const fetchCompanyInfo = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/companies/my`, { headers });
      setCompany(response.data);
      if (response.data.deliveryAddresses?.length === 1) {
        setSelectedAddress(response.data.deliveryAddresses[0]);
      }
    } catch (error) {
      console.error('Failed to fetch company:', error);
    }
  };

  const updateQuantity = (cartId, delta) => {
    const updated = cartItems.map(item => {
      if (item.cartId === cartId) {
        const newQty = Math.max(1, item.quantity + delta);
        return { ...item, quantity: newQty };
      }
      return item;
    });
    setCartItems(updated);
    saveCart(updated);
  };

  const removeItem = (cartId) => {
    const updated = cartItems.filter(item => item.cartId !== cartId);
    setCartItems(updated);
    saveCart(updated);
  };

  const saveCart = (items) => {
    // Split back into catalog and favorite carts
    const catalogItems = items.filter(i => !i.favoriteId);
    const favoriteItems = items.filter(i => i.favoriteId);
    
    localStorage.setItem('catalogCart', JSON.stringify(catalogItems));
    localStorage.setItem('favoriteCart', JSON.stringify(favoriteItems));
  };

  const getCartTotal = () => {
    return cartItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  };

  const groupBySupplier = () => {
    const groups = {};
    cartItems.forEach(item => {
      const supplier = item.supplier || item.supplierName || 'Unknown';
      if (!groups[supplier]) {
        groups[supplier] = [];
      }
      groups[supplier].push(item);
    });
    return groups;
  };

  const handleCheckout = async () => {
    if (cartItems.length === 0) return;

    if (company?.deliveryAddresses?.length > 1 && !selectedAddress) {
      setShowAddressModal(true);
      return;
    }

    setProcessingOrder(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      // Group by supplier
      const ordersBySupplier = {};
      cartItems.forEach(item => {
        const supplierId = item.supplierId || item.favoriteId;  // Needs proper supplier ID
        if (!ordersBySupplier[supplierId]) {
          ordersBySupplier[supplierId] = { items: [] };
        }
        ordersBySupplier[supplierId].items.push({
          productName: item.productName,
          article: item.article || item.productCode || '',
          quantity: item.quantity,
          price: item.price,
          unit: item.unit
        });
      });

      // Create orders
      for (const [supplierId, orderData] of Object.entries(ordersBySupplier)) {
        const amount = orderData.items.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        await axios.post(`${API}/orders`, {
          supplierCompanyId: supplierId,
          amount: amount,
          orderDetails: orderData.items,
          deliveryAddress: selectedAddress
        }, { headers });
      }

      // Clear cart
      localStorage.removeItem('catalogCart');
      localStorage.removeItem('favoriteCart');
      setCartItems([]);
      
      alert('✓ Заказ успешно создан!');
      navigate('/customer/orders');
    } catch (error) {
      console.error('Failed to create order:', error);
      alert('Ошибка создания заказа');
    } finally {
      setProcessingOrder(false);
    }
  };

  const supplierGroups = groupBySupplier();

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Корзина</h2>
          <p className="text-base text-muted-foreground">
            Проверьте товары перед оформлением заказа
          </p>
        </div>
        {cartItems.length > 0 && (
          <Button onClick={handleCheckout} disabled={processingOrder} size="lg">
            <ShoppingCart className="h-4 w-4 mr-2" />
            Оформить заказ ({cartItems.length})
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
          {Object.entries(supplierGroups).map(([supplier, items]) => (
            <Card key={supplier} className="p-6">
              <div className="flex items-center gap-2 mb-4 pb-3 border-b">
                <Package className="h-5 w-5 text-blue-600" />
                <h3 className="text-lg font-semibold">{supplier}</h3>
                <Badge className="ml-auto">
                  {items.length} товаров
                </Badge>
              </div>

              <div className="space-y-3">
                {items.map((item) => (
                  <div key={item.cartId} className="flex items-center gap-4 p-4 border rounded-lg">
                    <div className="flex-1">
                      <p className="font-medium">{item.productName}</p>
                      <p className="text-sm text-gray-600">
                        {item.price?.toLocaleString('ru-RU')} ₽ / {item.unit}
                      </p>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => updateQuantity(item.cartId, -1)}
                      >
                        <Minus className="h-4 w-4" />
                      </Button>
                      <Input
                        type="number"
                        min="1"
                        step="1"
                        value={item.quantity}
                        onChange={(e) => {
                          const val = parseInt(e.target.value) || 1;
                          updateQuantity(item.cartId, val - item.quantity);
                        }}
                        className="w-20 text-center"
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => updateQuantity(item.cartId, 1)}
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>

                    <div className="text-right w-24">
                      <p className="font-semibold">
                        {(item.price * item.quantity).toLocaleString('ru-RU')} ₽
                      </p>
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeItem(item.cartId)}
                      className="text-red-600 hover:text-red-700"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>

              <div className="mt-4 pt-4 border-t flex justify-between items-center">
                <span className="font-medium">Итого у {supplier}:</span>
                <span className="text-xl font-bold">
                  {items.reduce((sum, i) => sum + (i.price * i.quantity), 0).toLocaleString('ru-RU')} ₽
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
          {company?.deliveryAddresses && company.deliveryAddresses.length > 1 && (
            <Card className="p-6">
              <h3 className="font-semibold mb-3">Адрес доставки</h3>
              <div className="space-y-2">
                {company.deliveryAddresses.map((addr, idx) => (
                  <label
                    key={idx}
                    className={`flex items-start gap-3 p-3 border rounded cursor-pointer ${
                      selectedAddress?.address === addr.address ? 'border-blue-500 bg-blue-50' : ''
                    }`}
                  >
                    <input
                      type="radio"
                      name="address"
                      checked={selectedAddress?.address === addr.address}
                      onChange={() => setSelectedAddress(addr)}
                      className="mt-1"
                    />
                    <div className="flex-1">
                      <p className="font-medium">{addr.address}</p>
                      <p className="text-sm text-gray-600">Тел: {addr.phone}</p>
                    </div>
                  </label>
                ))}
              </div>
            </Card>
          )}

          {/* Checkout Button */}
          <div className="flex gap-3">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => navigate('/customer/catalog')}
            >
              Продолжить покупки
            </Button>
            <Button
              className="flex-1"
              size="lg"
              onClick={handleCheckout}
              disabled={processingOrder}
            >
              {processingOrder ? 'Оформление...' : 'Оформить заказ'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
