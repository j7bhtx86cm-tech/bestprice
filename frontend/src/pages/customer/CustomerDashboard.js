import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { CustomerLayout } from './CustomerLayout';
import { CustomerCatalog } from './CustomerCatalog';
import { CustomerProfile } from './CustomerProfile';
import { CustomerTeam } from './CustomerTeam';
import { CustomerDocuments } from './CustomerDocuments';
import { CustomerOrders } from './CustomerOrders';
import { CustomerAnalytics } from './CustomerAnalytics';
import { CustomerRatings } from './CustomerRatings';

export const CustomerDashboard = () => {
  return (
    <CustomerLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/customer/catalog" replace />} />
        <Route path="/catalog" element={<CustomerCatalog />} />
        <Route path="/profile" element={<CustomerProfile />} />
        <Route path="/team" element={<CustomerTeam />} />
        <Route path="/documents" element={<CustomerDocuments />} />
        <Route path="/orders" element={<CustomerOrders />} />
        <Route path="/analytics" element={<CustomerAnalytics />} />
        <Route path="/ratings" element={<CustomerRatings />} />
      </Routes>
    </CustomerLayout>
  );
};