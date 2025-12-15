import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Upload, Plus, Pencil, Trash2, Check, X, Search } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const SupplierPriceList = () => {
  const [products, setProducts] = useState([]);
  const [filteredProducts, setFilteredProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [columnMapping, setColumnMapping] = useState(null);
  const [filePreview, setFilePreview] = useState(null);
  
  const [newProduct, setNewProduct] = useState({
    productName: '',
    article: '',
    price: '',
    unit: '',
    availability: true,
    active: true
  });

  useEffect(() => {
    fetchProducts();
  }, []);

  useEffect(() => {
    // Filter products when search term changes
    if (searchTerm.trim()) {
      const filtered = products.filter(p =>
        p.productName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.article.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.unit.toLowerCase().includes(searchTerm.toLowerCase())
      );
      setFilteredProducts(filtered);
    } else {
      setFilteredProducts(products);
    }
  }, [searchTerm, products]);

  const fetchProducts = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/price-lists/my`, { headers });
      setProducts(response.data);
      setFilteredProducts(response.data);
    } catch (error) {
      console.error('Failed to fetch products:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddProduct = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.post(`${API}/price-lists`, {
        ...newProduct,
        price: parseFloat(newProduct.price)
      }, { headers });
      setMessage('Товар успешно добавлен');
      setIsAddDialogOpen(false);
      setNewProduct({
        productName: '',
        article: '',
        price: '',
        unit: '',
        availability: true,
        active: true
      });
      fetchProducts();
    } catch (error) {
      setMessage('Ошибка при добавлении товара');
    }
  };

  const handleUpdateProduct = async (productId, updates) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.put(`${API}/price-lists/${productId}`, updates, { headers });
      setMessage('Товар обновлен');
      setEditingProduct(null);
      fetchProducts();
    } catch (error) {
      setMessage('Ошибка при обновлении');
    }
  };

  const handleDeleteProduct = async (productId) => {
    if (!window.confirm('Удалить этот товар?')) return;
    
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.delete(`${API}/price-lists/${productId}`, { headers });
      setMessage('Товар удален');
      fetchProducts();
    } catch (error) {
      setMessage('Ошибка при удалении');
    }
  };

  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!uploadFile) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const formData = new FormData();
      formData.append('file', uploadFile);

      const response = await axios.post(`${API}/price-lists/upload`, formData, { headers });
      setFilePreview(response.data);
      setColumnMapping({
        productName: response.data.columns[0] || '',
        article: response.data.columns[1] || '',
        price: response.data.columns[2] || '',
        unit: response.data.columns[3] || ''
      });
    } catch (error) {
      setMessage('Ошибка при загрузке файла');
    }
  };

  const handleImport = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('column_mapping', JSON.stringify(columnMapping));

      await axios.post(`${API}/price-lists/import`, formData, { headers });
      setMessage('Прайс-лист успешно импортирован');
      setIsUploadDialogOpen(false);
      setUploadFile(null);
      setFilePreview(null);
      setColumnMapping(null);
      fetchProducts();
    } catch (error) {
      setMessage('Ошибка при импорте');
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="supplier-pricelist-page">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Прайс-лист</h2>
        <div className="flex gap-2">
          <Dialog open={isUploadDialogOpen} onOpenChange={setIsUploadDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" data-testid="upload-pricelist-btn">
                <Upload className="h-4 w-4 mr-2" />
                Загрузить файл
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Загрузка прайс-листа</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                {!filePreview ? (
                  <form onSubmit={handleFileUpload} className="space-y-4">
                    <div>
                      <Label>Выберите файл (CSV или Excel)</Label>
                      <Input
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        onChange={(e) => setUploadFile(e.target.files[0])}
                        required
                      />
                    </div>
                    <Button type="submit">Загрузить и просмотреть</Button>
                  </form>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-medium mb-2">Сопоставление колонок</h4>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label>Название товара</Label>
                          <select
                            value={columnMapping.productName}
                            onChange={(e) => setColumnMapping({...columnMapping, productName: e.target.value})}
                            className="w-full px-3 py-2 border rounded-md"
                          >
                            {filePreview.columns.map(col => (
                              <option key={col} value={col}>{col}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <Label>Артикул</Label>
                          <select
                            value={columnMapping.article}
                            onChange={(e) => setColumnMapping({...columnMapping, article: e.target.value})}
                            className="w-full px-3 py-2 border rounded-md"
                          >
                            {filePreview.columns.map(col => (
                              <option key={col} value={col}>{col}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <Label>Цена</Label>
                          <select
                            value={columnMapping.price}
                            onChange={(e) => setColumnMapping({...columnMapping, price: e.target.value})}
                            className="w-full px-3 py-2 border rounded-md"
                          >
                            {filePreview.columns.map(col => (
                              <option key={col} value={col}>{col}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <Label>Единица</Label>
                          <select
                            value={columnMapping.unit}
                            onChange={(e) => setColumnMapping({...columnMapping, unit: e.target.value})}
                            className="w-full px-3 py-2 border rounded-md"
                          >
                            {filePreview.columns.map(col => (
                              <option key={col} value={col}>{col}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>
                    <div>
                      <h4 className="font-medium mb-2">Предпросмотр (первые 5 строк)</h4>
                      <div className="overflow-x-auto max-h-60 border rounded-md">
                        <table className="w-full text-sm">
                          <thead className="bg-gray-50">
                            <tr>
                              {filePreview.columns.map(col => (
                                <th key={col} className="px-3 py-2 text-left">{col}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {filePreview.preview.map((row, idx) => (
                              <tr key={idx} className="border-t">
                                {filePreview.columns.map(col => (
                                  <td key={col} className="px-3 py-2">{row[col]}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="text-sm text-gray-600 mt-2">
                        Всего строк: {filePreview.total_rows}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button onClick={handleImport}>Импортировать {filePreview.total_rows} товаров</Button>
                      <Button variant="outline" onClick={() => {
                        setFilePreview(null);
                        setColumnMapping(null);
                        setUploadFile(null);
                      }}>
                        Отмена
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </DialogContent>
          </Dialog>

          <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
            <DialogTrigger asChild>
              <Button data-testid="add-product-btn">
                <Plus className="h-4 w-4 mr-2" />
                Добавить товар
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Добавить товар</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleAddProduct} className="space-y-4">
                <div>
                  <Label htmlFor="productName">Название товара</Label>
                  <Input
                    id="productName"
                    value={newProduct.productName}
                    onChange={(e) => setNewProduct({...newProduct, productName: e.target.value})}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="article">Артикул</Label>
                  <Input
                    id="article"
                    value={newProduct.article}
                    onChange={(e) => setNewProduct({...newProduct, article: e.target.value})}
                    required
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="price">Цена</Label>
                    <Input
                      id="price"
                      type="number"
                      step="0.01"
                      value={newProduct.price}
                      onChange={(e) => setNewProduct({...newProduct, price: e.target.value})}
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="unit">Единица</Label>
                    <Input
                      id="unit"
                      value={newProduct.unit}
                      onChange={(e) => setNewProduct({...newProduct, unit: e.target.value})}
                      placeholder="кг, шт, л"
                      required
                    />
                  </div>
                </div>
                <Button type="submit" className="w-full">Добавить</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {message && (
        <Alert className="mb-4" variant={message.includes('успешно') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      {products.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600 mb-4">Прайс-лист пуст</p>
          <p className="text-sm text-gray-500">Добавьте товары вручную или загрузите файл</p>
        </Card>
      ) : (
        <>
          {/* Search Input */}
          <div className="mb-4">
            <div className="relative">
              <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Поиск по названию, артикулу, единице..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            {searchTerm && (
              <p className="text-sm text-muted-foreground mt-2">
                Найдено: {filteredProducts.length} из {products.length} товаров
              </p>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium">Товар</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Артикул</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Цена</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Ед.</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Наличие</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Действия</th>
                </tr>
              </thead>
            <tbody className="bg-white divide-y">
              {filteredProducts.map((product) => (
                <tr key={product.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span className="font-medium">{product.productName}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">{product.article}</td>
                  <td className="px-4 py-3">
                    {editingProduct?.id === product.id ? (
                      <Input
                        type="number"
                        step="0.01"
                        value={editingProduct.price}
                        onChange={(e) => setEditingProduct({...editingProduct, price: parseFloat(e.target.value)})}
                        className="w-24"
                      />
                    ) : (
                      <span className="font-medium">{product.price} ₽</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm">{product.unit}</td>
                  <td className="px-4 py-3">
                    {editingProduct?.id === product.id ? (
                      <Switch
                        checked={editingProduct.availability}
                        onCheckedChange={(checked) => setEditingProduct({...editingProduct, availability: checked})}
                      />
                    ) : (
                      <Badge className={product.availability ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}>
                        {product.availability ? 'В наличии' : 'Нет'}
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {editingProduct?.id === product.id ? (
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleUpdateProduct(product.id, {
                            price: editingProduct.price,
                            availability: editingProduct.availability
                          })}
                        >
                          <Check className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingProduct(null)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingProduct(product)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDeleteProduct(product.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </>
      )}

      <Card className="p-4 mt-6 bg-blue-50 border-blue-200">
        <p className="text-sm text-gray-700">
          <strong>Совет:</strong> Загрузите полный прайс-лист из файла Excel или CSV для быстрого добавления товаров.
          Поддерживаются форматы: .csv, .xlsx, .xls
        </p>
      </Card>
    </div>
  );
};