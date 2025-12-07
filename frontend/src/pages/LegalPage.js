import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';

const legalContent = {
  'privacy-policy': {
    title: 'Политика конфиденциальности',
    content: `
      <h2>1. Общие положения</h2>
      <p>Настоящая Политика конфиденциальности определяет порядок обработки и защиты персональных данных пользователей.</p>
      
      <h2>2. Собираемые данные</h2>
      <p>Мы собираем следующую информацию:</p>
      <ul>
        <li>Имя, email, телефон</li>
        <li>Реквизиты компании</li>
        <li>Информацию о заказах</li>
      </ul>
      
      <h2>3. Цели обработки</h2>
      <p>Данные используются для предоставления услуг платформы.</p>
      
      <h2>4. Защита данных</h2>
      <p>Мы принимаем все необходимые меры для защиты ваших данных.</p>
    `
  },
  'personal-data-consent': {
    title: 'Согласие на обработку персональных данных',
    content: `
      <h2>1. Согласие</h2>
      <p>Я даю свое согласие на обработку моих персональных данных.</p>
      
      <h2>2. Объем обрабатываемых данных</h2>
      <p>Обработке подлежат все данные, указанные при регистрации.</p>
      
      <h2>3. Срок действия</h2>
      <p>Согласие действует до его отзыва.</p>
    `
  },
  'supplier-agreement': {
    title: 'Договор для поставщиков',
    content: `
      <h2>1. Предмет договора</h2>
      <p>Поставщик обязуется поставлять продукцию через платформу BestPrice.</p>
      
      <h2>2. Обязанности поставщика</h2>
      <ul>
        <li>Поддерживать актуальные прайс-листы</li>
        <li>Выполнять заказы в срок</li>
        <li>Обеспечивать качество продукции</li>
      </ul>
      
      <h2>3. Комиссия платформы</h2>
      <p>Комиссия платформы составляет 5% от суммы заказа.</p>
    `
  },
  'customer-agreement': {
    title: 'Договор для ресторанов',
    content: `
      <h2>1. Предмет договора</h2>
      <p>Клиент получает доступ к платформе для закупки продукции.</p>
      
      <h2>2. Обязанности клиента</h2>
      <ul>
        <li>Своевременно оплачивать заказы</li>
        <li>Предоставлять актуальные данные</li>
        <li>Принимать доставку в указанное время</li>
      </ul>
      
      <h2>3. Условия использования</h2>
      <p>Платформа бесплатна для ресторанов.</p>
    `
  }
};

export const LegalPage = () => {
  const navigate = useNavigate();
  const { page } = useParams();
  const content = legalContent[page];

  if (!content) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-4xl font-bold mb-4">Страница не найдена</h1>
          <Button onClick={() => navigate('/')}>Вернуться на главную</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4">
          <Button variant="ghost" onClick={() => navigate('/')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Назад
          </Button>
        </div>
      </header>
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto bg-white rounded-lg shadow-sm p-8">
          <h1 className="text-3xl font-bold mb-8">{content.title}</h1>
          <div
            className="prose max-w-none"
            dangerouslySetInnerHTML={{ __html: content.content }}
            style={{
              fontSize: '1rem',
              lineHeight: '1.75',
            }}
          />
        </div>
      </div>
    </div>
  );
};