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
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [showAddressModal, setShowAddressModal] = useState(false);
  const [processingOrder, setProcessingOrder] = useState(false);
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);

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

    // Create groups based on productName + unit
    Object.entries(productsMap).forEach(([supplierId, { supplier, products }]) => {
      products.forEach(product => {
        const key = `${product.productName.toLowerCase().trim()}|${product.unit.toLowerCase().trim()}`;
        
        if (!productGroups[key]) {
          productGroups[key] = {
            displayName: product.productName,
            unit: product.unit,
            offers: []
          };
        }

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
      });
    });

    // Convert to array and sort offers by price
    const groupedArray = Object.values(productGroups).map(group => {
      // Sort offers by price (ascending)
      group.offers.sort((a, b) => a.price - b.price);
      
      // Mark the best price
      if (group.offers.length > 0) {
        group.offers[0].isBestPrice = true;
      }

      return group;
    }).filter(group => group.offers.length > 0);

    // Sort groups alphabetically by product name
    return groupedArray.sort((a, b) => a.displayName.localeCompare(b.displayName));
  };

  const filterProducts = () => {
    if (!searchTerm.trim()) {
      setFilteredGroups(groupedProducts);
      return;
    }

    const filtered = groupedProducts.filter(group =>
      group.displayName.toLowerCase().includes(searchTerm.toLowerCase())
    );
    setFilteredGroups(filtered);
  };

  const addToCart = (offer, group) => {
    const cartItem = {
      cartId: `${offer.priceListId}_${Date.now()}`,
      priceListId: offer.priceListId,
      supplierId: offer.supplierId,
      supplierName: offer.supplierName, // Hidden in cart, revealed in order history
      productName: group.displayName,
      article: offer.article,
      price: offer.price,
      unit: group.unit,
      quantity: 1,
      isBestPrice: offer.isBestPrice || false
    };

    setCart([...cart, cartItem]);
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
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-4xl font-bold mb-2">Каталог товаров</h1>
          <p className="text-base text-muted-foreground">
            Лучшие цены от поставщиков
          </p>
        </div>
        <Button 
          onClick={() => setShowCart(true)} 
          className="relative"
          variant="default"
        >
          <ShoppingCart className="mr-2 h-4 w-4" />
          Корзина ({cart.length})
        </Button>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Поиск товаров..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Product Grid */}
      <div className="space-y-4">
        {filteredGroups.length === 0 ? (
          <Card className="p-8 text-center">
            <Package className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-lg text-muted-foreground">
              {searchTerm ? 'Товары не найдены' : 'Товаров пока нет'}
            </p>
          </Card>
        ) : (
          filteredGroups.map((group, idx) => (
            <Card key={idx} className="p-6">
              <h3 className="text-xl font-semibold mb-4">{group.displayName}</h3>
              
              {/* Show all price options */}
              <div className="space-y-3">
                {group.offers.slice(0, 5).map((offer, offerIdx) => (
                  <div 
                    key={offerIdx}
                    className={`flex items-center justify-between p-4 rounded-lg border ${
                      offer.isBestPrice ? 'border-green-500 bg-green-50' : 'border-gray-200 bg-gray-50'
                    }`}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-lg">
                          {offer.price.toFixed(2)} ₽ / {offer.unit}
                        </span>
                        {offer.isBestPrice && (
                          <Badge variant="default" className="bg-green-600">
                            <Award className="h-3 w-3 mr-1" />
                            Best Price
                          </Badge>
                        )}
                        {group.offers.length === 1 && (
                          <Badge variant="secondary">
                            Единственное предложение
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        Артикул: {offer.article}
                      </p>
                    </div>
                    <Button 
                      onClick={() => addToCart(offer, group)}
                      size="sm"
                      variant={offer.isBestPrice ? "default" : "outline"}
                    >
                      <Plus className="h-4 w-4 mr-1" />
                      В корзину
                    </Button>
                  </div>
                ))}
              </div>

              {group.offers.length > 5 && (
                <p className="text-sm text-muted-foreground mt-3 text-center">
                  И ещё {group.offers.length - 5} предложений
                </p>
              )}
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
