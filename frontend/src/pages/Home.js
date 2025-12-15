import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ShoppingCart, TrendingUp, Clock, CheckCircle } from 'lucide-react';

export const Home = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-blue-600">BestPrice</h1>
          <Button onClick={() => navigate('/auth')} data-testid="header-login-btn">
            Войти
          </Button>
        </div>
      </header>

      {/* Hero Section */}
      <section className="bg-gradient-to-br from-blue-600 via-blue-700 to-green-600 text-white py-24" data-testid="hero-section">
        <div className="container mx-auto px-4 text-center">
          <div className="inline-block mb-6 animate-pulse">
            <div className="bg-white/20 backdrop-blur-sm text-white px-6 py-2 rounded-full text-sm font-medium shadow-lg">
              🎯 Оптимизация закупок для ресторанов
            </div>
          </div>
          <h2 className="text-5xl md:text-6xl font-bold mb-6 drop-shadow-lg">
            Платформа для HoReCa
          </h2>
          <p className="text-xl md:text-2xl mb-10 max-w-2xl mx-auto leading-relaxed opacity-95">
            Связываем поставщиков и рестораны для эффективных закупок продуктов
          </p>
          <div className="flex gap-4 justify-center flex-wrap">
            <Button
              size="lg"
              variant="secondary"
              onClick={() => navigate('/supplier/auth')}
              data-testid="hero-supplier-btn"
              className="bg-white text-blue-700 hover:bg-gray-100 shadow-xl px-8 py-6 text-lg font-semibold"
            >
              Я поставщик →
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={() => navigate('/customer/auth')}
              data-testid="hero-customer-btn"
              className="text-white border-2 border-white hover:bg-white/10 backdrop-blur-sm shadow-xl px-8 py-6 text-lg font-semibold"
            >
              Я ресторан →
            </Button>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 bg-gradient-to-b from-gray-50 to-white" data-testid="how-it-works-section">
        <div className="container mx-auto px-4">
          <h3 className="text-4xl font-bold text-center mb-4 bg-gradient-to-r from-blue-600 to-green-600 bg-clip-text text-transparent">
            Как это работает
          </h3>
          <p className="text-center text-gray-600 mb-12 text-lg">Простой процесс в 3 шага</p>
          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            <Card className="p-8 text-center hover:shadow-xl transition-all duration-300 border-2 hover:border-blue-200">
              <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg">
                <ShoppingCart className="w-10 h-10 text-white" />
              </div>
              <h4 className="text-2xl font-semibold mb-3">Регистрация</h4>
              <p className="text-gray-600 leading-relaxed">
                Зарегистрируйтесь как поставщик или ресторан
              </p>
            </Card>
            <Card className="p-8 text-center hover:shadow-xl transition-all duration-300 border-2 hover:border-green-200">
              <div className="w-20 h-20 bg-gradient-to-br from-green-500 to-green-600 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg">
                <TrendingUp className="w-10 h-10 text-white" />
              </div>
              <h4 className="text-2xl font-semibold mb-3">Выбор продуктов</h4>
              <p className="text-gray-600 leading-relaxed">
                Просматривайте прайс-листы и сравнивайте цены
              </p>
            </Card>
            <Card className="p-8 text-center hover:shadow-xl transition-all duration-300 border-2 hover:border-purple-200">
              <div className="w-20 h-20 bg-gradient-to-br from-purple-500 to-purple-600 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg">
                <CheckCircle className="w-10 h-10 text-white" />
              </div>
              <h4 className="text-2xl font-semibold mb-3">Оформление заказа</h4>
              <p className="text-gray-600 leading-relaxed">
                Оформляйте заказы и отслеживайте доставку
              </p>
            </Card>
          </div>
        </div>
      </section>

      {/* For Restaurants */}
      <section className="py-16" data-testid="for-restaurants-section">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto">
            <h3 className="text-3xl font-bold text-center mb-8">Для ресторанов</h3>
            <div className="grid md:grid-cols-2 gap-6">
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Экономия времени</h4>
                <p className="text-gray-600">
                  Оформляйте заказы у нескольких поставщиков в одном месте
                </p>
              </Card>
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Лучшие цены</h4>
                <p className="text-gray-600">
                  Сравнивайте цены и находите наилучшие предложения
                </p>
              </Card>
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Прозрачность</h4>
                <p className="text-gray-600">
                  Полная история заказов и аналитика
                </p>
              </Card>
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Надежность</h4>
                <p className="text-gray-600">
                  Работайте только с проверенными поставщиками
                </p>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* For Suppliers */}
      <section className="py-16 bg-gray-50" data-testid="for-suppliers-section">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto">
            <h3 className="text-3xl font-bold text-center mb-8">Для поставщиков</h3>
            <div className="grid md:grid-cols-2 gap-6">
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Новые клиенты</h4>
                <p className="text-gray-600">
                  Получайте доступ к сети ресторанов и кафе
                </p>
              </Card>
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Автоматизация</h4>
                <p className="text-gray-600">
                  Упростите процесс приема и обработки заказов
                </p>
              </Card>
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Управление прайсами</h4>
                <p className="text-gray-600">
                  Легко обновляйте цены и ассортимент
                </p>
              </Card>
              <Card className="p-6">
                <h4 className="text-xl font-semibold mb-2">Аналитика</h4>
                <p className="text-gray-600">
                  Отслеживайте продажи и популярные товары
                </p>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 bg-blue-600 text-white" data-testid="cta-section">
        <div className="container mx-auto px-4 text-center">
          <h3 className="text-3xl font-bold mb-6">
            Готовы начать?
          </h3>
          <p className="text-xl mb-8">
            Присоединяйтесь к BestPrice уже сегодня
          </p>
          <Button
            size="lg"
            variant="secondary"
            onClick={() => navigate('/auth')}
            data-testid="cta-register-btn"
          >
            Зарегистрироваться
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-white py-8">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-3 gap-8">
            <div>
              <h4 className="text-xl font-bold mb-4">BestPrice</h4>
              <p className="text-gray-400">
                Платформа для эффективных закупок в HoReCa
              </p>
            </div>
            <div>
              <h5 className="font-semibold mb-4">Документы</h5>
              <ul className="space-y-2 text-gray-400">
                <li>
                  <a href="/privacy-policy" className="hover:text-white">
                    Политика конфиденциальности
                  </a>
                </li>
                <li>
                  <a href="/personal-data-consent" className="hover:text-white">
                    Согласие на обработку данных
                  </a>
                </li>
                <li>
                  <a href="/supplier-agreement" className="hover:text-white">
                    Договор для поставщиков
                  </a>
                </li>
                <li>
                  <a href="/customer-agreement" className="hover:text-white">
                    Договор для ресторанов
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h5 className="font-semibold mb-4">Контакты</h5>
              <p className="text-gray-400">
                Email: info@bestprice.ru
                <br />
                Тел: +7 (495) 123-45-67
              </p>
            </div>
          </div>
          <div className="border-t border-gray-800 mt-8 pt-8 text-center text-gray-400">
            <p>&copy; 2025 BestPrice. Все права защищены.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};