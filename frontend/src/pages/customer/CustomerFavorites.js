import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Heart, Trash2, ShoppingCart, TrendingDown, Search, CheckCircle, AlertCircle, GripVertical } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Sortable Item Component
function SortableItem({ favorite, onRemove, onModeChange, onBrandStrictChange, addToCart }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: favorite.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} className={isDragging ? 'z-50' : ''}>
      <Card className={`p-5 hover:shadow-lg transition-all relative ${
        isDragging ? 'shadow-2xl scale-105 cursor-grabbing' : 'hover:border-2 hover:border-blue-300'
      }`}>
        {/* Drag Handle */}
        <div
          {...attributes}
          {...listeners}
          className="absolute top-2 left-2 cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600 touch-none"
        >
          <GripVertical className="h-5 w-5" />
        </div>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRemove(favorite.id)}
          className="absolute top-2 right-2 text-red-500 hover:text-red-600 z-10"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
        
        {/* Main Product Name */}
        <div className="mb-4 ml-6">
          <h3 className="font-semibold text-lg mb-1 pr-8">
            {favorite.productName}
          </h3>
          <p className="text-sm text-gray-600">Артикул: {favorite.productCode || 'Н/Д'}</p>
        </div>

        {/* Brand Toggle - only for branded products */}
        {favorite.isBranded && (
          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <label htmlFor={`brand-${favorite.id}`} className="text-sm font-medium text-gray-700">
                Не учитывать бренд
              </label>
              <Switch
                id={`brand-${favorite.id}`}
                checked={favorite.brandMode === 'ANY'}
                onCheckedChange={(checked) => onBrandModeChange(favorite.id, checked ? 'ANY' : 'STRICT')}
              />
            </div>
            <p className="text-xs text-gray-500">
              {favorite.brandMode === 'ANY' 
                ? 'Любой бренд - ищем самый дешёвый' 
                : `Только ${favorite.brand || 'этот'} бренд`}
            </p>
          </div>
        )}

        {/* Quantity and unit */}
        <div className="mb-4 p-3 bg-white border rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">Ед. изм:</span>
            <span className="text-sm font-medium">{favorite.unit}</span>
          </div>
        </div>

        {/* Add to cart button */}
        <div className="pt-2">
          <Button
            onClick={() => addToCart(favorite)}
            className="w-full"
            variant="default"
          >
            <ShoppingCart className="h-4 w-4 mr-2" />
            Добавить в корзину
          </Button>
        </div>
                Найдено {favorite.matchCount} похожих товаров
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

