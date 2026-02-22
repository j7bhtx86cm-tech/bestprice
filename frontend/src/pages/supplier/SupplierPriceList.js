import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Upload, Plus, Pencil, Trash2, Check, X, Search, Loader2, ChevronDown, Download } from 'lucide-react';
import { toast } from 'sonner';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8001';
const API = `${BACKEND_URL}/api`;

// Словарь текстов (RU)
const T = {
  pageTitle: 'Прайс-лист',
  uploadFile: 'Загрузить файл',
  addProduct: 'Добавить товар',
  modalTitle: 'Загрузка прайс-листа',
  selectFile: 'Выберите файл (CSV или Excel)',
  uploadAndReview: 'Загрузить и просмотреть',
  columnMapping: 'Сопоставление колонок',
  productName: 'Название',
  packQty: 'Кол-во в упаковке',
  minOrder: 'Минимальный заказ',
  article: 'Код товара',
  mandatoryFields: 'Обязательные',
  additionalFields: 'Дополнительные',
  showAdditional: 'Показать дополнительные поля',
  hideAdditional: 'Скрыть дополнительные поля',
  price: 'Цена',
  unit: 'Единица',
  doNotSelect: '— не выбирать',
  preview: 'Предпросмотр (первые 5 строк)',
  totalRows: 'Всего строк',
  replaceMode: 'Заменить прайс полностью (деактивировать товары, отсутствующие в файле)',
  importBtn: 'Импортировать',
  importing: 'Импортирую...',
  importingLabel: 'Импортируем…',
  cancel: 'Отмена',
  showDetails: 'Показать детали',
  failTitle: 'Ошибка загрузки',
  successSummary: 'Импортировано: {imported} / Ошибок: {errors}',
  addProductTitle: 'Добавить товар',
  add: 'Добавить',
  searchPlaceholder: 'Поиск по названию, артикулу, единице...',
  found: 'Найдено',
  of: 'из',
  items: 'товаров',
  emptyList: 'Прайс-лист пуст',
  emptyHint: 'Добавьте товары вручную или загрузите файл',
  codeCol: 'Код',
  nameCol: 'Наименование',
  unitCol: 'Ед.',
  packCol: 'Упаковка',
  minOrderCol: 'Мин. заказ',
  priceCol: 'Цена за ед.',
  availability: 'Наличие',
  actions: 'Действия',
  inStock: 'В наличии',
  outOfStock: 'Нет',
  deleteConfirm: 'Удалить этот товар?',
  bulkDeleteConfirm: 'Удалить N товаров? Действие необратимо.',
  bulkDeleteSelected: 'Удалить выбранные',
  clearSelection: 'Снять выделение',
  supplierPaused: 'Поставщик на паузе. Заказы и каталог отключены.',
  active: 'Активен',
  paused: 'На паузе',
  tip: 'Загрузите полный прайс-лист из файла Excel или CSV для быстрого добавления товаров.',
  tipFormats: 'Форматы: xlsx, csv',
  selectFileBtn: 'Выбрать файл',
  uploadBtn: 'Загрузить',
  progressStatus: 'Прочитано {total} / Импортировано: {imported} / Ошибок: {errors}',
  advancedMappingLabel: 'Расширенные настройки (сопоставление колонок)',
  needMappingHint: 'Нужно уточнить колонки',
  loading: 'Загрузка...',
  requiredFields: 'Укажите обязательные поля: Название товара, Цена, Единица',
  unitPlaceholder: 'кг, шт, л',
  articleOptional: 'Артикул / Код (необязательно)',
  articlePlaceholder: 'Например: 12345 или COKE-033',
  articleHint: 'Внутренний код товара у поставщика. Можно не заполнять.',
  namePlaceholder: 'Например: Кока-кола 0.33',
  pricePlaceholder: 'Например: 70',
  priceHint: 'Цена за 1 единицу',
  unitHint: 'шт / кг / л …',
  packPlaceholder: '1',
  packHint: 'Сколько единиц в упаковке (по умолчанию 1)',
  minOrderPlaceholder: '1',
  minOrderHint: 'Минимум упаковок к заказу (по умолчанию 1)',
};

