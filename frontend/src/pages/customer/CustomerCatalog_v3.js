import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ShoppingCart, Search, Plus, Minus, Trash2, TrendingDown, Store } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerCatalog = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [allProducts, setAllProducts] = useState({});
  const [activeTab, setActiveTab] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredProducts, setFilteredProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState([]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchAllData();
  }, []);

  useEffect(() => {
    filterAndDisplayProducts();
  }, [searchTerm, activeTab, allProducts]);

  const fetchAllData = async () => {
    try {
      const suppliersResponse = await axios.get(`${API}/suppliers`);
      setSuppliers(suppliersResponse.data);

      const productsMap = {};
      for (const supplier of suppliersResponse.data) {
        const priceListResponse = await axios.get(`${API}/suppliers/${supplier.id}/price-lists`);
        productsMap[supplier.id] = {
          supplier: supplier,
          products: priceListResponse.data
        };
      }
      setAllProducts(productsMap);
      
      // Set first supplier as default tab
      if (suppliersResponse.data.length > 0) {
        setActiveTab(suppliersResponse.data[0].id);
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  const filterAndDisplayProducts = () => {
    let productsToShow = [];

    if (activeTab === 'all') {
      // Show products from all suppliers
      Object.values(allProducts).forEach(({ supplier, products }) => {
        productsToShow.push(...products.map(p => ({ ...p, supplier })));
      });
    } else {
      // Show products from selected supplier
      if (allProducts[activeTab]) {
        const { supplier, products } = allProducts[activeTab];
        productsToShow = products.map(p => ({ ...p, supplier }));
      }
    }

    // Apply search filter
    if (searchTerm) {
      productsToShow = productsToShow.filter(product =>
        product.productName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        product.article.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Sort by name
    productsToShow.sort((a, b) => a.productName.localeCompare(b.productName));

    setFilteredProducts(productsToShow.slice(0, 100)); // Limit to 100 for performance
  };

  const addToCart = (product, supplier) => {
    const cartItem = {
      ...product,
      supplierId: supplier.id,
      supplierName: supplier.companyName,
      cartId: `${product.id}-${supplier.id}`
    };

    const existingItem = cart.find(item => item.cartId === cartItem.cartId);
    if (existingItem) {
      setCart(cart.map(item =>
        item.cartId === cartItem.cartId
          ? { ...item, quantity: item.quantity + 1 }
          : item
      ));
    } else {
      setCart([...cart, { ...cartItem, quantity: 1 }]);
    }
  };

  const updateQuantity = (cartId, delta) => {
    setCart(cart.map(item =>
      item.cartId === cartId
        ? { ...item, quantity: Math.max(0, item.quantity + delta) }
        : item
    ).filter(item => item.quantity > 0));
  };

  const removeFromCart = (cartId) => {
    setCart(cart.filter(item => item.cartId !== cartId));
  };

  const calculateTotal = () => {
    return cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  };

  const handlePlaceOrder = async () => {
    if (cart.length === 0) {
      setMessage('Корзина пуста');
      return;
    }

    const ordersBySupplier = {};
    cart.forEach(item => {
      if (!ordersBySupplier[item.supplierId]) {
        ordersBySupplier[item.supplierId] = [];
      }
      ordersBySupplier[item.supplierId].push(item);
    });

    try {
      for (const [supplierId, items] of Object.entries(ordersBySupplier)) {
        const orderDetails = items.map(item => ({
          productName: item.productName,
          article: item.article,
          quantity: item.quantity,
          price: item.price,
          unit: item.unit
        }));

        const amount = items.reduce((sum, item) => sum + (item.price * item.quantity), 0);

        await axios.post(`${API}/orders`, {
          supplierCompanyId: supplierId,
          amount: amount,
          orderDetails: orderDetails
        });
      }

      const orderCount = Object.keys(ordersBySupplier).length;
      setMessage(`Успешно создано ${orderCount} заказ(ов)!`);
      setCart([]);
    } catch (error) {
      setMessage('Ошибка при размещении заказа');
    }
  };

  const getSupplierStats = (supplierId) => {
    if (!allProducts[supplierId]) return { count: 0, avgPrice: 0 };
    
    const products = allProducts[supplierId].products;
    const count = products.length;
    const avgPrice = products.reduce((sum, p) => sum + p.price, 0) / count;
    
    return { count, avgPrice: avgPrice.toFixed(2) };
  };

  if (loading) {
    return <div className=\"text-center py-8\">Загрузка каталога...</div>;
  }

  return (
    <div data-testid=\"customer-catalog-page\">
      <div className=\"flex justify-between items-center mb-6\">
        <div>
          <h2 className=\"text-2xl font-bold\">Каталог товаров</h2>
          <p className=\"text-sm text-gray-600\">
            {Object.values(allProducts).reduce((sum, {products}) => sum + products.length, 0)} товаров от {suppliers.length} поставщиков
          </p>
        </div>
        <div className=\"flex items-center gap-2\">
          <ShoppingCart className=\"h-5 w-5\" />
          <span className=\"font-medium\">{cart.length} товаров</span>
        </div>
      </div>

      {message && (
        <Alert className=\"mb-4\" variant={message.includes('Успешно') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <div className=\"grid lg:grid-cols-4 gap-6\">
        {/* Main content */}
        <div className=\"lg:col-span-3\">
          {/* Search */}
          <div className=\"relative mb-4\">
            <Search className=\"absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400\" />
            <Input
              placeholder=\"Поиск товаров по названию или артикулу...\"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className=\"pl-10\"
              data-testid=\"search-products-input\"
            />
          </div>

          {/* Supplier tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className=\"mb-4\">
            <TabsList className=\"w-full justify-start\">
              <TabsTrigger value=\"all\" className=\"flex-1\">
                Все поставщики
              </TabsTrigger>
              {suppliers.map(supplier => {
                const stats = getSupplierStats(supplier.id);
                return (
                  <TabsTrigger key={supplier.id} value={supplier.id} className=\"flex-1\">
                    <div className=\"flex items-center gap-2\">
                      <Store className=\"h-4 w-4\" />
                      <div className=\"text-left\">
                        <div className=\"font-medium\">{supplier.companyName}</div>
                        <div className=\"text-xs text-gray-500\">{stats.count} товаров</div>
                      </div>
                    </div>
                  </TabsTrigger>
                );
              })}
            </TabsList>

            <TabsContent value={activeTab} className=\"mt-4\">
              {filteredProducts.length === 0 ? (
                <Card className=\"p-8 text-center\">
                  <p className=\"text-gray-600\">Товары не найдены</p>
                </Card>
              ) : (
                <div className=\"grid md:grid-cols-2 gap-4\">
                  {filteredProducts.map(product => {
                    const isAvailable = product.availability && product.active;
                    
                    return (
                      <Card key={`${product.id}-${product.supplier.id}`} className=\"p-4 hover:shadow-md transition-shadow\">
                        <div className=\"flex justify-between items-start mb-2\">
                          <div className=\"flex-1 min-w-0\">
                            <h4 className=\"font-medium text-sm mb-1 line-clamp-2\">{product.productName}</h4>
                            <p className=\"text-xs text-gray-600 mb-1\">Арт: {product.article}</p>
                            <div className=\"flex items-center gap-2 mt-2\">
                              <Badge variant=\"outline\" className=\"text-xs\">
                                <Store className=\"h-3 w-3 mr-1\" />
                                {product.supplier.companyName}
                              </Badge>
                              {isAvailable ? (
                                <Badge className=\"bg-green-100 text-green-800 text-xs\">В наличии</Badge>
                              ) : (
                                <Badge variant=\"outline\" className=\"text-xs\">Нет в наличии</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className=\"flex justify-between items-end mt-3 pt-3 border-t\">
                          <div>
                            <p className=\"text-xl font-bold text-blue-600\">{product.price} ₽</p>
                            <p className=\"text-xs text-gray-600\">за {product.unit}</p>
                          </div>
                          <Button
                            size=\"sm\"
                            onClick={() => addToCart(product, product.supplier)}
                            disabled={!isAvailable}
                            data-testid={`add-to-cart-${product.id}`}
                          >
                            <Plus className=\"h-4 w-4 mr-1\" />
                            В корзину
                          </Button>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              )}

              {filteredProducts.length >= 100 && (
                <p className=\"text-sm text-gray-600 text-center mt-4\">
                  Показано 100 товаров. Используйте поиск для уточнения.
                </p>
              )}
            </TabsContent>
          </Tabs>
        </div>

        {/* Cart sidebar */}
        <div className=\"lg:col-span-1\">
          <Card className=\"p-4 sticky top-4\">
            <h3 className=\"font-semibold mb-3 flex items-center gap-2\">
              <ShoppingCart className=\"h-5 w-5\" />
              Корзина
            </h3>
            {cart.length === 0 ? (
              <p className=\"text-sm text-gray-600 text-center py-4\">Корзина пуста</p>
            ) : (
              <div className=\"space-y-3\">
                <div className=\"max-h-96 overflow-y-auto space-y-3\">
                  {cart.map(item => (
                    <div key={item.cartId} className=\"flex items-start justify-between gap-2 pb-3 border-b\">
                      <div className=\"flex-1 min-w-0\">
                        <p className=\"text-sm font-medium line-clamp-2\">{item.productName}</p>
                        <p className=\"text-xs text-gray-600 mt-1\">{item.supplierName}</p>
                        <p className=\"text-xs text-gray-600\">{item.price} ₽/{item.unit}</p>
                        <div className=\"flex items-center gap-2 mt-2\">
                          <Button
                            size=\"sm\"
                            variant=\"outline\"
                            onClick={() => updateQuantity(item.cartId, -1)}
                            className=\"h-6 w-6 p-0\"
                          >
                            <Minus className=\"h-3 w-3\" />
                          </Button>
                          <span className=\"text-sm font-medium w-8 text-center\">{item.quantity}</span>
                          <Button
                            size=\"sm\"
                            variant=\"outline\"
                            onClick={() => updateQuantity(item.cartId, 1)}
                            className=\"h-6 w-6 p-0\"
                          >
                            <Plus className=\"h-3 w-3\" />
                          </Button>
                        </div>
                      </div>
                      <div className=\"text-right\">
                        <p className=\"text-sm font-medium\">{(item.price * item.quantity).toFixed(2)} ₽</p>
                        <Button
                          size=\"sm\"
                          variant=\"ghost\"
                          onClick={() => removeFromCart(item.cartId)}
                          className=\"h-6 w-6 p-0 mt-1\"
                        >
                          <Trash2 className=\"h-3 w-3\" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className=\"pt-3 border-t\">
                  <div className=\"flex justify-between items-center mb-3\">
                    <span className=\"font-semibold\">Итого:</span>
                    <span className=\"text-xl font-bold\">{calculateTotal().toFixed(2)} ₽</span>
                  </div>
                  <Button
                    onClick={handlePlaceOrder}
                    className=\"w-full\"
                    data-testid=\"place-order-btn\"
                  >
                    Оформить заказ
                  </Button>
                  <p className=\"text-xs text-gray-600 text-center mt-2\">
                    Заказы будут разделены по поставщикам
                  </p>
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};