export const CustomerFavorites = () => {
  const [favorites, setFavorites] = useState([]);
  const [filteredFavorites, setFilteredFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [company, setCompany] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [draggedItem, setDraggedItem] = useState(null);

  useEffect(() => {
    fetchFavorites();
    fetchCompanyInfo();
  }, []);

  useEffect(() => {
    // Filter favorites when search term changes
    if (searchTerm.trim()) {
      const filtered = favorites.filter(f =>
        f.productName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (f.productCode && f.productCode.toLowerCase().includes(searchTerm.toLowerCase()))
      );
      setFilteredFavorites(filtered);
    } else {
      setFilteredFavorites(favorites);
    }
  }, [searchTerm, favorites]);

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

  const fetchFavorites = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/favorites/v2`, { headers });
      setFavorites(response.data);
      setFilteredFavorites(response.data);
    } catch (error) {
      console.error('Failed to fetch favorites:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveFavorite = async (favoriteId) => {
    if (!confirm('Удалить из избранного?')) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.delete(`${API}/favorites/${favoriteId}`, { headers });
      fetchFavorites();
    } catch (error) {
      console.error('Failed to remove favorite:', error);
    }
  };

  const onBrandModeChange = async (favoriteId, brandMode) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.put(`${API}/favorites/${favoriteId}/brand-mode`, { brandMode }, { headers });
      fetchFavorites();
    } catch (error) {
      console.error('Failed to update brand mode:', error);
    }
  };

  const addToCart = (favorite) => {
    const cartItem = {
      cartId: `fav_${favorite.id}_${Date.now()}`,
      favoriteId: favorite.id,
      productName: favorite.productName,
      quantity: 1,
      price: favorite.bestPrice || favorite.originalPrice || 0,
      unit: favorite.unit,
      bestSupplier: favorite.bestSupplier
    };

    // Add to GENERAL cart (catalogCart), not separate favoriteCart
    const existingCart = JSON.parse(localStorage.getItem('catalogCart') || '[]');
    
    // Check if already in cart
    const alreadyInCart = existingCart.some(item => item.favoriteId === favorite.id);
    
    if (alreadyInCart) {
      alert('Этот товар уже в корзине');
      return;
    }

    // Add to cart
    existingCart.push(cartItem);
    localStorage.setItem('catalogCart', JSON.stringify(existingCart));
    
    alert('Товар добавлен в корзину!');
  };

  const handleModeChange = async (favoriteId, newMode) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.put(`${API}/favorites/${favoriteId}/mode`, { mode: newMode }, { headers });
      fetchFavorites(); // Refresh to show updated mode
    } catch (error) {
      console.error('Failed to update mode:', error);
    }
  };

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = async (event) => {
    const { active, over } = event;
    
    if (!over || active.id === over.id) return;

    const oldIndex = filteredFavorites.findIndex(f => f.id === active.id);
    const newIndex = filteredFavorites.findIndex(f => f.id === over.id);
    
    // Reorder locally for immediate feedback
    const reordered = arrayMove(filteredFavorites, oldIndex, newIndex);
    setFilteredFavorites(reordered);

    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      // Send new order to backend
      const orderMap = reordered.map((fav, index) => ({
        id: fav.id,
        displayOrder: index
      }));
      
      await axios.post(`${API}/favorites/reorder`, { favorites: orderMap }, { headers });
      
      // Refresh from server
      fetchFavorites();
    } catch (error) {
      console.error('Failed to reorder:', error);
      // Revert on error
      fetchFavorites();
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Избранное</h2>
          <p className="text-base text-muted-foreground">
            Быстрый заказ часто используемых товаров
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Global Best Price Toggle */}
          {favorites.length > 0 && (
            <div className="flex items-center gap-3 p-3 border rounded-lg bg-white">
              <div className="text-right">
                <p className="text-sm font-medium">Искать лучшую цену для всех</p>
                <p className="text-xs text-gray-500">Включить для всех товаров</p>
              </div>
              <Switch
                checked={favorites.every(f => f.mode === 'cheapest')}
                onCheckedChange={async (checked) => {
                  const mode = checked ? 'cheapest' : 'exact';
                  const token = localStorage.getItem('token');
                  const headers = token ? { Authorization: `Bearer ${token}` } : {};
                  
                  // Update all favorites
                  for (const fav of favorites) {
                    try {
                      await axios.put(`${API}/favorites/${fav.id}/mode`, { mode }, { headers });
                    } catch (err) {
                      console.error('Failed to update mode:', err);
                    }
                  }
                  
                  // Refresh
                  fetchFavorites();
                }}
              />
            </div>
          )}
        </div>
      </div>

      {/* Search */}
      {favorites.length > 0 && (
        <div className="mb-6">
          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Поиск по названию или артикулу..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          {searchTerm && (
            <p className="text-sm text-muted-foreground mt-2">
              Найдено: {filteredFavorites.length} из {favorites.length}
            </p>
          )}
        </div>
      )}

      {filteredFavorites.length === 0 && searchTerm ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600">Товары не найдены</p>
        </Card>
      ) : favorites.length === 0 ? (
        <Card className="p-12 text-center">
          <Heart className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-2">У вас пока нет избранных товаров</p>
          <p className="text-sm text-gray-500">Добавляйте товары в избранное из каталога для быстрого заказа</p>
        </Card>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={filteredFavorites.map(f => f.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredFavorites.map((favorite) => (
                <SortableItem
                  key={favorite.id}
                  favorite={favorite}
                  onRemove={handleRemoveFavorite}
                  onModeChange={handleModeChange}
                  onBrandStrictChange={onBrandStrictChange}
                  addToCart={addToCart}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Create Order Modal */}
    </div>
  );
};
