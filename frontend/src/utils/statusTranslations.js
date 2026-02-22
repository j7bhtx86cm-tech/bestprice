/**
 * Переводы статусов для UI. Backend enum не менять — только отображаемые подписи.
 * Order: контекст "customer" (ресторан) / "supplier" (поставщик).
 */

const ORDER_LABELS_CUSTOMER = {
  DRAFT: 'Черновик',
  SENT_TO_SUPPLIER: 'Отправлен поставщику',
  PARTIALLY_CONFIRMED: 'Частично подтверждён',
  CONFIRMED: 'Подтверждён',
  REJECTED: 'Отклонён',
  CANCELLED: 'Отменён',
};

const ORDER_LABELS_SUPPLIER = {
  DRAFT: '—',
  SENT_TO_SUPPLIER: 'Новый заказ',
  PARTIALLY_CONFIRMED: 'Частично подтверждён',
  CONFIRMED: 'Подтверждён',
  REJECTED: 'Отклонён',
  CANCELLED: 'Отменён',
};

const REQUEST_LABELS = {
  PENDING: 'Ожидает ответа',
  CONFIRMED: 'Подтверждён',
  PARTIALLY_CONFIRMED: 'Частично подтверждён',
  REJECTED: 'Отклонён',
};

const ITEM_LABELS = {
  PENDING: 'Ожидает ответа',
  CONFIRMED: 'Подтверждено',
  REJECTED: 'Отклонено',
  UPDATED: 'Изменено',
};

/** Цвета badge: PENDING — жёлтый, CONFIRMED — зелёный, PARTIALLY_CONFIRMED — синий, REJECTED — красный, CANCELLED — серый */
const STATUS_BADGE_CLASS = {
  PENDING: 'bg-amber-100 text-amber-800',
  CONFIRMED: 'bg-green-100 text-green-800',
  PARTIALLY_CONFIRMED: 'bg-blue-100 text-blue-800',
  REJECTED: 'bg-red-100 text-red-800',
  CANCELLED: 'bg-gray-100 text-gray-800',
  SENT_TO_SUPPLIER: 'bg-blue-100 text-blue-800',
  DRAFT: 'bg-gray-100 text-gray-800',
  UPDATED: 'bg-blue-100 text-blue-800',
};

/**
 * @param {string} status - order.status (backend)
 * @param {'customer'|'supplier'} context
 * @returns {string}
 */
export function translateOrderStatus(status, context = 'customer') {
  if (!status) return '—';
  const map = context === 'supplier' ? ORDER_LABELS_SUPPLIER : ORDER_LABELS_CUSTOMER;
  return map[status] ?? status;
}

/**
 * @param {string} status - request.status (backend)
 * @returns {string}
 */
export function translateRequestStatus(status) {
  if (!status) return '—';
  return REQUEST_LABELS[status] ?? status;
}

/**
 * @param {string} status - item.status (backend)
 * @returns {string}
 */
export function translateItemStatus(status) {
  if (!status) return '—';
  return ITEM_LABELS[status] ?? status;
}

/**
 * CSS class для Badge по order/request/item status (PENDING→жёлтый, CONFIRMED→зелёный и т.д.)
 * @param {string} status
 * @returns {string}
 */
export function getStatusBadgeClass(status) {
  if (!status) return 'bg-gray-100 text-gray-800';
  return STATUS_BADGE_CLASS[status] ?? 'bg-gray-100 text-gray-800';
}
