import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { CustomerLayout } from './CustomerLayout';
import { CustomerProfile } from './CustomerProfile';

export const CustomerDashboard = () => {
  return (
    <CustomerLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/customer/profile" replace />} />
        <Route path="/profile" element={<CustomerProfile />} />
      </Routes>
    </CustomerLayout>
  );
};