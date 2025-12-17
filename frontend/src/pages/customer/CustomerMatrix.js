import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useParams } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Plus, Search, Edit2, Trash2, ShoppingCart } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerMatrix = () => {
  const { matrixId } = useParams();
  const { user } = useAuth();
  const [matrix, setMatrix] = useState(null);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddProductModal, setShowAddProductModal] = useState(false);
  const [showModeSelectionModal, setShowModeSelectionModal] = useState(false);
  const [selectedProductToAdd, setSelectedProductToAdd] = useState(null);
  const [selectedMode, setSelectedMode] = useState('exact');
  const [showOrderModal, setShowOrderModal] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [orderItems, setOrderItems] = useState([]);

  const isAdmin = user?.role === 'customer';
  const isChefOrStaff = user?.role === 'chef' || user?.role === 'responsible';

  useEffect(() => {
    // If chef/staff and no matrixId, get their assigned matrix
    if (isChefOrStaff && !matrixId) {
      fetchUserMatrix();
    } else if (matrixId) {
      fetchMatrix();
      fetchMatrixProducts();
    }
  }, [matrixId, isChefOrStaff]);

  const fetchUserMatrix = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/matrices`, { headers });
      if (response.data.length > 0) {
        const userMatrix = response.data[0];
        window.location.href = `/customer/matrix/${userMatrix.id}`;
      }
    } catch (error) {
      console.error('Failed to fetch user matrix:', error);
    }
  };

  const fetchMatrix = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/matrices/${matrixId}`, { headers });
      setMatrix(response.data);
    } catch (error) {
      console.error('Failed to fetch matrix:', error);
    }
  };

  const fetchMatrixProducts = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/matrices/${matrixId}/products`, { headers });
      setProducts(response.data);
    } catch (error) {
      console.error('Failed to fetch matrix products:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchProducts = async () => {
    if (!searchTerm.trim()) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      // Get all suppliers
      const suppliersResponse = await axios.get(`${API}/suppliers`, { headers });
      
      // Search across all suppliers
      const allResults = [];
      for (const supplier of suppliersResponse.data) {
        try {
          const response = await axios.get(
            `${API}/suppliers/${supplier.id}/price-lists?search=${encodeURIComponent(searchTerm)}`,
            { headers }
          );
          allResults.push(...response.data.map(p => ({ ...p, supplierId: supplier.id, supplierName: supplier.companyName })));
        } catch (err) {
          console.error(`Failed to search supplier ${supplier.companyName}:`, err);
        }
      }
      setSearchResults(allResults);
    } catch (error) {
      console.error('Failed to search products:', error);
    }
  };

  const handleAddProduct = async (product) => {
    // First show mode selection dialog
    setSelectedProductToAdd(product);
    setSelectedMode('exact');
    setShowModeSelectionModal(true);
  };

  const confirmAddProduct = async () => {
    if (!selectedProductToAdd) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      // Find the productId
      const productsResponse = await axios.get(`${API}/suppliers`, { headers });
      let productId = null;
      
      for (const supplier of productsResponse.data) {
        const priceListResponse = await axios.get(`${API}/suppliers/${supplier.id}/price-lists`, { headers });
        const found = priceListResponse.data.find(p => p.productName === selectedProductToAdd.productName);
        if (found) {
          productId = found.id;
          break;
        }
      }

      if (!productId) {
        alert('Продукт не найден в глобальном каталоге');
        return;
      }

      await axios.post(
        `${API}/matrices/${matrixId}/products`,
        { 
          productId: productId,
          mode: selectedMode  // Send selected mode
        },
        { headers }
      );
      
      setShowAddProductModal(false);
      setShowModeSelectionModal(false);
      setSelectedProductToAdd(null);
      setSearchTerm('');
      setSearchResults([]);
      fetchMatrixProducts();
    } catch (error) {
      console.error('Failed to add product:', error);
      alert('Ошибка добавления продукта');
    }
  };

  const handleRemoveProduct = async (productId) => {
    if (!confirm('Удалить этот продукт из матрицы?')) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.delete(`${API}/matrices/${matrixId}/products/${productId}`, { headers });
      fetchMatrixProducts();
    } catch (error) {
      console.error('Failed to remove product:', error);
    }
  };

  const handleCreateOrder = () => {
    // Initialize order items from matrix
    const items = products.map(p => ({
      rowNumber: p.rowNumber,
      productName: p.productName,
      quantity: 0,
      bestPrice: p.bestPrice,
      unit: p.unit
    }));
    setOrderItems(items);
    setShowOrderModal(true);
  };

  const handleSubmitOrder = async () => {
    const itemsToOrder = orderItems.filter(item => item.quantity > 0);
    
    if (itemsToOrder.length === 0) {
      alert('Добавьте товары в заказ');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const orderData = {
        matrixId: matrixId,
        items: itemsToOrder.map(item => ({
          rowNumber: item.rowNumber,
          quantity: item.quantity
        }))
      };

      await axios.post(`${API}/matrices/${matrixId}/orders`, orderData, { headers });
      
      alert('Заказ успешно создан!');
      setShowOrderModal(false);
      fetchMatrixProducts(); // Refresh to update last order quantities
    } catch (error) {
      console.error('Failed to create order:', error);
      alert('Ошибка создания заказа');
    }
  };

  if (loading || !matrix) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">{matrix.name}</h2>
          <p className="text-base text-muted-foreground">
            {isChefOrStaff ? 'Ваша продуктовая матрица' : 'Управление продуктами в матрице'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => setShowAddProductModal(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Добавить продукт
          </Button>
          {isChefOrStaff && products.length > 0 && (
            <Button onClick={handleCreateOrder} variant="default">
              <ShoppingCart className="h-4 w-4 mr-2" />
              Создать заказ
            </Button>
          )}
        </div>
      </div>

      {products.length === 0 ? (
        <Card className="p-12 text-center">
          <p className="text-gray-600 mb-4">В матрице пока нет продуктов</p>
          <Button onClick={() => setShowAddProductModal(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Добавить первый продукт
          </Button>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">№</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Название</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Артикул</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Ед. изм.</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Лучшая цена</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Поставщик</th>
                  {isChefOrStaff && (
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Посл. заказ</th>
                  )}
                  {isAdmin && (
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Действия</th>
                  )}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {products.map((product) => (
                  <tr key={product.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm font-medium">{product.rowNumber}</td>
                    <td className="px-4 py-3 text-sm">{product.productName}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">{product.productCode}</td>
                    <td className="px-4 py-3 text-sm">{product.unit}</td>
                    <td className="px-4 py-3 text-sm font-medium text-green-600">
                      {product.bestPrice ? `${product.bestPrice.toLocaleString('ru-RU')} ₽` : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{product.bestSupplier || '-'}</td>
                    {isChefOrStaff && (
                      <td className="px-4 py-3 text-sm">{product.lastOrderQuantity || '-'}</td>
                    )}
                    {isAdmin && (
                      <td className="px-4 py-3 text-sm">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveProduct(product.id)}
                          className="text-red-600 hover:text-red-700"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Add Product Modal */}
      <Dialog open={showAddProductModal} onOpenChange={setShowAddProductModal}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Добавить продукт в матрицу</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="flex gap-2">
              <Input
                placeholder="Поиск по названию или коду"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearchProducts()}
              />
              <Button onClick={handleSearchProducts}>
                <Search className="h-4 w-4 mr-2" />
                Искать
              </Button>
            </div>

            {searchResults.length > 0 && (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {searchResults.slice(0, 50).map((product, idx) => (
                  <Card key={idx} className="p-4 hover:bg-gray-50">
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <h4 className="font-medium">{product.productName}</h4>
                        <p className="text-sm text-gray-600">Артикул: {product.article}</p>
                        <p className="text-sm text-gray-600">Поставщик: {product.supplierName}</p>
                        <p className="text-sm font-medium text-green-600">
                          {product.price.toLocaleString('ru-RU')} ₽ / {product.unit}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        onClick={() => handleAddProduct(product)}
                      >
                        <Plus className="h-4 w-4 mr-1" />
                        Добавить
                      </Button>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Order Modal */}
      <Dialog open={showOrderModal} onOpenChange={setShowOrderModal}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Создать заказ по матрице</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <p className="text-sm text-gray-600">Введите количество для каждой позиции:</p>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {orderItems.map((item, idx) => (
                <div key={idx} className="flex items-center gap-4 p-3 border rounded">
                  <div className="w-12 font-medium">№{item.rowNumber}</div>
                  <div className="flex-1">
                    <p className="font-medium">{item.productName}</p>
                    <p className="text-sm text-gray-600">
                      {item.bestPrice?.toLocaleString('ru-RU')} ₽ / {item.unit}
                    </p>
                  </div>
                  <Input
                    type="number"
                    min="0"
                    step="0.1"
                    placeholder="0"
                    value={item.quantity || ''}
                    onChange={(e) => {
                      const newItems = [...orderItems];
                      newItems[idx].quantity = parseFloat(e.target.value) || 0;
                      setOrderItems(newItems);
                    }}
                    className="w-32"
                  />
                  <span className="text-sm text-gray-600 w-16">{item.unit}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2 pt-4 border-t">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setShowOrderModal(false)}
              >
                Отмена
              </Button>
              <Button
                className="flex-1"
                onClick={handleSubmitOrder}
              >
                Отправить заказ
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
