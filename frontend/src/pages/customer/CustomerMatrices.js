import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Plus, Trash2, Grid3x3 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerMatrices = () => {
  const [matrices, setMatrices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newMatrixName, setNewMatrixName] = useState('');
  const [companyId, setCompanyId] = useState('');

  useEffect(() => {
    fetchMatrices();
    fetchCompanyInfo();
  }, []);

  const fetchCompanyInfo = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/auth/me`, { headers });
      setCompanyId(response.data.companyId);
    } catch (error) {
      console.error('Failed to fetch company info:', error);
    }
  };

  const fetchMatrices = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/matrices`, { headers });
      setMatrices(response.data);
    } catch (error) {
      console.error('Failed to fetch matrices:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateMatrix = async () => {
    if (!newMatrixName.trim()) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.post(
        `${API}/matrices`,
        {
          name: newMatrixName,
          restaurantCompanyId: companyId
        },
        { headers }
      );
      setShowCreateModal(false);
      setNewMatrixName('');
      fetchMatrices();
    } catch (error) {
      console.error('Failed to create matrix:', error);
      alert('Ошибка создания матрицы');
    }
  };

  const handleDeleteMatrix = async (matrixId) => {
    if (!confirm('Вы уверены, что хотите удалить эту матрицу?')) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.delete(`${API}/matrices/${matrixId}`, { headers });
      fetchMatrices();
    } catch (error) {
      console.error('Failed to delete matrix:', error);
      alert('Ошибка удаления матрицы');
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Управление матрицами</h2>
          <p className="text-base text-muted-foreground">Создавайте и управляйте продуктовыми матрицами для вашего ресторана</p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Создать матрицу
        </Button>
      </div>

      {matrices.length === 0 ? (
        <Card className="p-12 text-center">
          <Grid3x3 className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-4">У вас пока нет матриц</p>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Создать первую матрицу
          </Button>
        </Card>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {matrices.map((matrix) => (
            <Card key={matrix.id} className="p-6 hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-xl font-semibold mb-2">{matrix.name}</h3>
                  <p className="text-sm text-gray-600">
                    Создана: {new Date(matrix.createdAt).toLocaleDateString('ru-RU')}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDeleteMatrix(matrix.id)}
                  className="text-red-600 hover:text-red-700"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => window.location.href = `/customer/matrix/${matrix.id}`}
              >
                Управлять продуктами
              </Button>
            </Card>
          ))}
        </div>
      )}

      {/* Create Matrix Modal */}
      <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Создать новую матрицу</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Название матрицы</label>
              <Input
                placeholder="Например: Основное меню"
                value={newMatrixName}
                onChange={(e) => setNewMatrixName(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleCreateMatrix()}
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setShowCreateModal(false)}
              >
                Отмена
              </Button>
              <Button
                className="flex-1"
                onClick={handleCreateMatrix}
                disabled={!newMatrixName.trim()}
              >
                Создать
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
