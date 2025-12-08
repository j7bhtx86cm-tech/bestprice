import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ShoppingCart, Search, Plus, Minus, Trash2, Award, CheckCircle, TrendingDown } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerCatalog = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [allProducts, setAllProducts] = useState({});
  const [groupedProducts, setGroupedProducts] = useState([]);
  const [filteredGroups, setFilteredGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [cart, setCart] = useState([]);
  const [message, setMessage] = useState('');
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [lastOrderInfo, setLastOrderInfo] = useState(null);

  useEffect(() => {
    fetchAllData();
  }, []);

  useEffect(() => {
    filterProducts();
  }, [searchTerm, groupedProducts]);

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

      const grouped = groupProductsByName(productsMap);
      setGroupedProducts(grouped);
      setFilteredGroups(grouped);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  const groupProductsByName = (productsMap) => {
    const allProductNames = new Set();
    Object.values(productsMap).forEach(({ products }) => {
      products.forEach(p => {
        const normalized = normalizeProductName(p.productName);
        allProductNames.add(normalized);
      });
    });

    const groups = [];
    allProductNames.forEach(normalizedName => {
      const variants = [];
      
      Object.entries(productsMap).forEach(([supplierId, { supplier, products }]) => {
        const matchingProducts = products.filter(p => 
          normalizeProductName(p.productName) === normalizedName
        );
        
        if (matchingProducts.length > 0) {
          variants.push({
            supplier: supplier,
            products: matchingProducts
          });
        }
      });

      if (variants.length > 0) {
        const displayName = variants[0].products[0].productName;
        groups.push({
          displayName: displayName,
          normalizedName: normalizedName,
          variants: variants
        });
      }
    });

    return groups.sort((a, b) => a.displayName.localeCompare(b.displayName));
  };

  const normalizeProductName = (name) => {
    let normalized = name
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .replace(/[«»"(),]/g, ' ')
      .trim();
    
    const words = normalized.split(' ').filter(w => w.length > 2);
    
    if (words.length >= 2) {
      return words.slice(0, 2).join(' ');
    }
    
    return words[0] || normalized;
  };

  const filterProducts = () => {
    if (!searchTerm) {
      setFilteredGroups(groupedProducts);
      return;
    }

    const filtered = groupedProducts.filter(group =>
      group.displayName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      group.variants.some(v => v.products.some(p => 
        p.article.toLowerCase().includes(searchTerm.toLowerCase())
      ))
    );
    setFilteredGroups(filtered);
  };

  const getAllPriceOptions = (group) => {
    const options = [];
    group.variants.forEach(variant => {
      variant.products.forEach(product => {
        if (product.availability && product.active) {
          options.push({
            ...product,
            supplier: variant.supplier
          });
        }
      });
    });
    
    return options.sort((a, b) => a.price - b.price);
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

  const calculateSavings = () => {
    let totalSavings = 0;
    cart.forEach(item => {
      const group = groupedProducts.find(g => 
        g.variants.some(v => v.products.some(p => p.id === item.id))
      );
      if (group) {
        let maxPrice = 0;
        group.variants.forEach(variant => {
          variant.products.forEach(product => {
            if (product.price > maxPrice && product.availability) {
              maxPrice = product.price;
            }
          });
        });
        if (maxPrice > item.price) {
          totalSavings += (maxPrice - item.price) * item.quantity;
        }
      }
    });
    return totalSavings;
  };

  const handlePlaceOrder = async () => {
    if (cart.length === 0) {
      setMessage('Корзина пуста');
      return;
    }

    const ordersBySupplier = {};
    cart.forEach(item => {
      if (!ordersBySupplier[item.supplierId]) {
        ordersBySupplier[item.supplierId] = {
          supplierName: item.supplierName,
          items: []
        };
      }
      ordersBySupplier[item.supplierId].items.push(item);
    });

    try {
      const orderIds = [];
      for (const [supplierId, data] of Object.entries(ordersBySupplier)) {
        const orderDetails = data.items.map(item => ({
          productName: item.productName,
          article: item.article,
          quantity: item.quantity,
          price: item.price,
          unit: item.unit
        }));

        const amount = data.items.reduce((sum, item) => sum + (item.price * item.quantity), 0);

        const response = await axios.post(`${API}/orders`, {
          supplierCompanyId: supplierId,
          amount: amount,
          orderDetails: orderDetails
        });
        orderIds.push(response.data.id);
      }

      const orderCount = Object.keys(ordersBySupplier).length;
      const savings = calculateSavings();
      
      setLastOrderInfo({
        orderCount,
        total: calculateTotal(),
        savings: savings,
        suppliers: Object.values(ordersBySupplier).map(s => s.supplierName)
      });
      
      setCart([]);
      setShowSuccessModal(true);
    } catch (error) {
      setMessage('Ошибка при размещении заказа');
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка каталога...</div>;
  }

  return (
    <div data-testid="customer-catalog-page">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold">Каталог товаров</h2>
          <p className="text-sm text-gray-600">
            {Object.values(allProducts).reduce((sum, {products}) => sum + products.length, 0)} товаров • Лучшие цены
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ShoppingCart className="h-5 w-5" />
          <span className="font-medium">{cart.length} товаров</span>
        </div>
      </div>

      {message && (
        <Alert className="mb-4" variant="destructive">
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <div className="grid lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3 space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Поиск товаров..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
              data-testid="search-products-input"
            />
          </div>

          {filteredGroups.length === 0 ? (
            <Card className="p-8 text-center">
              <p className="text-gray-600">Товары не найдены</p>
            </Card>
          ) : (
            <div className="space-y-3">
              {filteredGroups.slice(0, 50).map((group, idx) => {
                const priceOptions = getAllPriceOptions(group);
                
                if (priceOptions.length === 0) return null;

                const bestPrice = priceOptions[0];
                
                return (
                  <Card key={idx} className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium mb-3">{group.displayName}</h4>
                        
                        <div className="space-y-2">
                          {priceOptions.map((product, pIdx) => {
                            const isBestPrice = pIdx === 0 && priceOptions.length > 1;
                            
                            return (
                              <div 
                                key={product.id} 
                                className={`flex items-center justify-between p-3 rounded-lg ${
                                  isBestPrice ? 'bg-green-50 border-2 border-green-500' : 'bg-gray-50 border border-gray-200'
                                }`}
                              >
                                <div className="flex items-center gap-3 flex-1">
                                  {isBestPrice && (
                                    <Badge className="bg-green-600 text-white">
                                      <Award className="h-3 w-3 mr-1" />
                                      Best Price
                                    </Badge>
                                  )}
                                  {priceOptions.length > 1 && !isBestPrice && (
                                    <Badge variant="outline" className="text-xs">
                                      Вариант {pIdx + 1}
                                    </Badge>
                                  )}
                                </div>
                                <div className="flex items-center gap-4">
                                  <div className="text-right">
                                    <p className={`font-bold ${isBestPrice ? 'text-green-600 text-2xl' : 'text-gray-900 text-xl'}`}>
                                      {product.price} ₽
                                    </p>
                                    <p className="text-xs text-gray-600">за {product.unit}</p>
                                  </div>
                                  <Button
                                    size="sm"
                                    onClick={() => addToCart(product, product.supplier)}
                                    className={isBestPrice ? 'bg-green-600 hover:bg-green-700' : ''}
                                    data-testid={`add-to-cart-${product.id}`}
                                  >
                                    <Plus className="h-4 w-4 mr-1" />
                                    В корзину
                                  </Button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        <div className="lg:col-span-1">
          <Card className="p-4 sticky top-4">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <ShoppingCart className="h-5 w-5" />
              Корзина
            </h3>
            {cart.length === 0 ? (
              <p className="text-sm text-gray-600 text-center py-4">Корзина пуста</p>
            ) : (
              <div className="space-y-3">
                <div className="max-h-96 overflow-y-auto space-y-3">
                  {cart.map(item => (
                    <div key={item.cartId} className="flex items-start justify-between gap-2 pb-3 border-b">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium line-clamp-2">{item.productName}</p>
                        <p className="text-xs text-gray-600 mt-1">{item.price} ₽/{item.unit}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => updateQuantity(item.cartId, -1)}
                            className="h-6 w-6 p-0"
                          >
                            <Minus className="h-3 w-3" />
                          </Button>
                          <span className="text-sm font-medium w-8 text-center">{item.quantity}</span>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => updateQuantity(item.cartId, 1)}
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
                          onClick={() => removeFromCart(item.cartId)}
                          className="h-6 w-6 p-0 mt-1"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>

                {calculateSavings() > 0 && (
                  <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                    <div className="flex items-center gap-2 text-green-700">
                      <TrendingDown className="h-4 w-4" />
                      <div>
                        <p className="text-xs font-medium">Ваша экономия</p>
                        <p className="text-lg font-bold">{calculateSavings().toFixed(2)} ₽</p>
                      </div>
                    </div>
                  </div>
                )}

                <div className="pt-3 border-t">
                  <div className="flex justify-between items-center mb-3">
                    <span className="font-semibold">Итого:</span>
                    <span className="text-xl font-bold">{calculateTotal().toFixed(2)} ₽</span>
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
      </div>

      {/* Success Modal */}
      <Dialog open={showSuccessModal} onOpenChange={setShowSuccessModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-green-600">
              <CheckCircle className="h-6 w-6" />
              Заказ принят!
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <p className="text-sm text-gray-700 mb-2">
                Создано заказов: <span className="font-bold">{lastOrderInfo?.orderCount}</span>
              </p>
              <p className="text-sm text-gray-700 mb-2">
                Сумма заказа: <span className="font-bold">{lastOrderInfo?.total.toFixed(2)} ₽</span>
              </p>
              {lastOrderInfo?.savings > 0 && (
                <div className="mt-3 pt-3 border-t border-green-300">
                  <p className="text-sm text-green-700 flex items-center gap-2">
                    <TrendingDown className="h-4 w-4" />
                    <span>Ваша экономия: <span className="font-bold text-lg">{lastOrderInfo?.savings.toFixed(2)} ₽</span></span>
                  </p>
                </div>
              )}
            </div>
            
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Поставщики:</p>
              <div className="space-y-1">
                {lastOrderInfo?.suppliers.map((supplier, idx) => (
                  <div key={idx} className="text-sm text-gray-600 flex items-center gap-2">
                    <div className="h-2 w-2 bg-blue-500 rounded-full"></div>
                    {supplier}
                  </div>
                ))}
              </div>
            </div>

            <Button onClick={() => setShowSuccessModal(false)} className="w-full">
              Продолжить покупки
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