// Auto-detect column mapping by header names (RU/EN aliases) — same as backend
const COLUMN_ALIASES_REQUIRED = {
  productName: ['name', 'product', 'productname', 'название', 'наименование', 'товар', 'позиция'],
  price: ['price', 'cost', 'цена', 'стоимость', 'цена за единицу', 'цена за ед'],
  unit: ['unit', 'uom', 'ед', 'ед.', 'единица', 'измерение', 'ед. изм', 'единица измерения', 'ед.изм'],
};
const COLUMN_ALIASES_ADDITIONAL = {
  article: ['код', 'артикул', 'sku', 'id товара'],
  packQty: ['упаков', 'в упаковке', 'кол-во в упаковке', 'pack', 'packqty', 'pack_quantity'],
  minOrderQty: ['мин', 'минимальный', 'min order', 'мин. заказ', 'мин заказ', 'minorder', 'minorderqty'],
};
const COLUMN_ALIASES = { ...COLUMN_ALIASES_REQUIRED, ...COLUMN_ALIASES_ADDITIONAL };
function detectColumnMapping(columns) {
  const result = { productName: '', article: '', price: '', unit: '', packQty: '', minOrderQty: '' };
  const lower = (s) => String(s || '').toLowerCase().trim();
  for (const col of columns) {
    const c = lower(col);
    for (const [key, aliases] of Object.entries(COLUMN_ALIASES)) {
      if (aliases.some(a => c.includes(a) || a.includes(c))) {
        result[key] = col;
        break;
      }
    }
  }
  return result;
}
function isMappingValid(mapping) {
  return !!(mapping?.productName && mapping?.price && mapping?.unit);
}
function hasAdditionalMappings(mapping) {
  return !!(mapping?.article || mapping?.packQty || mapping?.minOrderQty);
}

