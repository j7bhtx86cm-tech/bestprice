import React from 'react';
import { Link } from 'react-router-dom';

/** Placeholder: supplier password reset page. */
export const SupplierResetPassword = () => (
  <div style={{ padding: '2rem', textAlign: 'center' }}>
    <h1>Сброс пароля поставщика</h1>
    <p>
      <Link to="/supplier/auth">Вернуться к входу</Link>
    </p>
  </div>
);
