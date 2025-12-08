import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ShoppingCart, Search, Plus, Minus, Trash2, TrendingDown, Award } from 'lucide-react';

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

  useEffect(() => {
    fetchAllData();
  }, []);

  useEffect(() => {
    filterProducts();
  }, [searchTerm, groupedProducts]);

  const fetchAllData = async () => {
    try {
      // Fetch suppliers
      const suppliersResponse = await axios.get(`${API}/suppliers`);
      setSuppliers(suppliersResponse.data);

      // Fetch price lists from all suppliers
      const productsMap = {};
      for (const supplier of suppliersResponse.data) {
        const priceListResponse = await axios.get(`${API}/suppliers/${supplier.id}/price-lists`);
        productsMap[supplier.id] = {
          supplier: supplier,
          products: priceListResponse.data
        };
      }
      setAllProducts(productsMap);

      // Group products by name similarity
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
    // Get all unique product names
    const allProductNames = new Set();
    Object.values(productsMap).forEach(({ products }) => {
      products.forEach(p => {
        const normalized = normalizeProductName(p.productName);
        allProductNames.add(normalized);
      });
    });

    // Group products by normalized name
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
        // Use the first product's name as the display name
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
    // Extract the core product name by removing brand names, weights, manufacturers
    let normalized = name
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .replace(/[«»"(),]/g, ' ')
      .trim();
    
    // Extract first 2-3 meaningful words (the actual product)
    const words = normalized.split(' ').filter(w => w.length > 2);
    
    // Take first 2-3 words as the product identifier
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

  const getBestPrice = (group) => {
    let bestPrice = Infinity;
    let bestVariant = null;

    group.variants.forEach(variant => {
      variant.products.forEach(product => {
        if (product.price < bestPrice && product.availability && product.active) {
          bestPrice = product.price;
          bestVariant = { ...product, supplier: variant.supplier };
        }
      });
    });

    return bestVariant;
  };

  const addToCart = (product, supplier) => {
    const cartItem = {
      ...product,
      supplierId: supplier.id,
      supplierName: supplier.companyName,
      cartId: `${product.id}-${supplier.id}` // Unique ID for cart
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
      // Find this product in grouped products
      const group = groupedProducts.find(g => 
        g.variants.some(v => v.products.some(p => p.id === item.id))
      );
      if (group) {
        // Find highest price among suppliers for this product
        let maxPrice = 0;
        group.variants.forEach(variant => {
          variant.products.forEach(product => {
            if (product.price > maxPrice) {
              maxPrice = product.price;
            }
          });
        });
        totalSavings += (maxPrice - item.price) * item.quantity;
      }
    });
    return totalSavings;
  };

  const handlePlaceOrder = async () => {
    if (cart.length === 0) {
      setMessage('Корзина пуста');
      return;
    }

    // Group cart items by supplier
    const ordersBySupplier = {};
    cart.forEach(item => {
      if (!ordersBySupplier[item.supplierId]) {
        ordersBySupplier[item.supplierId] = [];
      }
      ordersBySupplier[item.supplierId].push(item);
    });

    try {
      // Create separate orders for each supplier
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

  if (loading) {
    return <div className="text-center py-8">Загрузка каталога...</div>;
  }

  return (
    <div data-testid="customer-catalog-page">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold">Каталог товаров</h2>
          <p className="text-sm text-gray-600">Сравнивайте цены от {suppliers.length} поставщиков</p>
        </div>
        <div className="flex items-center gap-2">
          <ShoppingCart className="h-5 w-5" />
          <span className="font-medium">{cart.length} товаров</span>
        </div>
      </div>

      {message && (
        <Alert className="mb-4" variant={message.includes('Успешно') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <div className="grid lg:grid-cols-4 gap-6">
        {/* Main content - Products */}
        <div className="lg:col-span-3 space-y-4">
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

          {/* Products comparison list */}
          {filteredGroups.length === 0 ? (
            <Card className="p-8 text-center">
              <p className="text-gray-600">Товары не найдены</p>
            </Card>
          ) : (
            <div className="space-y-3">
              {filteredGroups.slice(0, 50).map((group, idx) => {
                const bestPrice = getBestPrice(group);
                
                // Check if this is a real comparison (products from DIFFERENT suppliers)
                const hasMultipleSuppliers = group.variants.length > 1;
                const totalProducts = group.variants.reduce((sum, v) => sum + v.products.length, 0);
                
                return (
                  <Card key={idx} className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium mb-2 line-clamp-2">{group.displayName}</h4>
                        {hasMultipleSuppliers && (
                          <Badge className="mb-2 bg-blue-100 text-blue-800">
                            Сравнение цен от {group.variants.length} поставщиков
                          </Badge>
                        )}
                        
                        {/* Price comparison table */}
                        <div className="space-y-2">
                          {group.variants.map((variant, vIdx) => (
                            <div key={vIdx}>
                              {variant.products.map((product, pIdx) => {
                                const isBestPrice = bestPrice && product.id === bestPrice.id && hasMultipleSuppliers;
                                const isAvailable = product.availability && product.active;
                                
                                return (
                                  <div 
                                    key={pIdx} 
                                    className={`flex items-center justify-between p-2 rounded ${
                                      isBestPrice ? 'bg-green-50 border border-green-200' : 'bg-gray-50'
                                    }`}
                                  >
                                    <div className="flex-1 flex items-center gap-2">
                                      <span className="text-sm font-medium text-gray-700">
                                        {variant.supplier.companyName}
                                      </span>
                                      {variant.products.length > 1 && (
                                        <span className="text-xs text-gray-500">
                                          (вариант {pIdx + 1})
                                        </span>
                                      )}
                                      {isBestPrice && (
                                        <Badge className="bg-green-600 text-white">
                                          <Award className="h-3 w-3 mr-1" />
                                          Лучшая цена
                                        </Badge>
                                      )}
                                      {!isAvailable && (
                                        <Badge variant="outline">Нет в наличии</Badge>
                                      )}
                                    </div>
                                    <div className="flex items-center gap-3">
                                      <div className="text-right">
                                        <p className={`font-bold ${isBestPrice ? 'text-green-600 text-lg' : 'text-gray-900'}`}>
                                          {product.price} ₽
                                        </p>
                                        <p className="text-xs text-gray-600">за {product.unit}</p>
                                      </div>
                                      <Button
                                        size="sm"
                                        onClick={() => addToCart(product, variant.supplier)}
                                        disabled={!isAvailable}
                                        className={isBestPrice ? 'bg-green-600 hover:bg-green-700' : ''}
                                        data-testid={`add-to-cart-${product.id}`}
                                      >
                                        <Plus className="h-4 w-4" />
                                      </Button>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })}

              {filteredGroups.length > 50 && (
                <p className="text-sm text-gray-600 text-center">
                  Показано 50 из {filteredGroups.length} товаров. Используйте поиск для уточнения.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Right sidebar - Cart */}
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
                {cart.map(item => (
                  <div key={item.cartId} className="flex items-start justify-between gap-2 pb-3 border-b">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{item.productName}</p>
                      <p className="text-xs text-gray-600">{item.supplierName}</p>
                      <p className="text-xs text-gray-600">{item.price} ₽/{item.unit}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => updateQuantity(item.cartId, -1)}
                          className="h-6 w-6 p-0"
                        >
                          <Minus className="h-3 w-3" />
                        </Button>
                        <span className="text-sm font-medium">{item.quantity}</span>
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
      </div>
    </div>
  );
};