export const SupplierPriceList = () => {
  const { user, fetchUser } = useAuth();
  const isPaused = user?.is_paused ?? false;

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
  const [importing, setImporting] = useState(false);
  const [replaceMode, setReplaceMode] = useState(false);
  const [importErrors, setImportErrors] = useState([]);
  const [showAdditionalMapping, setShowAdditionalMapping] = useState(false);
  const [needMapping, setNeedMapping] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importReportId, setImportReportId] = useState(null);
  const [importErrorsPreview, setImportErrorsPreview] = useState([]);
  const [showErrorsTable, setShowErrorsTable] = useState(false);
  const [uploadErrorDetail, setUploadErrorDetail] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [pausing, setPausing] = useState(false);

  const [newProduct, setNewProduct] = useState({
    productName: '',
    article: '',
    price: '',
    unit: '',
    pack_quantity: 1,
    minQuantity: 1,
    availability: true,
    active: true
  });

  useEffect(() => {
    fetchProducts();
  }, []);

  useEffect(() => {
    if (isPaused && editingProduct) setEditingProduct(null);
  }, [isPaused]);

  useEffect(() => {
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      const filtered = products.filter(p => {
        const name = (p.name ?? p.productName ?? '').toLowerCase();
        const article = (p.article ?? '').toLowerCase();
        const unit = (p.unit ?? '').toLowerCase();
        return name.includes(term) || article.includes(term) || unit.includes(term);
      });
      setFilteredProducts(filtered);
    } else {
      setFilteredProducts(products);
    }
  }, [searchTerm, products]);

  const fetchProducts = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/supplier/price-list`, { headers });
      const items = Array.isArray(response.data) ? response.data : (response.data?.items ?? []);
      setProducts(items);
      setFilteredProducts(items);
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
      const packQty = parseInt(newProduct.pack_quantity, 10) || 1;
      const minQty = parseInt(newProduct.minQuantity, 10) || 1;
      await axios.post(`${API}/price-lists`, {
        productName: newProduct.productName,
        article: (newProduct.article || '').trim(),
        price: parseFloat(newProduct.price),
        unit: newProduct.unit || 'шт',
        pack_quantity: Math.max(1, packQty),
        minQuantity: Math.max(1, minQty),
        availability: newProduct.availability,
        active: newProduct.active
      }, { headers });
      setMessage('Товар успешно добавлен');
      setIsAddDialogOpen(false);
      setNewProduct({
        productName: '',
        article: '',
        price: '',
        unit: '',
        pack_quantity: 1,
        minQuantity: 1,
        availability: true,
        active: true
      });
      fetchProducts();
    } catch (error) {
      setMessage('Ошибка при добавлении товара');
    }
  };

  const handleUpdateProduct = async (productId, payload) => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.put(`${API}/price-lists/${productId}`, payload, { headers });
      setMessage('Товар обновлен');
      setEditingProduct(null);
      const updated = res.data;
      setProducts(prev => prev.map(p => p.id === productId ? { ...p, ...updated, unit_price: updated.unit_price ?? updated.price } : p));
      setFilteredProducts(prev => prev.map(p => p.id === productId ? { ...p, ...updated, unit_price: updated.unit_price ?? updated.price } : p));
    } catch (error) {
      setMessage('Ошибка при обновлении');
    }
  };

  const handleDeleteProduct = async (productId) => {
    if (!window.confirm(T.deleteConfirm)) return;
    
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.delete(`${API}/price-lists/${productId}`, { headers });
      setMessage('Товар удален');
      setSelectedIds(prev => { const s = new Set(prev); s.delete(productId); return s; });
      fetchProducts();
    } catch (error) {
      setMessage('Ошибка при удалении');
    }
  };

  const handlePauseToggle = async () => {
    try {
      setPausing(true);
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.patch(`${API}/supplier/pause`, { is_paused: !isPaused }, { headers });
      if (fetchUser) fetchUser();
    } catch (error) {
      setMessage('Ошибка при переключении паузы');
    } finally {
      setPausing(false);
    }
  };

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const confirmMsg = T.bulkDeleteConfirm.replace('N', String(ids.length));
    if (!window.confirm(confirmMsg)) return;
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.post(`${API}/supplier/items/bulk-delete`, { ids }, { headers });
      const n = res.data?.deletedCount ?? 0;
      setSelectedIds(new Set());
      setProducts(prev => prev.filter(p => !ids.includes(p.id)));
      setFilteredProducts(prev => prev.filter(p => !ids.includes(p.id)));
      toast.success(`Удалено ${n} товаров`);
    } catch (error) {
      setMessage('Ошибка при массовом удалении');
    }
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredProducts.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredProducts.map(p => p.id)));
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });
  };

  const writeEvidence = async (payload) => {
    try {
      await axios.post(`${API}/dev/evidence`, payload, {
        headers: { 'Content-Type': 'application/json' },
        timeout: 5000,
      });
    } catch (e) {
      console.warn('Evidence write failed:', e?.message || e);
    }
  };

  const handleImportSubmit = async () => {
    if (!uploadFile) return;
    const endpoint = `${API}/price-lists/import`;
    setImportErrors([]);
    setImportResult(null);
    setMessage('');
    setUploadErrorDetail(null);
    setImporting(true);

    const requestMeta = {
      filename: uploadFile.name,
      size: uploadFile.size,
      replace: replaceMode,
      mapping_used: needMapping && isMappingValid(columnMapping),
    };

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('replace', replaceMode ? 'true' : 'false');
      if (needMapping && isMappingValid(columnMapping)) {
        const cleaned = { productName: columnMapping.productName, price: columnMapping.price, unit: columnMapping.unit };
        if (columnMapping.article) cleaned.article = columnMapping.article;
        if (columnMapping.packQty) cleaned.packQty = columnMapping.packQty;
        if (columnMapping.minOrderQty) cleaned.minOrderQty = columnMapping.minOrderQty;
        formData.append('column_mapping', JSON.stringify(cleaned));
      }

      const res = await axios.post(endpoint, formData, { headers });
      const total = res.data?.total_rows_read ?? res.data?.read ?? 0;
      const imported = res.data?.importedCount ?? res.data?.imported ?? (res.data?.created ?? 0) + (res.data?.updated ?? 0);
      const skipped = res.data?.skipped ?? res.data?.errors ?? 0;
      setImportResult({ total, imported, errors: skipped, skipped_reasons: res.data?.skipped_reasons ?? res.data?.breakdown });
      setImportReportId(res.data?.report_id ?? null);
      setImportErrorsPreview(Array.isArray(res.data?.errors_preview) ? res.data.errors_preview : []);
      setShowErrorsTable(false);
      const successMsg = T.successSummary.replace('{imported}', imported).replace('{errors}', skipped);
      setMessage(successMsg);
      toast.success(successMsg);
      setNeedMapping(false);
      setFilePreview(null);
      await fetchProducts();

      await writeEvidence({
        timestamp: new Date().toISOString(),
        supplier_email: user?.email ?? null,
        endpoint,
        request: requestMeta,
        response: { status: res.status, body: res.data },
        ui_result: 'success',
        message: successMsg,
      });

      if (skipped === 0) {
        setTimeout(() => {
          setIsUploadDialogOpen(false);
          setUploadFile(null);
          setColumnMapping(null);
          setImportResult(null);
          setImportReportId(null);
          setImportErrorsPreview([]);
        }, 2000);
      }
    } catch (error) {
      const status = error.response?.status;
      const detail = error.response?.data?.detail;
      const body = error.response?.data;
      const errorCode = typeof detail === 'object' ? (detail?.error_code ?? detail?.error) : null;
      const diagnostic = typeof detail === 'object' ? detail?.diagnostic_summary : null;
      let msg;
      if (Array.isArray(detail)) {
        msg = 'Неверные параметры запроса. Убедитесь, что выбран файл (xlsx или csv) и попробуйте снова.';
      } else {
        msg =
          diagnostic ||
          (typeof detail === 'object' ? (detail?.message || detail?.error || 'Ошибка при импорте') : (detail || error?.message || 'Ошибка при импорте'));
      }
      setMessage(msg);
      setUploadErrorDetail({
        status,
        endpoint,
        message: typeof detail === 'object' ? detail?.message || detail?.error : Array.isArray(detail) ? msg : String(detail ?? error?.message ?? ''),
        body,
        diagnostic_summary: diagnostic ?? (typeof detail === 'object' ? detail?.diagnostic_summary : null),
        skipped_reasons: typeof detail === 'object' ? detail?.skipped_reasons : null,
      });
      if (status === 422 && (typeof detail === 'object' || Array.isArray(detail))) {
        const d = typeof detail === 'object' && !Array.isArray(detail) ? detail : {};
        const needMapping = d.error_code === 'missing_required_mapping' || d.error === 'missing_required_mapping' ||
          d.error_code === 'no_rows_imported' || d.error === 'no_rows_imported';
        if (d.columns && needMapping) {
          setFilePreview({ columns: d.columns, total_rows: d.total_rows_read ?? 0 });
          setColumnMapping(detectColumnMapping(d.columns) || {});
          setNeedMapping(true);
          setShowAdditionalMapping(true);
        }
        if (d.skipped_reasons) {
          setImportResult({
            total: d.total_rows_read ?? 0,
            imported: 0,
            errors: d.skipped ?? 0,
            skipped_reasons: d.skipped_reasons,
          });
          setImportReportId(d.report_id ?? null);
          setImportErrorsPreview(Array.isArray(d.errors_preview) ? d.errors_preview : []);
          setShowErrorsTable(false);
        }
      }
      const errs = typeof detail === 'object' ? (detail?.errors || []) : [];
      setImportErrors(Array.isArray(errs) ? errs.slice(0, 10) : []);
      toast.error(T.failTitle);
      console.error('Price list import failed', { status, endpoint, detail, error: error?.message });

      await writeEvidence({
        timestamp: new Date().toISOString(),
        supplier_email: user?.email ?? null,
        endpoint,
        request: requestMeta,
        response: { status: status ?? null, body },
        ui_result: 'fail',
        message: msg,
      });
    } finally {
      setImporting(false);
    }
  };

  const handleImport = () => {
    if (needMapping && !isMappingValid(columnMapping)) {
      setMessage(T.requiredFields);
      setImportErrors([]);
      return;
    }
    handleImportSubmit();
  };

  useEffect(() => {
    if (!showErrorsTable || importErrorsPreview.length > 0 || !importReportId) return;
    const token = localStorage.getItem('token');
    axios
      .get(`${API}/supplier/pricelists/import-report/${importReportId}`, {
        params: { limit: 200, offset: 0 },
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      .then((r) => {
        if (Array.isArray(r.data?.errors)) setImportErrorsPreview(r.data.errors);
      })
      .catch(() => {});
  }, [showErrorsTable, importReportId, importErrorsPreview.length]);

  if (loading) {
    return <div className="text-center py-8">{T.loading}</div>;
  }

  return (
    <div data-testid="supplier-pricelist-page">
      {isPaused && (
        <Alert className="mb-4 border-amber-500 bg-amber-50" variant="default">
          <AlertDescription className="text-amber-800">
            <strong>{T.supplierPaused}</strong>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex justify-between items-center mb-6 flex-wrap gap-2">
        <h2 className="text-2xl font-bold">{T.pageTitle}</h2>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Label htmlFor="pause-toggle" className="text-sm whitespace-nowrap">
              {isPaused ? T.paused : T.active}
            </Label>
            <Switch
              id="pause-toggle"
              checked={isPaused}
              onCheckedChange={handlePauseToggle}
              disabled={pausing}
            />
          </div>
          <Dialog open={isUploadDialogOpen} onOpenChange={(open) => {
            setIsUploadDialogOpen(open);
            if (!open) {
              setNeedMapping(false);
              setFilePreview(null);
              setUploadFile(null);
              setImportResult(null);
              setImportReportId(null);
              setImportErrorsPreview([]);
              setShowErrorsTable(false);
              setUploadErrorDetail(null);
              setColumnMapping(null);
            }
          }}>
            <DialogTrigger asChild>
              <Button variant="outline" data-testid="upload-pricelist-btn" disabled={isPaused}>
                <Upload className="h-4 w-4 mr-2" />
                {T.uploadFile}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>{T.modalTitle}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <form onSubmit={(e) => { e.preventDefault(); handleImport(); }} className="space-y-4">
                  <div>
                    <Label>{T.selectFileBtn}</Label>
                    <Input
                      type="file"
                      accept=".csv,.xlsx,.xls"
                      onChange={(e) => setUploadFile(e.target.files?.[0])}
                    />
                  </div>
                  <p className="text-sm text-muted-foreground">{T.tipFormats}</p>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="replace-mode"
                      checked={replaceMode}
                      onChange={(e) => setReplaceMode(e.target.checked)}
                      className="rounded border-gray-300"
                    />
                    <Label htmlFor="replace-mode" className="cursor-pointer text-sm">{T.replaceMode}</Label>
                  </div>

                  {importing && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {T.importingLabel}
                    </div>
                  )}
                  {uploadErrorDetail && !importing && (
                    <Alert variant="destructive" className="mt-2">
                      <AlertDescription>
                        <p className="font-medium">{T.failTitle}</p>
                        <p className="mt-1">{message || uploadErrorDetail.message}</p>
                        <details className="mt-2">
                          <summary className="cursor-pointer text-sm underline">{T.showDetails}</summary>
                          <pre className="mt-2 p-2 bg-black/5 rounded text-xs overflow-auto max-h-48">
                            {[
                              `HTTP: ${uploadErrorDetail.status ?? '—'}`,
                              `Endpoint: ${uploadErrorDetail.endpoint ?? '—'}`,
                              uploadErrorDetail.diagnostic_summary ? `Диагностика: ${uploadErrorDetail.diagnostic_summary}` : null,
                              uploadErrorDetail.skipped_reasons
                                ? `Причины отбраковки: ${JSON.stringify(uploadErrorDetail.skipped_reasons)}`
                                : null,
                              typeof uploadErrorDetail.body === 'object'
                                ? JSON.stringify(uploadErrorDetail.body, null, 2)
                                : String(uploadErrorDetail.body ?? ''),
                            ]
                              .filter(Boolean)
                              .join('\n')}
                          </pre>
                        </details>
                      </AlertDescription>
                    </Alert>
                  )}
                  {importResult && !importing && !uploadErrorDetail && (
                    <div className="space-y-3">
                      <div className="rounded-md bg-muted p-3 text-sm">
                        <p className="font-medium">
                          {T.progressStatus
                            .replace('{total}', String(importResult.total))
                            .replace('{imported}', String(importResult.imported))
                            .replace('{errors}', String(importResult.errors ?? 0))}
                        </p>
                        {importResult.skipped_reasons && (importResult.imported === 0 || (importResult.errors ?? 0) > 0) && (
                          <p className="mt-1 text-muted-foreground">
                            Пустое название: {importResult.skipped_reasons.empty_name ?? importResult.skipped_reasons?.EMPTY_NAME ?? 0}, не распарсилась цена: {importResult.skipped_reasons.price_parse_failed ?? importResult.skipped_reasons?.PRICE_PARSE ?? 0}, цена ≤ 0: {importResult.skipped_reasons.price_le_zero ?? importResult.skipped_reasons?.PRICE_ZERO ?? 0}, прочее: {importResult.skipped_reasons.other ?? importResult.skipped_reasons?.OTHER ?? 0}.
                          </p>
                        )}
                      </div>
                      {(importResult.errors ?? 0) > 0 && (
                        <>
                          <div>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => setShowErrorsTable((v) => !v)}
                              className="gap-1"
                            >
                              <ChevronDown className={`h-4 w-4 transition-transform ${showErrorsTable ? 'rotate-180' : ''}`} />
                              Показать ошибки ({importResult.errors})
                            </Button>
                            {importReportId && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="ml-2"
                                onClick={async () => {
                                  try {
                                    const token = localStorage.getItem('token');
                                    const r = await fetch(`${API}/supplier/pricelists/import-report/${importReportId}/errors.csv`, {
                                      headers: token ? { Authorization: `Bearer ${token}` } : {},
                                    });
                                    if (!r.ok) throw new Error(r.statusText);
                                    const blob = await r.blob();
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = `import-errors-${importReportId.slice(0, 8)}.csv`;
                                    a.click();
                                    URL.revokeObjectURL(url);
                                    toast.success('CSV сохранён');
                                  } catch (e) {
                                    toast.error('Не удалось скачать CSV');
                                  }
                                }}
                              >
                                <Download className="h-4 w-4 mr-1" />
                                Скачать CSV ошибок
                              </Button>
                            )}
                          </div>
                          {showErrorsTable && (
                            <div className="border rounded-md overflow-auto max-h-60">
                              <table className="w-full text-xs">
                                <thead className="bg-muted sticky top-0">
                                  <tr>
                                    <th className="text-left p-2">№</th>
                                    <th className="text-left p-2">Название</th>
                                    <th className="text-left p-2">Цена</th>
                                    <th className="text-left p-2">Причина</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(importErrorsPreview.length ? importErrorsPreview : []).slice(0, 200).map((e, i) => (
                                    <tr key={i} className="border-t">
                                      <td className="p-2">{e.row_number}</td>
                                      <td className="p-2 max-w-[120px] truncate" title={e.raw_name}>{e.raw_name || '—'}</td>
                                      <td className="p-2">{e.raw_price || '—'}</td>
                                      <td className="p-2">{e.reason_text || e.reason_code}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              {importErrorsPreview.length >= 200 && (
                                <p className="p-2 text-muted-foreground text-xs">Показаны первые 200. Полный список — в CSV.</p>
                              )}
                            </div>
                          )}
                          <Accordion type="single" collapsible className="border rounded-md">
                            <AccordionItem value="howto">
                              <AccordionTrigger className="px-3 py-2 text-sm">Как исправить ошибки</AccordionTrigger>
                              <AccordionContent className="px-3 pb-3 text-sm text-muted-foreground space-y-2">
                                <p><strong>Пустое название</strong> — проверьте колонку «Название/Номенклатура», уберите пустые строки, объединённые ячейки, лишние шапки.</p>
                                <p><strong>Цена не распарсилась</strong> — формат числа 123.45 или 123,45; уберите ₽, пробелы, текст.</p>
                                <p><strong>Цена ≤ 0</strong> — проверьте нули и прочерки.</p>
                                <p><strong>Неверные колонки</strong> — откройте «Расширенные настройки (сопоставление колонок)» и выберите правильные колонки.</p>
                                <p><strong>Лишние строки вверху</strong> — оставьте одну строку заголовков.</p>
                              </AccordionContent>
                            </AccordionItem>
                          </Accordion>
                        </>
                      )}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <Button type="submit" disabled={!uploadFile || importing}>
                      {importing ? T.importing : T.uploadBtn}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setFilePreview(null);
                        setColumnMapping(null);
                        setUploadFile(null);
                        setImportResult(null);
                        setNeedMapping(false);
                      }}
                    >
                      {T.cancel}
                    </Button>
                  </div>
                </form>

                <details className="border rounded-md p-2" open={needMapping}>
                  <summary className="cursor-pointer text-sm text-muted-foreground">{T.advancedMappingLabel}</summary>
                  <div className="pt-3 space-y-3">
                    {needMapping && filePreview?.columns?.length > 0 && (
                      <p className="text-sm font-medium text-amber-700">{T.needMappingHint}</p>
                    )}
                    {filePreview?.columns?.length > 0 && (
                      <>
                        <p className="text-sm text-muted-foreground">{T.mandatoryFields}</p>
                        <div className="grid grid-cols-3 gap-3">
                          <div>
                            <Label>{T.productName}</Label>
                            <select
                              value={columnMapping?.productName ?? ''}
                              onChange={(e) => setColumnMapping(prev => ({ ...prev, productName: e.target.value }))}
                              className="w-full px-3 py-2 border rounded-md"
                            >
                              {filePreview.columns.map(col => (
                                <option key={col} value={col}>{col}</option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <Label>{T.price}</Label>
                            <select
                              value={columnMapping?.price ?? ''}
                              onChange={(e) => setColumnMapping(prev => ({ ...prev, price: e.target.value }))}
                              className="w-full px-3 py-2 border rounded-md"
                            >
                              {filePreview.columns.map(col => (
                                <option key={col} value={col}>{col}</option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <Label>{T.unit}</Label>
                            <select
                              value={columnMapping?.unit ?? ''}
                              onChange={(e) => setColumnMapping(prev => ({ ...prev, unit: e.target.value }))}
                              className="w-full px-3 py-2 border rounded-md"
                            >
                              {filePreview.columns.map(col => (
                                <option key={col} value={col}>{col}</option>
                              ))}
                            </select>
                          </div>
                        </div>
                        {hasAdditionalMappings(columnMapping) && (
                          <div className="grid grid-cols-3 gap-3 pt-2 border-t">
                            <div>
                              <Label>{T.article}</Label>
                              <select
                                value={columnMapping?.article || ''}
                                onChange={(e) => setColumnMapping(prev => ({ ...prev, article: e.target.value || '' }))}
                                className="w-full px-3 py-2 border rounded-md"
                              >
                                <option value="">{T.doNotSelect}</option>
                                {filePreview.columns.map(col => (
                                  <option key={col} value={col}>{col}</option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <Label>{T.packQty}</Label>
                              <select
                                value={columnMapping?.packQty || ''}
                                onChange={(e) => setColumnMapping(prev => ({ ...prev, packQty: e.target.value || '' }))}
                                className="w-full px-3 py-2 border rounded-md"
                              >
                                <option value="">{T.doNotSelect} (1)</option>
                                {filePreview.columns.map(col => (
                                  <option key={col} value={col}>{col}</option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <Label>{T.minOrder}</Label>
                              <select
                                value={columnMapping?.minOrderQty || ''}
                                onChange={(e) => setColumnMapping(prev => ({ ...prev, minOrderQty: e.target.value || '' }))}
                                className="w-full px-3 py-2 border rounded-md"
                              >
                                <option value="">{T.doNotSelect} (1)</option>
                                {filePreview.columns.map(col => (
                                  <option key={col} value={col}>{col}</option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )}
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          onClick={() => handleImport()}
                          disabled={!isMappingValid(columnMapping) || importing}
                        >
                          {importing ? T.importing : T.uploadBtn}
                        </Button>
                      </>
                    )}
                    {(!filePreview?.columns?.length) && !needMapping && (
                      <p className="text-sm text-muted-foreground">Выберите файл и нажмите «Загрузить». Маппинг понадобится только если колонки не определились автоматически.</p>
                    )}
                  </div>
                </details>
              </div>
            </DialogContent>
          </Dialog>

          <Dialog open={isAddDialogOpen} onOpenChange={(open) => {
            setIsAddDialogOpen(open);
            if (open) {
              setNewProduct({ productName: '', article: '', price: '', unit: '', pack_quantity: 1, minQuantity: 1, availability: true, active: true });
            }
          }}>
            <DialogTrigger asChild>
              <Button data-testid="add-product-btn" disabled={isPaused}>
                <Plus className="h-4 w-4 mr-2" />
                {T.addProduct}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{T.addProductTitle}</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleAddProduct} className="space-y-4">
                <div>
                  <Label htmlFor="productName">{T.productName}</Label>
                  <Input
                    id="productName"
                    value={newProduct.productName}
                    onChange={(e) => setNewProduct({...newProduct, productName: e.target.value})}
                    placeholder={T.namePlaceholder}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="article">{T.articleOptional}</Label>
                  <Input
                    id="article"
                    value={newProduct.article}
                    onChange={(e) => setNewProduct({...newProduct, article: e.target.value})}
                    placeholder={T.articlePlaceholder}
                  />
                  <p className="text-xs text-muted-foreground mt-1">{T.articleHint}</p>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="price">{T.price}</Label>
                    <Input
                      id="price"
                      type="number"
                      step="0.01"
                      min={0}
                      value={newProduct.price}
                      onChange={(e) => setNewProduct({...newProduct, price: e.target.value})}
                      placeholder={T.pricePlaceholder}
                      required
                    />
                    <p className="text-xs text-muted-foreground mt-1">{T.priceHint}</p>
                  </div>
                  <div>
                    <Label htmlFor="unit">{T.unit}</Label>
                    <Input
                      id="unit"
                      value={newProduct.unit}
                      onChange={(e) => setNewProduct({...newProduct, unit: e.target.value})}
                      placeholder={T.unitPlaceholder}
                      required
                    />
                    <p className="text-xs text-muted-foreground mt-1">{T.unitHint}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="pack_quantity">{T.packCol}</Label>
                    <Input
                      id="pack_quantity"
                      type="number"
                      min={1}
                      value={newProduct.pack_quantity}
                      onChange={(e) => setNewProduct({...newProduct, pack_quantity: e.target.value})}
                      placeholder={T.packPlaceholder}
                    />
                    <p className="text-xs text-muted-foreground mt-1">{T.packHint}</p>
                  </div>
                  <div>
                    <Label htmlFor="minQuantity">{T.minOrderCol}</Label>
                    <Input
                      id="minQuantity"
                      type="number"
                      min={1}
                      value={newProduct.minQuantity}
                      onChange={(e) => setNewProduct({...newProduct, minQuantity: e.target.value})}
                      placeholder={T.minOrderPlaceholder}
                    />
                    <p className="text-xs text-muted-foreground mt-1">{T.minOrderHint}</p>
                  </div>
                </div>
                <Button type="submit" className="w-full">{T.add}</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {message && (
        <Alert className="mb-4" variant={message.includes('Ошибка') || message.includes('Ни одна') ? 'destructive' : 'default'}>
          <AlertDescription>
            <div>{message}</div>
            {importErrors.length > 0 && (
              <ul className="mt-2 text-sm list-disc list-inside space-y-0.5">
                {importErrors.slice(0, 10).map((e, i) => (
                  <li key={i}>Строка {e.row}: {e.field} — {e.message}</li>
                ))}
                {importErrors.length > 10 && <li className="text-gray-500">… и ещё {importErrors.length - 10}</li>}
              </ul>
            )}
          </AlertDescription>
        </Alert>
      )}

      {products.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-gray-600 mb-4">{T.emptyList}</p>
          <p className="text-sm text-gray-500">{T.emptyHint}</p>
        </Card>
      ) : (
        <>
          <div className="mb-4">
            <div className="relative">
              <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={T.searchPlaceholder}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            {searchTerm && (
              <p className="text-sm text-muted-foreground mt-2">
                {T.found}: {filteredProducts.length} {T.of} {products.length} {T.items}
              </p>
            )}
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-3 mt-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
                <span className="text-sm font-medium">
                  Выбрано: {selectedIds.size} {T.items}
                </span>
                <Button size="sm" variant="destructive" onClick={handleBulkDelete} disabled={isPaused}>
                  <Trash2 className="h-4 w-4 mr-1" />
                  {T.bulkDeleteSelected} ({selectedIds.size})
                </Button>
                <Button size="sm" variant="outline" onClick={() => setSelectedIds(new Set())}>
                  {T.clearSelection}
                </Button>
              </div>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 w-10">
                    <Checkbox
                      checked={filteredProducts.length > 0 && filteredProducts.every(p => selectedIds.has(p.id))}
                      onCheckedChange={toggleSelectAll}
                      disabled={isPaused}
                    />
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.codeCol}</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.nameCol}</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.unitCol}</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.packCol}</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.minOrderCol}</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.priceCol}</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.availability}</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">{T.actions}</th>
                </tr>
              </thead>
            <tbody className="bg-white divide-y">
              {filteredProducts.map((product) => {
                const isEditing = editingProduct?.id === product.id;
                const p = isEditing ? editingProduct : product;
                const unitPrice = p.unit_price ?? p.price ?? 0;
                const packQty = p.pack_quantity ?? 1;
                const minOrder = p.min_order ?? p.minQuantity ?? 1;
                const availability = p.availability ?? true;
                return (
                <tr key={product.id} className={`hover:bg-gray-50 ${isEditing ? 'bg-blue-50/50' : ''}`}>
                  <td className="px-4 py-3">
                    <Checkbox
                      checked={selectedIds.has(product.id)}
                      onCheckedChange={() => toggleSelect(product.id)}
                      disabled={isPaused}
                    />
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <Input value={p.article ?? ''} onChange={(e) => setEditingProduct({...p, article: e.target.value})} className="h-8 text-sm" />
                    ) : (
                      <span className="text-sm text-gray-600">{p.article ?? ''}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <Input value={p.name ?? p.productName ?? ''} onChange={(e) => setEditingProduct({...p, name: e.target.value})} className="h-8 text-sm" />
                    ) : (
                      <span className="font-medium">{p.name ?? p.productName ?? ''}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <Input value={p.unit ?? ''} onChange={(e) => setEditingProduct({...p, unit: e.target.value})} className="h-8 w-16 text-sm" />
                    ) : (
                      <span className="text-sm">{p.unit ?? ''}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <Input type="number" min={1} value={packQty} onChange={(e) => setEditingProduct({...p, pack_quantity: parseInt(e.target.value, 10) || 1})} className="h-8 w-16 text-sm" />
                    ) : (
                      <span className="text-sm">{packQty}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <Input type="number" min={1} value={minOrder} onChange={(e) => setEditingProduct({...p, min_order: parseInt(e.target.value, 10) || 1})} className="h-8 w-16 text-sm" />
                    ) : (
                      <span className="text-sm">{minOrder}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <Input type="number" min={0} step={0.01} value={unitPrice} onChange={(e) => setEditingProduct({...p, unit_price: parseFloat(e.target.value) || 0})} className="h-8 w-24 text-sm" />
                    ) : (
                      <span className="font-medium">{unitPrice} ₽</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <Switch checked={availability} disabled={isPaused} onCheckedChange={(checked) => setEditingProduct({...p, availability: checked})} />
                    ) : (
                      <Badge className={availability ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}>
                        {availability ? T.inStock : T.outOfStock}
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" title="Сохранить" disabled={isPaused} onClick={() => handleUpdateProduct(product.id, {
                          article: p.article ?? '',
                          name: p.name ?? p.productName ?? '',
                          unit: p.unit ?? 'шт',
                          pack_quantity: parseInt(p.pack_quantity ?? 1, 10),
                          min_order: parseInt(p.min_order ?? p.minQuantity ?? 1, 10),
                          unit_price: parseFloat(p.unit_price ?? p.price ?? 0),
                          availability: p.availability ?? true
                        })}>
                          <Check className="h-4 w-4 text-green-600" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Отмена" onClick={() => setEditingProduct(null)}>
                          <X className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" title="Редактировать" disabled={isPaused} onClick={() => setEditingProduct({
                          ...product,
                          article: product.article ?? '',
                          name: product.name ?? product.productName ?? '',
                          unit: product.unit ?? 'шт',
                          pack_quantity: product.pack_quantity ?? 1,
                          min_order: product.min_order ?? product.minQuantity ?? 1,
                          unit_price: product.unit_price ?? product.price ?? 0,
                          availability: product.availability ?? true
                        })}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Удалить" disabled={isPaused} onClick={() => handleDeleteProduct(product.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              );})}
            </tbody>
          </table>
        </div>
        </>
      )}

      <Card className="p-4 mt-6 bg-blue-50 border-blue-200">
        <p className="text-sm text-gray-700">
          <strong>Совет:</strong> {T.tip} {T.tipFormats}
        </p>
      </Card>
    </div>
  );
};