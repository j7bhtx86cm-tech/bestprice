import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Loader2, Package, TrendingDown, Check, ShoppingCart, Building2, AlertCircle } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * Модальное окно выбора оффера (P1)
 * 
 * Показывает альтернативные предложения от разных поставщиков
 * для одного и того же товара.
 * 
 * GUARD: Модалка не рендерится пока sourceItem не установлен.
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
  const [error, setError] = useState(null);
  const [selectedOffer, setSelectedOffer] = useState(null);
  const [qty, setQty] = useState(1);
  // P0 DEBUG: Техническая информация для отладки
  const [debugInfo, setDebugInfo] = useState(null);

  // GUARD: Не загружаем данные если sourceItem не установлен
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
      setAlternatives([]);
      setError(null);
      setDebugInfo(null);
    }
  }, [isOpen]);

  const fetchAlternatives = async () => {
    // Double-check sourceItem exists
    if (!sourceItem?.id) {
      setError('Товар не выбран');
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      // v12: Cache-bust с timestamp + refetch при каждом открытии
      const ts = Date.now();
      const response = await axios.get(
        `${API}/api/v12/item/${sourceItem.id}/alternatives?ts=${ts}`,
        { 
          headers: {
            ...(getHeaders?.() || {}),
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          }
        }
      );
      
      const data = response.data;
      
      // P0 ZERO-TRASH: Сохраняем debug info для отображения в UI
      const refDebug = data.ref_debug || {};
      setDebugInfo({
        source: `/api/v12/item/${sourceItem.id}/alternatives`,
        ruleset_version: data.ruleset_version || 'unknown',
        debug_id: data.debug_id || 'none',
        ref_caliber: data.ref_parsed?.shrimp_caliber || refDebug.ref_caliber || 'null',
        ref_domain: data.ref_parsed?.npc_domain || refDebug.npc_domain || 'null',
        strict_count: data.strict_after_gates?.length || 0,
        rejected_reasons: data.rejected_reasons || {},
        // Расширенные поля ref_debug
        looks_like_shrimp: refDebug.looks_like_shrimp,
        has_caliber_pattern: refDebug.has_caliber_pattern,
        caliber_pattern_match: refDebug.caliber_pattern_match,
        why_legacy: refDebug.why_legacy,
      });
      
      // P0 ZERO-TRASH: DEBUG OUTPUT
      console.log('=== ZERO-TRASH STRICT DEBUG ===');
      console.log('debug_id:', data.debug_id);
      console.log('ruleset:', data.ruleset_version);
      console.log('ref_caliber:', data.ref_parsed?.shrimp_caliber);
      console.log('strict_after_gates:', data.strict_after_gates?.length);
      console.log('rejected_reasons:', data.rejected_reasons);
      console.log('total_candidates:', data.total_candidates);
      if (data.strict_after_gates?.[0]) {
        console.log('strict_after_gates[0].cand_parsed:', data.strict_after_gates[0].cand_parsed);
        console.log('strict_after_gates[0].passed_gates:', data.strict_after_gates[0].passed_gates);
      }
      console.log('================================');
      
      // P0 ZERO-TRASH: UI рендерит ТОЛЬКО strict_after_gates
      // ЗАПРЕЩЕНО: alternatives, similar, strict, сырые candidates
      // ЕДИНСТВЕННЫЙ источник данных — strict_after_gates
      const strictAfterGates = data.strict_after_gates || data.strict || [];
      
      // Защита: дополнительная валидация калибра на клиенте (belt-and-suspenders)
      const refCaliber = data.ref_parsed?.shrimp_caliber;
      const refDomain = data.ref_parsed?.npc_domain;
      
      if (refCaliber && refDomain === 'SHRIMP') {
        const validated = strictAfterGates.filter(item => {
          const candCaliber = item.cand_parsed?.shrimp_caliber;
          // REF имеет калибр, но кандидат нет → REJECT (CALIBER_UNKNOWN)
          if (!candCaliber) {
            console.warn(`[${data.debug_id}] CLIENT REJECT CALIBER_UNKNOWN: ${item.name_raw?.slice(0,40)}`);
            return false;
          }
          // Калибры не совпадают → REJECT (CALIBER_MISMATCH)
          if (candCaliber !== refCaliber) {
            console.warn(`[${data.debug_id}] CLIENT REJECT CALIBER_MISMATCH: ${candCaliber} != ${refCaliber}`);
            return false;
          }
          return true;
        });
        setAlternatives(validated);
      } else {
        setAlternatives(strictAfterGates);
      }
    } catch (err) {
      console.error('Failed to fetch alternatives:', err);
      setError('Не удалось загрузить альтернативы');
      setAlternatives([]);
    } finally {
      setLoading(false);
    }
  };

  const formatPrice = (price) => {
    if (!price && price !== 0) return '—';
    return `${price.toLocaleString('ru-RU')} ₽`;
  };

  const formatUnit = (unitType) => {
    if (unitType === 'WEIGHT') return 'кг';
    if (unitType === 'VOLUME') return 'л';
    return 'шт';
  };

  // Выбрать оффер и добавить в корзину
  const handleConfirm = () => {
    const offer = selectedOffer || sourceItem;
    if (offer && onSelect) {
      onSelect(offer, qty);
    }
    onClose();
  };

  // GUARD: Не рендерим диалог если sourceItem не установлен
  if (!sourceItem) {
    return null;
  }

  // Все офферы включая исходный
  const allOffers = [
    {
      ...sourceItem,
      supplier_name: sourceItem.supplier_name || 'Поставщик',
      isSource: true,
    },
    ...alternatives.map(a => ({ ...a, isSource: false }))
  ];

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="h-5 w-5" />
            Выберите предложение
          </DialogTitle>
          <DialogDescription>
            {sourceItem.name ? `${sourceItem.name.slice(0, 60)}${sourceItem.name.length > 60 ? '...' : ''}` : 'Товар'}
          </DialogDescription>
          {/* P0 DEBUG: Техническая плашка для отладки */}
          {debugInfo && (
            <div 
              className="mt-2 p-2 bg-gray-100 rounded text-xs font-mono text-gray-600 break-all"
              data-testid="debug-banner"
            >
              <div><strong>source=</strong>{debugInfo.source}</div>
              <div>
                <strong>ruleset=</strong>{debugInfo.ruleset_version} | 
                <strong> debug_id=</strong>{debugInfo.debug_id} | 
                <strong> ref_caliber=</strong>{debugInfo.ref_caliber}
              </div>
              <div>
                <strong>strict_count=</strong>{debugInfo.strict_count} | 
                <strong> rejected=</strong>{JSON.stringify(debugInfo.rejected_reasons)}
              </div>
            </div>
          )}
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
              <span className="ml-2 text-gray-500">Загрузка предложений...</span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-8 text-red-500">
              <AlertCircle className="h-8 w-8 mb-2" />
              <span>{error}</span>
            </div>
          ) : allOffers.length <= 1 ? (
            <div className="text-center py-8 text-gray-500" data-testid="no-strict-alternatives">
              <AlertCircle className="h-8 w-8 mx-auto mb-2 text-yellow-500" />
              <p className="font-medium">Нет сопоставимых предложений</p>
              <p className="text-sm mt-1">Strict-режим: альтернативы с точным совпадением параметров не найдены</p>
            </div>
          ) : (
            <div className="space-y-2">
              {allOffers.map((offer) => {
                const isSelected = selectedOffer?.id === offer.id || (offer.isSource && !selectedOffer);
                
                return (
                  <div
                    key={offer.id}
                    onClick={() => setSelectedOffer(offer.isSource ? null : offer)}
                    className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                      isSelected
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                    }`}
                    data-testid={`offer-option-${offer.id}`}
                  >
                    <div className="flex justify-between items-start gap-4">
                      {/* Левая часть - информация */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          {offer.isSource && (
                            <Badge variant="secondary" className="text-xs">
                              Текущий
                            </Badge>
                          )}
                          <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                            <Building2 className="h-3 w-3" />
                            {offer.supplier_name || 'Поставщик'}
                          </span>
                        </div>
                        
                        <p className="text-sm text-gray-600 truncate" title={offer.name}>
                          {offer.name || 'Без названия'}
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
                        
                        {isSelected && (
                          <div className="mt-1">
                            <Check className="h-5 w-5 text-blue-500 inline" />
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
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
              data-testid="offer-qty-input"
            />
            <span className="text-sm text-gray-500">
              {formatUnit(sourceItem.unit_type)}
            </span>
          </div>

          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Отмена
            </Button>
            <Button 
              onClick={handleConfirm}
              className="bg-blue-600 hover:bg-blue-700"
              disabled={loading || !!error}
              data-testid="confirm-offer-btn"
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              Выбрать и в корзину
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default OfferSelectModal;
