import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { Search, Loader2, Package, TrendingDown } from 'lucide-react';
import { Input } from '@/components/ui/input';

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * SearchAutocomplete - компонент поиска с автодополнением
 * 
 * Использует endpoint /api/v12/search/quick для быстрого поиска по lemma_tokens.
 * Поддерживает:
 * - Морфологический поиск (молоко/молока/молочный)
 * - Debounce (250ms)
 * - Keyboard navigation
 * - Click outside to close
 */
const SearchAutocomplete = ({ 
  value, 
  onChange, 
  onSelect,
  placeholder = "Поиск товаров...",
  className = ""
}) => {
  const [inputValue, setInputValue] = useState(value || '');
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  
  const inputRef = useRef(null);
  const dropdownRef = useRef(null);
  const debounceRef = useRef(null);

  // Sync with parent value
  useEffect(() => {
    if (value !== undefined && value !== inputValue) {
      setInputValue(value);
    }
  }, [value]);

  // Fetch suggestions
  const fetchSuggestions = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSuggestions([]);
      return;
    }

    setLoading(true);
    try {
      const response = await axios.get(`${API}/api/v12/search/quick`, {
        params: { q: query, limit: 8 }
      });
      setSuggestions(response.data.results || []);
      setShowDropdown(true);
    } catch (error) {
      console.error('Search error:', error);
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      fetchSuggestions(inputValue);
    }, 250);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [inputValue, fetchSuggestions]);

  // Handle input change
  const handleInputChange = (e) => {
    const newValue = e.target.value;
    setInputValue(newValue);
    setSelectedIndex(-1);
    
    // Also notify parent for regular search
    if (onChange) {
      onChange(newValue);
    }
  };

  // Handle suggestion click
  const handleSuggestionClick = (item) => {
    setInputValue(item.name_raw || item.name || '');
    setShowDropdown(false);
    setSuggestions([]);
    
    if (onSelect) {
      onSelect(item);
    } else if (onChange) {
      onChange(item.name_raw || item.name || '');
    }
  };

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (!showDropdown || suggestions.length === 0) {
      if (e.key === 'Enter') {
        setShowDropdown(false);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < suggestions.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : -1);
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && suggestions[selectedIndex]) {
          handleSuggestionClick(suggestions[selectedIndex]);
        } else {
          setShowDropdown(false);
        }
        break;
      case 'Escape':
        setShowDropdown(false);
        setSelectedIndex(-1);
        break;
      default:
        break;
    }
  };

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (
        dropdownRef.current && 
        !dropdownRef.current.contains(e.target) &&
        inputRef.current &&
        !inputRef.current.contains(e.target)
      ) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Format price
  const formatPrice = (price) => {
    if (!price && price !== 0) return '';
    return `${price.toLocaleString('ru-RU')} ₽`;
  };

  // Get unit label
  const getUnitLabel = (unitType) => {
    if (unitType === 'WEIGHT') return '/кг';
    if (unitType === 'VOLUME') return '/л';
    return '/шт';
  };

  return (
    <div className={`relative ${className}`}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <Input
          ref={inputRef}
          placeholder={placeholder}
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
          className="pl-10 pr-10"
          data-testid="search-autocomplete-input"
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 animate-spin" />
        )}
      </div>

      {/* Dropdown */}
      {showDropdown && suggestions.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-80 overflow-y-auto"
          data-testid="search-autocomplete-dropdown"
        >
          {suggestions.map((item, index) => (
            <div
              key={item.id || index}
              onClick={() => handleSuggestionClick(item)}
              className={`px-4 py-3 cursor-pointer border-b last:border-0 transition-colors ${
                index === selectedIndex 
                  ? 'bg-blue-50' 
                  : 'hover:bg-gray-50'
              }`}
              data-testid={`search-suggestion-${index}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 truncate">
                    {item.name_raw || item.name || 'Без названия'}
                  </p>
                  {item.super_class && (
                    <p className="text-xs text-gray-500 mt-0.5">
                      <Package className="inline h-3 w-3 mr-1" />
                      {item.super_class}
                    </p>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="flex items-center text-green-600 font-semibold">
                    <TrendingDown className="h-3 w-3 mr-1" />
                    {formatPrice(item.price)}
                    <span className="text-xs text-gray-500 ml-1">
                      {getUnitLabel(item.unit_type)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchAutocomplete;
