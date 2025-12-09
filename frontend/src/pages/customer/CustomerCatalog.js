import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ShoppingCart, Search, Plus, Minus, Trash2, Award, CheckCircle, Package } from 'lucide-react';

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
  const [showCart, setShowCart] = useState(false);
  const [showMiniCart, setShowMiniCart] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [showAddressModal, setShowAddressModal] = useState(false);
  const [processingOrder, setProcessingOrder] = useState(false);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [quantities, setQuantities] = useState({});

  useEffect(() => {
    fetchAllData();
    fetchCompanyInfo();
  }, []);

  useEffect(() => {
    filterProducts();
  }, [searchTerm, groupedProducts]);

  const fetchCompanyInfo = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/companies/my`, { headers });
      setCompany(response.data);
      // Auto-select first delivery address if only one exists
      if (response.data.deliveryAddresses && response.data.deliveryAddresses.length === 1) {
        setSelectedAddress(response.data.deliveryAddresses[0]);
      }
    } catch (error) {
      console.error('Failed to fetch company info:', error);
    }
  };

  const fetchAllData = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};

      // Fetch all suppliers
      const suppliersResponse = await axios.get(`${API}/suppliers`, { headers });
      setSuppliers(suppliersResponse.data);

      // Fetch products from each supplier
      const productsMap = {};
      for (const supplier of suppliersResponse.data) {
        const priceListResponse = await axios.get(`${API}/suppliers/${supplier.id}/price-lists`, { headers });
        productsMap[supplier.id] = {
          supplier: supplier,
          products: priceListResponse.data
        };
      }
      setAllProducts(productsMap);

      // Group products by identical name and unit
      const grouped = groupProductsForBestPrice(productsMap);
      setGroupedProducts(grouped);
      setFilteredGroups(grouped);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Group products that are identical (same name and unit) to find best prices
  const groupProductsForBestPrice = (productsMap) => {
    const productGroups = {};

    // Create groups based on article + productName + unit to avoid duplicates
    Object.entries(productsMap).forEach(([supplierId, { supplier, products }]) => {
      products.forEach(product => {
        // Use article as primary key if available, otherwise use product name
        const normalizedName = product.productName.toLowerCase().trim();
        const normalizedUnit = product.unit.toLowerCase().trim();
        const key = `${product.article.toLowerCase().trim()}|${normalizedName}|${normalizedUnit}`;
        
        if (!productGroups[key]) {
          productGroups[key] = {
            displayName: product.productName,
            unit: product.unit,
            article: product.article,
            searchText: `${product.productName} ${product.article} ${product.unit}`.toLowerCase(),
            offers: []
          };
        }

        // Check if this supplier already has this product (avoid duplicates from same supplier)
        const existingOffer = productGroups[key].offers.find(o => o.supplierId === supplier.id);
        if (!existingOffer) {
          productGroups[key].offers.push({
            priceListId: product.id,
            supplierId: supplier.id,
            supplierName: supplier.companyName,
            article: product.article,
            price: product.price,
            unit: product.unit,
            availability: product.availability,
            product: product
          });
        }
      });
    });

    // Convert to array and sort offers by price
    const groupedArray = Object.values(productGroups).map(group => {
      // Remove duplicate offers and sort by price (ascending)
      const uniqueOffers = group.offers.filter((offer, index, self) => 
        index === self.findIndex(o => o.supplierId === offer.supplierId && o.article === offer.article)
      );
      
      uniqueOffers.sort((a, b) => a.price - b.price);
      
      // Mark the best price
      if (uniqueOffers.length > 0) {
        uniqueOffers[0].isBestPrice = true;
      }

      return {
        ...group,
        offers: uniqueOffers,
        lowestPrice: uniqueOffers[0]?.price || 0
      };
    }).filter(group => group.offers.length > 0);

    // Sort groups by lowest price (best deals first)
    return groupedArray.sort((a, b) => a.lowestPrice - b.lowestPrice);
  };

  const filterProducts = () => {
    if (!searchTerm.trim()) {
      setFilteredGroups(groupedProducts);
      return;
    }

    const searchLower = searchTerm.toLowerCase().trim();
    const searchWords = searchLower.split(/\s+/);

    // Smart search: matches all words in any order
    const filtered = groupedProducts.filter(group => {
      const searchText = group.searchText;
      // Check if all search words are present
      return searchWords.every(word => searchText.includes(word));
    });

    // Sort filtered results by price (lowest first)
    const sortedFiltered = filtered.sort((a, b) => a.lowestPrice - b.lowestPrice);
    
    setFilteredGroups(sortedFiltered);
  };

  const addToCart = (offer, group, productKey) => {
    const qty = quantities[productKey] || 1;
    
    const cartItem = {
      cartId: `${offer.priceListId}_${Date.now()}`,
      priceListId: offer.priceListId,
      supplierId: offer.supplierId,
      supplierName: offer.supplierName,
      productName: group.displayName,
      article: offer.article,
      price: offer.price,
      unit: group.unit,
      quantity: qty,
      isBestPrice: offer.isBestPrice || false
    };

    setCart([...cart, cartItem]);
    
    // Reset quantity for this product
    setQuantities({ ...quantities, [productKey]: 1 });
  };

  const setProductQuantity = (productKey, value) => {
    const qty = Math.max(1, parseInt(value) || 1);
    setQuantities({ ...quantities, [productKey]: qty });
  };

  const updateCartQuantity = (cartId, delta) => {
    setCart(cart.map(item => {
      if (item.cartId === cartId) {
        const newQuantity = Math.max(1, item.quantity + delta);
        return { ...item, quantity: newQuantity };
      }
      return item;
    }));
  };

  const removeFromCart = (cartId) => {
    setCart(cart.filter(item => item.cartId !== cartId));
  };

  const getCartTotal = () => {
    return cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  };

  const handleCheckout = () => {
    // Check if multiple delivery addresses exist
    if (company && company.deliveryAddresses && company.deliveryAddresses.length > 1) {
      setShowAddressModal(true);
    } else {
      placeOrder();
    }
  };

  const placeOrder = async () => {
    if (cart.length === 0) return;

    // If multiple addresses exist and none selected, show address modal
    if (company && company.deliveryAddresses && company.deliveryAddresses.length > 1 && !selectedAddress) {
      setShowAddressModal(true);
      return;
    }

    setProcessingOrder(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      // Group cart items by supplier
      const ordersBySupplier = {};
      cart.forEach(item => {
        if (!ordersBySupplier[item.supplierId]) {
          ordersBySupplier[item.supplierId] = {
            supplierCompanyId: item.supplierId,
            items: []
          };
        }
        ordersBySupplier[item.supplierId].items.push({
          productName: item.productName,
          article: item.article,
          quantity: item.quantity,
          price: item.price,
          unit: item.unit
        });
      });

      // Create an order for each supplier
      const orderPromises = Object.values(ordersBySupplier).map(orderData => {
        const amount = orderData.items.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        return axios.post(`${API}/orders`, {
          supplierCompanyId: orderData.supplierCompanyId,
          amount: amount,
          orderDetails: orderData.items,
          deliveryAddress: selectedAddress
        }, { headers });
      });

      await Promise.all(orderPromises);

      // Clear cart and show success
      setCart([]);
      setShowCart(false);
      setShowAddressModal(false);
      setShowSuccessModal(true);
    } catch (error) {
      console.error('Failed to place order:', error);
      alert('Не удалось разместить заказ. Пожалуйста, попробуйте снова.');
    } finally {
      setProcessingOrder(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-lg">Загрузка каталога...</div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Fixed Mini Cart - Top Right Corner */}
      {cart.length > 0 && (
        <div className="fixed top-20 right-6 z-50 w-80">
          <Card className="shadow-xl">
            <div className="p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="font-semibold">В корзине ({cart.length})</h3>
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => setCart([])}
                  className="h-6 w-6 p-0"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {cart.slice(0, 5).map(item => (
                  <div key={item.cartId} className="text-sm p-2 bg-gray-50 rounded">
                    <p className="font-medium truncate">{item.productName}</p>
                    <div className="flex justify-between text-xs text-gray-600 mt-1">
                      <span>{item.quantity} {item.unit}</span>
                      <span className="font-medium">{(item.price * item.quantity).toFixed(2)} ₽</span>
                    </div>
                    <p className="text-xs text-blue-600 mt-1">{item.supplierName}</p>
                  </div>
                ))}
                {cart.length > 5 && (
                  <p className="text-xs text-gray-500 text-center">
                    +{cart.length - 5} товаров
                  </p>
                )}
              </div>
              <div className="border-t mt-3 pt-3">
                <div className="flex justify-between font-semibold mb-2">
                  <span>Итого:</span>
                  <span>{getCartTotal().toFixed(2)} ₽</span>
                </div>
                <Button 
                  onClick={() => setShowCart(true)}
                  className="w-full"
                  size="sm"
                >
                  Оформить заказ
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-4xl font-bold mb-2">Каталог товаров</h1>
          <p className="text-base text-muted-foreground">
            Лучшие цены от поставщиков
          </p>
        </div>
        
        {/* Cart Button */}
        <Button 
          onClick={() => setShowCart(true)} 
          className="relative"
          variant="default"
        >
          <ShoppingCart className="mr-2 h-4 w-4" />
          Корзина ({cart.length})
          {cart.length > 0 && (
            <Badge className="ml-2 bg-red-500">{cart.reduce((sum, item) => sum + item.quantity, 0)}</Badge>
          )}
        </Button>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Поиск: название, артикул, размер (например: креветки 31/40)..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
        {searchTerm && (
          <p className="text-sm text-muted-foreground mt-2">
            Найдено товаров: {filteredGroups.length} • Сортировка: от дешёвых к дорогим
          </p>
        )}
      </div>

      {/* Product Grid */}
      <div className="space-y-3">
        {filteredGroups.length === 0 ? (
          <Card className="p-8 text-center">
            <Package className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-lg text-muted-foreground">
              {searchTerm ? 'Товары не найдены' : 'Товаров пока нет'}
            </p>
          </Card>
        ) : (
          filteredGroups.map((group, idx) => (
            <Card key={idx} className="p-4 hover:shadow-md transition-shadow">
              {/* Price-First Display */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  {/* Price - Most Prominent */}
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-2xl font-bold text-green-600">
                      {group.lowestPrice.toFixed(2)} ₽
                    </span>
                    <span className="text-sm text-gray-600">/ {group.unit}</span>
                    {group.offers.length > 1 && (
                      <Badge variant="default" className="bg-green-600">
                        <Award className="h-3 w-3 mr-1" />
                        Best Price
                      </Badge>
                    )}
                  </div>
                  
                  {/* Product Name */}
                  <h3 className="text-base font-medium mb-1">{group.displayName}</h3>
                  <div className="flex items-center gap-2 text-sm text-gray-500">
                    <span>Артикул: {group.article}</span>
                    <span>•</span>
                    <span className="font-medium text-blue-600">
                      {group.offers[0]?.supplierName || 'Поставщик'}
                    </span>
                  </div>
                  
                  {/* Alternative Prices */}
                  {group.offers.length > 1 && (
                    <details className="mt-2">
                      <summary className="text-sm text-blue-600 cursor-pointer hover:text-blue-700">
                        + {group.offers.length - 1} других предложений
                      </summary>
                      <div className="mt-2 space-y-2 pl-4">
                        {group.offers.slice(1, 5).map((offer, offerIdx) => (
                          <div key={offerIdx} className="flex items-center justify-between text-sm p-2 bg-gray-50 rounded">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-700">{offer.price.toFixed(2)} ₽</span>
                              <span className="text-gray-500">/ {offer.unit}</span>
                            </div>
                            <span className="text-blue-600 font-medium">{offer.supplierName}</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
                
                {/* Quantity Selector and Add to Cart */}
                <div className="flex items-center gap-2 shrink-0">
                  <div className="flex items-center border rounded-md">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setProductQuantity(`${idx}`, (quantities[`${idx}`] || 1) - 1)}
                      disabled={(quantities[`${idx}`] || 1) <= 1}
                      className="h-8 w-8 p-0"
                    >
                      <Minus className="h-3 w-3" />
                    </Button>
                    <Input
                      type="number"
                      min="1"
                      value={quantities[`${idx}`] || 1}
                      onChange={(e) => setProductQuantity(`${idx}`, e.target.value)}
                      className="w-14 h-8 text-center border-0 focus-visible:ring-0 p-0"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setProductQuantity(`${idx}`, (quantities[`${idx}`] || 1) + 1)}
                      className="h-8 w-8 p-0"
                    >
                      <Plus className="h-3 w-3" />
                    </Button>
                  </div>
                  <Button 
                    onClick={() => addToCart(group.offers[0], group, `${idx}`)}
                    size="sm"
                  >
                    <ShoppingCart className="h-4 w-4 mr-1" />
                    В корзину
                  </Button>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>

      {/* Cart Dialog */}
      <Dialog open={showCart} onOpenChange={setShowCart}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-2xl">Корзина</DialogTitle>
            <DialogDescription>
              {cart.length === 0 ? 'Ваша корзина пуста' : `Товаров в корзине: ${cart.length}`}
            </DialogDescription>
          </DialogHeader>
          
          {cart.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              <ShoppingCart className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Добавьте товары в корзину</p>
            </div>
          ) : (
            <div className="space-y-4">
              {cart.map(item => (
                <Card key={item.cartId} className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-medium">{item.productName}</h4>
                        {item.isBestPrice && (
                          <Badge variant="default" className="bg-green-600 text-xs">
                            <Award className="h-3 w-3 mr-1" />
                            Best Price
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Цена: {item.price.toFixed(2)} ₽ / {item.unit}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Артикул: {item.article}
                      </p>
                      <p className="font-medium mt-2">
                        Итого: {(item.price * item.quantity).toFixed(2)} ₽
                      </p>
                    </div>
                    
                    <div className="flex flex-col items-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFromCart(item.cartId)}
                        className="text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                      
                      <div className="flex items-center gap-2 border rounded-md">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => updateCartQuantity(item.cartId, -1)}
                          disabled={item.quantity <= 1}
                        >
                          <Minus className="h-4 w-4" />
                        </Button>
                        <span className="px-3 font-medium">{item.quantity}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => updateCartQuantity(item.cartId, 1)}
                        >
                          <Plus className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
              
              <div className="border-t pt-4 mt-4">
                <div className="flex justify-between items-center mb-4">
                  <span className="text-lg font-semibold">Общая сумма:</span>
                  <span className="text-2xl font-bold">{getCartTotal().toFixed(2)} ₽</span>
                </div>
                
                <Button 
                  onClick={handleCheckout} 
                  disabled={processingOrder || cart.length === 0}
                  className="w-full"
                  size="lg"
                >
                  {processingOrder ? 'Оформление...' : 'Оформить заказ'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delivery Address Selection Modal */}
      <Dialog open={showAddressModal} onOpenChange={setShowAddressModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-xl">Выберите адрес доставки</DialogTitle>
            <DialogDescription>
              Пожалуйста, подтвердите адрес доставки для этого заказа
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-3 mt-4">
            {company?.deliveryAddresses && company.deliveryAddresses.map((address, index) => (
              <Card 
                key={index}
                className={`p-4 cursor-pointer transition-all ${
                  selectedAddress === address 
                    ? 'border-blue-500 bg-blue-50' 
                    : 'hover:border-gray-400'
                }`}
                onClick={() => setSelectedAddress(address)}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-5 h-5 rounded-full border-2 mt-0.5 flex items-center justify-center ${
                    selectedAddress === address 
                      ? 'border-blue-500 bg-blue-500' 
                      : 'border-gray-300'
                  }`}>
                    {selectedAddress === address && (
                      <div className="w-2 h-2 bg-white rounded-full"></div>
                    )}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">{address.address || address}</p>
                    {address.phone && (
                      <p className="text-sm text-muted-foreground mt-1">
                        Тел: {address.phone}
                      </p>
                    )}
                    {address.additionalPhone && (
                      <p className="text-sm text-muted-foreground">
                        Доп. тел: {address.additionalPhone}
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>

          <div className="flex gap-3 mt-6">
            <Button 
              variant="outline" 
              onClick={() => setShowAddressModal(false)}
              className="flex-1"
            >
              Отмена
            </Button>
            <Button 
              onClick={placeOrder}
              disabled={!selectedAddress || processingOrder}
              className="flex-1"
            >
              {processingOrder ? 'Оформление...' : 'Подтвердить заказ'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Success Modal */}
      <Dialog open={showSuccessModal} onOpenChange={setShowSuccessModal}>
        <DialogContent>
          <DialogHeader>
            <div className="flex items-center justify-center mb-4">
              <div className="rounded-full bg-green-100 p-3">
                <CheckCircle className="h-8 w-8 text-green-600" />
              </div>
            </div>
            <DialogTitle className="text-center text-2xl">Заказ принят!</DialogTitle>
            <DialogDescription className="text-center">
              Ваш заказ успешно размещен. Вы можете просмотреть детали заказа в истории заказов.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-center mt-4">
            <Button onClick={() => setShowSuccessModal(false)}>
              Продолжить покупки
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
