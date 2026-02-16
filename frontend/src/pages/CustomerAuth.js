import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription } from '@/components/ui/alert';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerAuth = () => {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [isLogin, setIsLogin] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [innLoading, setInnLoading] = useState(false);
  
  const [loginData, setLoginData] = useState({
    email: '',
    password: ''
  });
  
  const [registerData, setRegisterData] = useState({
    email: '',
    password: '',
    inn: '',
    companyName: '',
    legalAddress: '',
    ogrn: '',
    actualAddress: '',
    phone: '',
    companyEmail: '',
    contactPersonName: '',
    contactPersonPosition: '',
    contactPersonPhone: '',
    deliveryAddresses: [''],
    dataProcessingConsent: false
  });

  const handleInnLookup = async (inn) => {
    if (inn.length === 10 || inn.length === 12) {
      setInnLoading(true);
      try {
        const response = await axios.get(`${API}/auth/inn/${inn}`);
        if (response.data.companyName) {
          setRegisterData(prev => ({
            ...prev,
            companyName: response.data.companyName,
            legalAddress: response.data.legalAddress,
            ogrn: response.data.ogrn
          }));
        }
      } catch (err) {
        console.error('INN lookup failed:', err);
      } finally {
        setInnLoading(false);
      }
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      const user = await login(loginData.email, loginData.password);
      // Allow customer, chef, and staff (responsible) to access restaurant portal
      if (['customer', 'chef', 'responsible'].includes(user.role)) {
        navigate('/customer');
      } else {
        setError('Этот аккаунт не является рестораном');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Неверный email или пароль');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!registerData.dataProcessingConsent) {
      setError('Необходимо согласие на обработку данных');
      return;
    }
    
    setLoading(true);
    
    try {
      const payload = {
        ...registerData,
        deliveryAddresses: registerData.deliveryAddresses
          .filter((a) => a && String(a).trim())
          .map((addr) => ({ address: String(addr).trim(), phone: '', additionalPhone: null }))
      };
      if (payload.deliveryAddresses.length === 0) {
        payload.deliveryAddresses = [{ address: registerData.actualAddress || 'Не указан', phone: '', additionalPhone: null }];
      }
      await register(payload, 'customer');
      navigate('/customer');
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка регистрации');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-8">
      <Card className="w-full max-w-2xl p-8">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-blue-600 mb-2">BestPrice</h1>
          <p className="text-gray-600">
            {isLogin ? 'Вход для ресторанов' : 'Регистрация ресторана'}
          </p>
        </div>

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {isLogin ? (
          <form onSubmit={handleLogin} className="space-y-4" data-testid="supplier-login-form">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={loginData.email}
                onChange={(e) => setLoginData({ ...loginData, email: e.target.value })}
                required
                data-testid="login-email-input"
              />
            </div>
            <div>
              <Label htmlFor="password">Пароль</Label>
              <Input
                id="password"
                type="password"
                value={loginData.password}
                onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
                required
                data-testid="login-password-input"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading} data-testid="login-submit-btn">
              {loading ? 'Загрузка...' : 'Войти'}
            </Button>
            <div className="text-center">
              <button
                type="button"
                className="text-sm text-blue-600 hover:underline"
                onClick={() => setIsLogin(false)}
                data-testid="switch-to-register-btn"
              >
                Нет аккаунта? Зарегистрироваться
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleRegister} className="space-y-4" data-testid="supplier-register-form">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="email">Email *</Label>
                <Input
                  id="email"
                  type="email"
                  value={registerData.email}
                  onChange={(e) => setRegisterData({ ...registerData, email: e.target.value })}
                  required
                  data-testid="register-email-input"
                />
              </div>
              <div>
                <Label htmlFor="password">Пароль *</Label>
                <Input
                  id="password"
                  type="password"
                  value={registerData.password}
                  onChange={(e) => setRegisterData({ ...registerData, password: e.target.value })}
                  required
                  data-testid="register-password-input"
                />
              </div>
            </div>
            
            <div>
              <Label htmlFor="inn">ИНН *</Label>
              <Input
                id="inn"
                value={registerData.inn}
                onChange={(e) => {
                  setRegisterData({ ...registerData, inn: e.target.value });
                  handleInnLookup(e.target.value);
                }}
                required
                data-testid="register-inn-input"
              />
              {innLoading && <p className="text-sm text-gray-500 mt-1">Загрузка данных...</p>}
            </div>
            
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="companyName">Название компании *</Label>
                <Input
                  id="companyName"
                  value={registerData.companyName}
                  onChange={(e) => setRegisterData({ ...registerData, companyName: e.target.value })}
                  required
                />
              </div>
              <div>
                <Label htmlFor="ogrn">ОГРН *</Label>
                <Input
                  id="ogrn"
                  value={registerData.ogrn}
                  onChange={(e) => setRegisterData({ ...registerData, ogrn: e.target.value })}
                  required
                />
              </div>
            </div>
            
            <div>
              <Label htmlFor="legalAddress">Юридический адрес *</Label>
              <Input
                id="legalAddress"
                value={registerData.legalAddress}
                onChange={(e) => setRegisterData({ ...registerData, legalAddress: e.target.value })}
                required
              />
            </div>
            
            <div>
              <Label htmlFor="actualAddress">Фактический адрес *</Label>
              <Input
                id="actualAddress"
                value={registerData.actualAddress}
                onChange={(e) => setRegisterData({ ...registerData, actualAddress: e.target.value })}
                required
              />
            </div>
            
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="phone">Телефон *</Label>
                <Input
                  id="phone"
                  value={registerData.phone}
                  onChange={(e) => setRegisterData({ ...registerData, phone: e.target.value })}
                  required
                />
              </div>
              <div>
                <Label htmlFor="companyEmail">Email компании *</Label>
                <Input
                  id="companyEmail"
                  type="email"
                  value={registerData.companyEmail}
                  onChange={(e) => setRegisterData({ ...registerData, companyEmail: e.target.value })}
                  required
                />
              </div>
            </div>
            
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="contactPersonName">Контактное лицо *</Label>
                <Input
                  id="contactPersonName"
                  value={registerData.contactPersonName}
                  onChange={(e) => setRegisterData({ ...registerData, contactPersonName: e.target.value })}
                  required
                />
              </div>
              <div>
                <Label htmlFor="contactPersonPosition">Должность *</Label>
                <Input
                  id="contactPersonPosition"
                  value={registerData.contactPersonPosition}
                  onChange={(e) => setRegisterData({ ...registerData, contactPersonPosition: e.target.value })}
                  required
                />
              </div>
              <div>
                <Label htmlFor="contactPersonPhone">Телефон контакта *</Label>
                <Input
                  id="contactPersonPhone"
                  value={registerData.contactPersonPhone}
                  onChange={(e) => setRegisterData({ ...registerData, contactPersonPhone: e.target.value })}
                  required
                />
              </div>
            </div>
            
            <div>
              <Label>Адреса доставки *</Label>
              {registerData.deliveryAddresses.map((address, index) => (
                <div key={index} className="flex gap-2 mt-2">
                  <Input
                    value={address}
                    onChange={(e) => {
                      const newAddresses = [...registerData.deliveryAddresses];
                      newAddresses[index] = e.target.value;
                      setRegisterData({ ...registerData, deliveryAddresses: newAddresses });
                    }}
                    placeholder="Адрес доставки"
                    required
                  />
                  {index > 0 && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        const newAddresses = registerData.deliveryAddresses.filter((_, i) => i !== index);
                        setRegisterData({ ...registerData, deliveryAddresses: newAddresses });
                      }}
                    >
                      Удалить
                    </Button>
                  )}
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                className="mt-2"
                onClick={() => setRegisterData({ ...registerData, deliveryAddresses: [...registerData.deliveryAddresses, ''] })}
              >
                + Добавить адрес
              </Button>
            </div>
            
            <div className="flex items-center space-x-2">
              <Checkbox
                id="consent"
                checked={registerData.dataProcessingConsent}
                onCheckedChange={(checked) => setRegisterData({ ...registerData, dataProcessingConsent: checked })}
                data-testid="consent-checkbox"
              />
              <Label htmlFor="consent" className="text-sm">
                Я согласен на{' '}
                <a href="/personal-data-consent" target="_blank" className="text-blue-600 hover:underline">
                  обработку персональных данных
                </a>
              </Label>
            </div>
            
            <Button type="submit" className="w-full" disabled={loading} data-testid="register-submit-btn">
              {loading ? 'Загрузка...' : 'Зарегистрироваться'}
            </Button>
            <div className="text-center">
              <button
                type="button"
                className="text-sm text-blue-600 hover:underline"
                onClick={() => setIsLogin(true)}
                data-testid="switch-to-login-btn"
              >
                Уже есть аккаунт? Войти
              </button>
            </div>
          </form>
        )}
        
        <div className="mt-6 text-center">
          <Button variant="ghost" onClick={() => navigate('/auth')} data-testid="back-to-role-select-btn">
            Выбрать другую роль
          </Button>
        </div>
      </Card>
    </div>
  );
};