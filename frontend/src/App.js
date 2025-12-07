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
