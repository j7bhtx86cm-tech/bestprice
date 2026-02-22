/**
 * Форматирование для UI: короткий ID заказа, дата/время RU.
 */

/**
 * Короткий ID для отображения: первые 6 символов + "…"
 * @param {string} id
 * @returns {string}
 */
export function shortId(id) {
  if (!id || typeof id !== 'string') return '—';
  return id.slice(0, 6) + '…';
}

/**
 * Дата/время в формате RU: DD.MM.YYYY HH:mm
 * @param {string} isoString - ISO дата или строка даты
 * @returns {string}
 */
export function formatRuDate(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return '—';
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const year = d.getFullYear();
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  return `${day}.${month}.${year} ${hours}:${minutes}`;
}
