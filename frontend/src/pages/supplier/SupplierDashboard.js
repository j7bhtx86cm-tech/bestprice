import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { SupplierLayout } from './SupplierLayout';
import { SupplierProfile } from './SupplierProfile';
import { SupplierSettings } from './SupplierSettings';
import { SupplierPriceList } from './SupplierPriceList';
import { SupplierOrders } from './SupplierOrders';
import { SupplierRating } from './SupplierRating';
import { SupplierDocuments } from './SupplierDocuments';

export const SupplierDashboard = () => {
  return (
    <SupplierLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/supplier/profile" replace />} />
        <Route path="/profile" element={<SupplierProfile />} />
        <Route path="/settings" element={<SupplierSettings />} />
        <Route path="/price-list" element={<SupplierPriceList />} />
        <Route path="/orders" element={<SupplierOrders />} />
        <Route path="/rating" element={<SupplierRating />} />
        <Route path="/documents" element={<SupplierDocuments />} />
      </Routes>
    </SupplierLayout>
  );
};