import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { CookieBanner } from '@/components/CookieBanner';
import { Home } from '@/pages/Home';
import { LegalPage } from '@/pages/LegalPage';
import { AuthPage } from '@/pages/AuthPage';
import { SupplierAuth } from '@/pages/SupplierAuth';
import { CustomerAuth } from '@/pages/CustomerAuth';
import { SupplierDashboard } from '@/pages/supplier/SupplierDashboard';
import { CustomerDashboard } from '@/pages/customer/CustomerDashboard';
import { MobileLogin } from '@/pages/mobile/MobileLogin';
import { MobileHome } from '@/pages/mobile/MobileHome';
import { MobileCreateOrder } from '@/pages/mobile/MobileCreateOrder';
import { MobileOrderPreview } from '@/pages/mobile/MobileOrderPreview';
import { MobileOrderSuccess } from '@/pages/mobile/MobileOrderSuccess';
import { MobileOrders } from '@/pages/mobile/MobileOrders';
import { MobileOrderDetails } from '@/pages/mobile/MobileOrderDetails';
import '@/App.css';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="App">
          <Routes>
            {/* Public Routes */}
            <Route path="/" element={<Home />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route path="/supplier/auth" element={<SupplierAuth />} />
            <Route path="/customer/auth" element={<CustomerAuth />} />
            
            {/* Mobile App Routes */}
            <Route path="/app/login" element={<MobileLogin />} />
            <Route path="/app/home" element={<ProtectedRoute role="responsible"><MobileHome /></ProtectedRoute>} />
            <Route path="/app/order/new" element={<ProtectedRoute role="responsible"><MobileCreateOrder /></ProtectedRoute>} />
            <Route path="/app/order/preview" element={<ProtectedRoute role="responsible"><MobileOrderPreview /></ProtectedRoute>} />
            <Route path="/app/order/success" element={<ProtectedRoute role="responsible"><MobileOrderSuccess /></ProtectedRoute>} />
            <Route path="/app/orders" element={<ProtectedRoute role="responsible"><MobileOrders /></ProtectedRoute>} />
            <Route path="/app/orders/:orderId" element={<ProtectedRoute role="responsible"><MobileOrderDetails /></ProtectedRoute>} />
            
            <Route path="/:page" element={<LegalPage />} />

            {/* Protected Routes */}
            <Route
              path="/supplier/*"
              element={
                <ProtectedRoute role="supplier">
                  <SupplierDashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/customer/*"
              element={
                <ProtectedRoute role="customer">
                  <CustomerDashboard />
                </ProtectedRoute>
              }
            />
          </Routes>
          <CookieBanner />
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
