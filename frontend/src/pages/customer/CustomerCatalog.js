import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ShoppingCart, Search, Plus, Minus, Trash2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerCatalog = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [selectedSupplier, setSelectedSupplier] = useState(null);
  const [products, setProducts] = useState([]);
  const [filteredProducts, setFilteredProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [cart, setCart] = useState([]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchSuppliers();
  }, []);

  useEffect(() => {
    if (selectedSupplier) {
      fetchProducts(selectedSupplier);
    }
  }, [selectedSupplier]);

  useEffect(() => {
    filterProducts();
  }, [searchTerm, products]);

  const fetchSuppliers = async () => {
    try {
      const response = await axios.get(`${API}/suppliers`);
      setSuppliers(response.data);
      if (response.data.length > 0) {
        setSelectedSupplier(response.data[0].id);
      }
    } catch (error) {
      console.error('Failed to fetch suppliers:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async (supplierId) => {
    setLoading(true);
    try {
      // Get company to fetch price lists
      const companyResponse = await axios.get(`${API}/companies/${supplierId}`);
      const response = await axios.get(`${API}/price-lists/my`);
      
      // Filter products for selected supplier - we need to get them differently
      // Let's use a direct query
      const allPriceLists = await axios.get(`${API}/price-lists/my`);
      
      // For now, let's fetch all and filter client-side
      // TODO: Add API endpoint to get price lists by supplier
      setProducts(allPriceLists.data.filter(p => p.supplierCompanyId === supplierId));
    } catch (error) {
      console.error('Failed to fetch products:', error);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  };

  const filterProducts = () => {
    if (!searchTerm) {
      setFilteredProducts(products);
      return;
    }
    
    const filtered = products.filter(product =>
      product.productName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.article.toLowerCase().includes(searchTerm.toLowerCase())
    );
    setFilteredProducts(filtered);
  };

  const addToCart = (product) => {
    const existingItem = cart.find(item => item.id === product.id);
    if (existingItem) {
      setCart(cart.map(item =>
        item.id === product.id
          ? { ...item, quantity: item.quantity + 1 }
          : item
      ));
    } else {
      setCart([...cart, { ...product, quantity: 1 }]);
    }
  };

  const updateQuantity = (productId, delta) => {
    setCart(cart.map(item =>
      item.id === productId
        ? { ...item, quantity: Math.max(0, item.quantity + delta) }
        : item
    ).filter(item => item.quantity > 0));
  };

  const removeFromCart = (productId) => {
    setCart(cart.filter(item => item.id !== productId));
  };

  const calculateTotal = () => {
    return cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  };

  const handlePlaceOrder = async () => {
    if (cart.length === 0) {
      setMessage('Корзина пуста');
      return;
    }

    try {
      const orderDetails = cart.map(item => ({
        productName: item.productName,
        article: item.article,
        quantity: item.quantity,
        price: item.price,
        unit: item.unit
      }));

      await axios.post(`${API}/orders`, {
        supplierCompanyId: selectedSupplier,
        amount: calculateTotal(),
        orderDetails
      });

      setMessage('Заказ успешно размещен!');
      setCart([]);
    } catch (error) {
      setMessage('Ошибка при размещении заказа');
    }
  };

  const getCurrentSupplier = () => {
    return suppliers.find(s => s.id === selectedSupplier);
  };

  if (loading && suppliers.length === 0) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-catalog-page">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Каталог товаров</h2>
        <div className="flex items-center gap-2">
          <ShoppingCart className="h-5 w-5" />
          <span className="font-medium">{cart.length} товаров</span>
        </div>
      </div>

      {message && (
        <Alert className="mb-4" variant={message.includes('успешно') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left sidebar - Supplier selection and cart */}
        <div className="space-y-6">
          {/* Supplier selection */}
          <Card className="p-4">
            <h3 className="font-semibold mb-3">Выберите поставщика</h3>
            <Select value={selectedSupplier} onValueChange={setSelectedSupplier}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {suppliers.map(supplier => (
                  <SelectItem key={supplier.id} value={supplier.id}>
                    {supplier.companyName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {getCurrentSupplier() && (
              <div className="mt-3 text-sm text-gray-600">
                <p>📞 {getCurrentSupplier().phone}</p>
                <p>📧 {getCurrentSupplier().email}</p>
              </div>
            )}
          </Card>

          {/* Cart */}
          <Card className="p-4">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <ShoppingCart className="h-5 w-5" />
              Корзина
            </h3>
            {cart.length === 0 ? (
              <p className="text-sm text-gray-600 text-center py-4">Корзина пуста</p>
            ) : (
              <div className="space-y-3">
                {cart.map(item => (
                  <div key={item.id} className="flex items-start justify-between gap-2 pb-3 border-b">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{item.productName}</p>
                      <p className="text-xs text-gray-600">{item.price} ₽/{item.unit}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => updateQuantity(item.id, -1)}
                          className="h-6 w-6 p-0"
                        >
                          <Minus className="h-3 w-3" />
                        </Button>
                        <span className="text-sm font-medium">{item.quantity}</span>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => updateQuantity(item.id, 1)}
                          className="h-6 w-6 p-0"
                        >
                          <Plus className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium">{(item.price * item.quantity).toFixed(2)} ₽</p>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => removeFromCart(item.id)}
                        className="h-6 w-6 p-0 mt-1"
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                ))}
                <div className="pt-3 border-t">
                  <div className="flex justify-between items-center mb-3">
                    <span className="font-semibold">Итого:</span>
                    <span className="text-lg font-bold">{calculateTotal().toFixed(2)} ₽</span>
                  </div>
                  <Button
                    onClick={handlePlaceOrder}
                    className="w-full"
                    data-testid="place-order-btn"
                  >
                    Оформить заказ
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Right content - Products */}
        <div className="lg:col-span-2 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Поиск по названию или артикулу..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
              data-testid="search-products-input"
            />
          </div>

          {/* Products grid */}
          {loading ? (
            <div className="text-center py-8">Загрузка товаров...</div>
          ) : filteredProducts.length === 0 ? (
            <Card className="p-8 text-center">
              <p className="text-gray-600">Товары не найдены</p>
            </Card>
          ) : (
            <div className="grid md:grid-cols-2 gap-4">
              {filteredProducts.map(product => (
                <Card key={product.id} className="p-4 hover:shadow-md transition-shadow">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1">
                      <h4 className="font-medium text-sm mb-1 line-clamp-2">{product.productName}</h4>
                      <p className="text-xs text-gray-600">Арт: {product.article}</p>
                    </div>
                    {product.availability && (
                      <Badge className="bg-green-100 text-green-800 text-xs">В наличии</Badge>
                    )}
                  </div>
                  <div className="flex justify-between items-end mt-3">
                    <div>
                      <p className="text-lg font-bold text-blue-600">{product.price} ₽</p>
                      <p className="text-xs text-gray-600">за {product.unit}</p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => addToCart(product)}
                      disabled={!product.availability || !product.active}
                      data-testid={`add-to-cart-${product.id}`}
                    >
                      <Plus className="h-4 w-4 mr-1" />
                      В корзину
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {filteredProducts.length > 0 && (
            <p className="text-sm text-gray-600 text-center mt-4">
              Показано {filteredProducts.length} из {products.length} товаров
            </p>
          )}
        </div>
      </div>
    </div>
  );
};