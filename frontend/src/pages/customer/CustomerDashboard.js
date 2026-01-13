import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { CustomerLayout } from './CustomerLayout';
import { CustomerCatalog } from './CustomerCatalog';
import { CustomerProfile } from './CustomerProfile';
import { CustomerTeam } from './CustomerTeam';
import { CustomerDocuments } from './CustomerDocuments';
import { CustomerOrders } from './CustomerOrders';
import { CustomerAnalytics } from './CustomerAnalytics';
import { CustomerRatings } from './CustomerRatings';
import { CustomerMatrix } from './CustomerMatrix';
import { CustomerMyProfile } from './CustomerMyProfile';
import { CustomerFavorites } from './CustomerFavorites';
import { CustomerCart } from './CustomerCart';

export const CustomerDashboard = () => {
  return (
    <CustomerLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/customer/catalog" replace />} />
        <Route path="/catalog" element={<CustomerCatalog />} />
        <Route path="/favorites" element={<CustomerFavorites />} />
        <Route path="/cart" element={<CustomerCart />} />
        <Route path="/profile" element={<CustomerProfile />} />
        <Route path="/my-profile" element={<CustomerMyProfile />} />
        <Route path="/team" element={<CustomerTeam />} />
        <Route path="/documents" element={<CustomerDocuments />} />
        <Route path="/orders" element={<CustomerOrders />} />
        <Route path="/analytics" element={<CustomerAnalytics />} />
        <Route path="/ratings" element={<CustomerRatings />} />
        <Route path="/matrix/:matrixId" element={<CustomerMatrix />} />
        <Route path="/matrix" element={<CustomerMatrix />} />
      </Routes>
    </CustomerLayout>
  );
};