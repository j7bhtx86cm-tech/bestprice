import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../../components/ui/dialog';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { Loader2, Package, TrendingDown, Check, ShoppingCart, Building2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * Модальное окно выбора оффера (P1)
 * 
 * Показывает альтернативные предложения от разных поставщиков
 * для одного и того же товара.
 */
const OfferSelectModal = ({ 
  isOpen, 
  onClose, 
  sourceItem, 
  onSelect,
  getHeaders 
}) => {
  const [alternatives, setAlternatives] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedOffer, setSelectedOffer] = useState(null);
  const [qty, setQty] = useState(1);

  // Загружаем альтернативы при открытии
  useEffect(() => {
    if (isOpen && sourceItem?.id) {
      fetchAlternatives();
    }
  }, [isOpen, sourceItem?.id]);

  // Сброс при закрытии
  useEffect(() => {
    if (!isOpen) {
      setSelectedOffer(null);
      setQty(1);
    }
  }, [isOpen]);

  const fetchAlternatives = async () => {
    setLoading(true);
    try {
      const response = await axios.get(
        `${API}/v12/item/${sourceItem.id}/alternatives`,
        { headers: getHeaders?.() || {} }
      );
      setAlternatives(response.data.alternatives || []);
    } catch (error) {
      console.error('Failed to fetch alternatives:', error);
      setAlternatives([]);
    } finally {
      setLoading(false);
    }
  };

  const formatPrice = (price) => {
    if (!price) return '—';
    return `${price.toLocaleString('ru-RU')} ₽`;
  };

  const formatUnit = (unitType) => {
    if (unitType === 'WEIGHT') return 'кг';
    if (unitType === 'VOLUME') return 'л';
    return 'шт';
  };

  const handleConfirm = () => {
    const offer = selectedOffer || sourceItem;
    onSelect(offer, qty);
    onClose();
  };

  // Все офферы включая исходный
  const allOffers = [
    {
      ...sourceItem,
      supplier_name: sourceItem.supplier_name || 'Поставщик',
      isSource: true,
    },
    ...alternatives.map(a => ({ ...a, isSource: false }))
  ].filter(Boolean);

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="h-5 w-5" />
            Выберите предложение
          </DialogTitle>
          <DialogDescription>
            {sourceItem?.name?.slice(0, 60)}...
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
              <span className="ml-2 text-gray-500">Загрузка предложений...</span>
            </div>
          ) : allOffers.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              Нет альтернативных предложений
            </div>
          ) : (
            <div className="space-y-2">
              {allOffers.map((offer) => (
                <div
                  key={offer.id}
                  onClick={() => setSelectedOffer(offer.isSource ? null : offer)}
                  className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                    (selectedOffer?.id === offer.id || (offer.isSource && !selectedOffer))
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                  }`}
                  data-testid={`offer-option-${offer.id}`}
                >
                  <div className="flex justify-between items-start gap-4">
                    {/* Левая часть - информация */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {offer.isSource && (
                          <Badge variant="secondary" className="text-xs">
                            Текущий
                          </Badge>
                        )}
                        <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                          <Building2 className="h-3 w-3" />
                          {offer.supplier_name}
                        </span>
                      </div>
                      
                      <p className="text-sm text-gray-600 truncate" title={offer.name}>
                        {offer.name}
                      </p>
                      
                      {offer.pack_qty && (
                        <p className="text-xs text-gray-500 mt-1">
                          Фасовка: {offer.pack_qty} {formatUnit(offer.unit_type)}
                        </p>
                      )}
                    </div>

                    {/* Правая часть - цена и выбор */}
                    <div className="text-right flex-shrink-0">
                      <div className="flex items-center gap-1 justify-end">
                        <TrendingDown className="h-4 w-4 text-green-600" />
                        <span className="text-lg font-bold text-green-600">
                          {formatPrice(offer.price)}
                        </span>
                      </div>
                      
                      {(selectedOffer?.id === offer.id || (offer.isSource && !selectedOffer)) && (
                        <div className="mt-1">
                          <Check className="h-5 w-5 text-blue-500 inline" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer с количеством и кнопкой */}
        <div className="border-t pt-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600">Количество:</label>
            <Input
              type="number"
              min="1"
              value={qty}
              onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
              className="w-20"
            />
            <span className="text-sm text-gray-500">
              {formatUnit(sourceItem?.unit_type)}
            </span>
          </div>

          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Отмена
            </Button>
            <Button 
              onClick={handleConfirm}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="confirm-offer-btn"
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              В корзину
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default OfferSelectModal;
