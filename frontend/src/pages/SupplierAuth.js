import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { PasswordInput } from '@/components/PasswordInput';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8001';
const API = `${BACKEND_URL}/api`;

export const SupplierAuth = () => {
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
  
  const [recoveryModal, setRecoveryModal] = useState(false);
  const [recoveryMode, setRecoveryMode] = useState(null); // null | 'email' | 'phone'
  const [emailRecovery, setEmailRecovery] = useState({ email: '', loading: false, success: false });
  const [phoneRecovery, setPhoneRecovery] = useState({
    step: 1,
    phone: '',
    otp: '',
    newPassword: '',
    confirmPassword: '',
    loading: false,
    success: false,
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
      if (user.role === 'supplier') {
        navigate('/supplier');
      } else {
        setError('Этот аккаунт не является поставщиком');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Неверный email или пароль');
    } finally {
      setLoading(false);
    }
  };

  const handleForgotEmail = async (e) => {
    e.preventDefault();
    setEmailRecovery((p) => ({ ...p, loading: true, success: false }));
    setError('');
    try {
      await axios.post(`${API}/auth/forgot-password`, { email: emailRecovery.email, role: 'supplier' });
      setEmailRecovery((p) => ({ ...p, loading: false, success: true }));
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка запроса');
      setEmailRecovery((p) => ({ ...p, loading: false }));
    }
  };

  const handlePhoneRequestOtp = async (e) => {
    e.preventDefault();
    setPhoneRecovery((p) => ({ ...p, loading: true }));
    setError('');
    try {
      await axios.post(`${API}/auth/phone/request-otp`, { phone: phoneRecovery.phone, role: 'supplier' });
      setPhoneRecovery((p) => ({ ...p, step: 2, loading: false }));
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка запроса');
      setPhoneRecovery((p) => ({ ...p, loading: false }));
    }
  };

  const handlePhoneReset = async (e) => {
    e.preventDefault();
    if (phoneRecovery.newPassword !== phoneRecovery.confirmPassword) {
      setError('Пароли не совпадают');
      return;
    }
    if (phoneRecovery.newPassword.length < 6) {
      setError('Пароль должен быть не менее 6 символов');
      return;
    }
    setPhoneRecovery((p) => ({ ...p, loading: true }));
    setError('');
    try {
      await axios.post(`${API}/auth/phone/reset-password`, {
        phone: phoneRecovery.phone,
        role: 'supplier',
        otp: phoneRecovery.otp,
        new_password: phoneRecovery.newPassword,
      });
      setPhoneRecovery((p) => ({ ...p, loading: false, success: true }));
      setTimeout(() => {
        setRecoveryModal(false);
        setRecoveryMode(null);
        setEmailRecovery({ email: '', loading: false, success: false });
        setPhoneRecovery({ step: 1, phone: '', otp: '', newPassword: '', confirmPassword: '', loading: false, success: false });
      }, 2000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка сброса пароля');
      setPhoneRecovery((p) => ({ ...p, loading: false }));
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
      await register(registerData, 'supplier');
      navigate('/supplier');
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
            {isLogin ? 'Вход для поставщиков' : 'Регистрация поставщика'}
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
              <PasswordInput
                id="password"
                value={loginData.password}
                onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
                required
                data-testid="login-password-input"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading} data-testid="login-submit-btn">
              {loading ? 'Загрузка...' : 'Войти'}
            </Button>
            <div className="auth-links text-center space-y-1">
              <button
                type="button"
                className="text-sm text-blue-600 hover:underline block mx-auto"
                onClick={() => { setError(''); setRecoveryModal(true); setRecoveryMode(null); }}
                data-testid="forgot-password-btn"
              >
                Забыли пароль?
              </button>
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
                <PasswordInput
                  id="password"
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

      <Dialog open={recoveryModal} onOpenChange={(open) => {
        if (!open) {
          setRecoveryModal(false);
          setRecoveryMode(null);
          setEmailRecovery({ email: '', loading: false, success: false });
          setPhoneRecovery({ step: 1, phone: '', otp: '', newPassword: '', confirmPassword: '', loading: false, success: false });
          setError('');
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Восстановление пароля</DialogTitle>
          </DialogHeader>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {recoveryMode === null && (
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Выберите способ восстановления:</p>
              <Button className="w-full" variant="outline" onClick={() => setRecoveryMode('email')}>
                По Email
              </Button>
              <Button className="w-full" variant="outline" onClick={() => setRecoveryMode('phone')}>
                По телефону
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => setRecoveryModal(false)}>
                Закрыть
              </Button>
            </div>
          )}
          {recoveryMode === 'email' && (
            <div className="space-y-4">
              <button type="button" className="text-sm text-blue-600 hover:underline" onClick={() => setRecoveryMode(null)}>
                ← Назад к выбору
              </button>
              {emailRecovery.success ? (
                <p className="text-sm text-gray-600">Если email существует — мы отправили ссылку для сброса пароля.</p>
              ) : (
                <form onSubmit={handleForgotEmail}>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="recovery-email">Email</Label>
                      <Input id="recovery-email" type="email" value={emailRecovery.email} onChange={(e) => setEmailRecovery((p) => ({ ...p, email: e.target.value }))} required placeholder="supplier1@example.com" />
                    </div>
                    <Button type="submit" className="w-full" disabled={emailRecovery.loading}>
                      {emailRecovery.loading ? 'Отправка...' : 'Отправить ссылку'}
                    </Button>
                  </div>
                </form>
              )}
            </div>
          )}
          {recoveryMode === 'phone' && (
            <div className="space-y-4">
              <button type="button" className="text-sm text-blue-600 hover:underline" onClick={() => setRecoveryMode(null)}>
                ← Назад к выбору
              </button>
              {phoneRecovery.success ? (
                <p className="text-sm text-green-600">Пароль изменён. Войдите с новым паролем.</p>
              ) : phoneRecovery.step === 1 ? (
                <form onSubmit={handlePhoneRequestOtp}>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="recovery-phone">Телефон</Label>
                      <Input id="recovery-phone" type="tel" value={phoneRecovery.phone} onChange={(e) => setPhoneRecovery((p) => ({ ...p, phone: e.target.value }))} required placeholder="+7 921 364 34 75" />
                    </div>
                    <Button type="submit" className="w-full" disabled={phoneRecovery.loading}>
                      {phoneRecovery.loading ? 'Отправка...' : 'Получить код'}
                    </Button>
                  </div>
                </form>
              ) : (
                <form onSubmit={handlePhoneReset}>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="recovery-otp">Код из SMS</Label>
                      <Input id="recovery-otp" type="text" inputMode="numeric" maxLength={6} value={phoneRecovery.otp} onChange={(e) => setPhoneRecovery((p) => ({ ...p, otp: e.target.value.replace(/\D/g, '') }))} required placeholder="123456" />
                    </div>
                    <div>
                      <Label htmlFor="recovery-new-pwd">Новый пароль</Label>
                      <PasswordInput id="recovery-new-pwd" value={phoneRecovery.newPassword} onChange={(e) => setPhoneRecovery((p) => ({ ...p, newPassword: e.target.value }))} required minLength={6} />
                    </div>
                    <div>
                      <Label htmlFor="recovery-confirm-pwd">Подтверждение пароля</Label>
                      <PasswordInput id="recovery-confirm-pwd" value={phoneRecovery.confirmPassword} onChange={(e) => setPhoneRecovery((p) => ({ ...p, confirmPassword: e.target.value }))} required minLength={6} />
                    </div>
                    <Button type="submit" className="w-full" disabled={phoneRecovery.loading}>
                      {phoneRecovery.loading ? 'Сохранение...' : 'Установить пароль'}
                    </Button>
                    <button type="button" className="text-sm text-blue-600 hover:underline block" onClick={() => setPhoneRecovery((p) => ({ ...p, step: 1 }))}>
                      Изменить номер
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};