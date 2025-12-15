import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { User, Plus, Trash2, Mail, Phone, UserCheck } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerTeam = () => {
  const [teamMembers, setTeamMembers] = useState([]);
  const [matrices, setMatrices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [message, setMessage] = useState('');
  const [newMember, setNewMember] = useState({
    name: '',
    position: 'staff',
    phone: '',
    email: '',
    matrixId: ''
  });

  useEffect(() => {
    fetchTeamMembers();
    fetchMatrices();
  }, []);

  const fetchMatrices = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/matrices`, { headers });
      setMatrices(response.data);
    } catch (error) {
      console.error('Failed to fetch matrices:', error);
    }
  };

  const fetchTeamMembers = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/team/members`, { headers });
      setTeamMembers(response.data || []);
    } catch (error) {
      console.error('Failed to fetch team members:', error);
      setTeamMembers([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAddMember = async () => {
    if (!newMember.name || !newMember.email || !newMember.phone) {
      alert('Пожалуйста, заполните все обязательные поля');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const role = newMember.position === 'chef' ? 'chef' : 'responsible';
      const password = 'password123';
      
      await axios.post(
        `${API}/team/members`,
        {
          name: newMember.name,
          role: role,
          phone: newMember.phone,
          email: newMember.email,
          matrixId: newMember.matrixId || null,
          password: password
        },
        { headers }
      );
      
      setShowAddModal(false);
      setNewMember({
        name: '',
        position: 'staff',
        phone: '',
        email: '',
        matrixId: ''
      });
      
      fetchTeamMembers();
      
      setMessage(`success|Сотрудник добавлен!\nEmail: ${newMember.email}\nПароль: ${password}`);
      setTimeout(() => setMessage(''), 5000);
    } catch (error) {
      console.error('Failed to add team member:', error);
      setMessage('error|' + (error.response?.data?.detail || 'Ошибка добавления сотрудника'));
      setTimeout(() => setMessage(''), 5000);
    }
  };

  const handleDeleteMember = async (memberId) => {
    if (!confirm('Вы уверены, что хотите удалить этого сотрудника?')) return;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.delete(`${API}/team/members/${memberId}`, { headers });
      fetchTeamMembers();
      setMessage('success|Сотрудник удален');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      console.error('Failed to delete member:', error);
      setMessage('error|Ошибка удаления сотрудника');
      setTimeout(() => setMessage(''), 3000);
    }
  };

  const getRoleLabel = (role) => {
    return role === 'chef' ? 'Повар' : 'Сотрудник';
  };

  const getMatrixName = (matrixId) => {
    const matrix = matrices.find(m => m.id === matrixId);
    return matrix ? matrix.name : 'Не назначена';
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  const [messageType, messageText] = message.split('|');

  return (
    <div data-testid="customer-team-page">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-4xl font-bold mb-2">Ответственные лица и доступ</h2>
          <p className="text-base text-muted-foreground">
            Управление командой и доступом к платформе
          </p>
        </div>
        <Button onClick={() => setShowAddModal(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Добавить сотрудника
        </Button>
      </div>

      {messageType === 'success' && (
        <Alert className="mb-6 bg-green-50 border-green-200">
          <AlertDescription className="text-green-800 whitespace-pre-line">
            ✓ {messageText}
          </AlertDescription>
        </Alert>
      )}
      
      {messageType === 'error' && (
        <Alert className="mb-6 bg-red-50 border-red-200">
          <AlertDescription className="text-red-800">
            ✗ {messageText}
          </AlertDescription>
        </Alert>
      )}

      {teamMembers.length === 0 ? (
        <Card className="p-12 text-center">
          <User className="h-16 w-16 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 mb-4">У вас пока нет сотрудников</p>
          <Button onClick={() => setShowAddModal(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Добавить первого сотрудника
          </Button>
        </Card>
      ) : (
        <div className="space-y-4">
          {teamMembers.map((member) => (
            <Card key={member.id} className="p-6">
              <div className="flex justify-between items-start">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                    <UserCheck className="w-6 h-6 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-lg">{member.name || member.email}</h3>
                    <p className="text-sm text-gray-600 mb-2">
                      <span className="font-medium">{getRoleLabel(member.role)}</span>
                    </p>
                    <div className="space-y-1">
                      <p className="text-sm text-gray-600">
                        <Mail className="h-3 w-3 inline mr-1" />
                        {member.email}
                      </p>
                      {member.phone && (
                        <p className="text-sm text-gray-600">
                          <Phone className="h-3 w-3 inline mr-1" />
                          {member.phone}
                        </p>
                      )}
                      {member.matrixId && (
                        <p className="text-sm text-blue-600">
                          Матрица: {getMatrixName(member.matrixId)}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDeleteMember(member.id)}
                  className="text-red-600 hover:text-red-700"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Add Member Modal */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Добавить сотрудника</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label className="text-sm mb-2 block">
                ФИО <span className="text-red-500">*</span>
              </Label>
              <Input
                value={newMember.name}
                onChange={(e) => setNewMember({ ...newMember, name: e.target.value })}
                placeholder="Иванов Иван Иванович"
              />
            </div>

            <div>
              <Label className="text-sm mb-2 block">
                Должность <span className="text-red-500">*</span>
              </Label>
              <select
                value={newMember.position}
                onChange={(e) => setNewMember({ ...newMember, position: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="staff">Сотрудник</option>
                <option value="chef">Повар</option>
              </select>
            </div>

            <div>
              <Label className="text-sm mb-2 block">
                Телефон <span className="text-red-500">*</span>
              </Label>
              <Input
                type="tel"
                value={newMember.phone}
                onChange={(e) => setNewMember({ ...newMember, phone: e.target.value })}
                placeholder="+7 (999) 123-45-67"
              />
            </div>

            <div>
              <Label className="text-sm mb-2 block">
                Email <span className="text-red-500">*</span>
              </Label>
              <Input
                type="email"
                value={newMember.email}
                onChange={(e) => setNewMember({ ...newMember, email: e.target.value })}
                placeholder="ivanov@company.ru"
              />
            </div>

            {matrices.length > 0 && (
              <div>
                <Label className="text-sm mb-2 block">Назначить матрицу (опционально)</Label>
                <select
                  value={newMember.matrixId}
                  onChange={(e) => setNewMember({ ...newMember, matrixId: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Без матрицы</option>
                  {matrices.map((matrix) => (
                    <option key={matrix.id} value={matrix.id}>
                      {matrix.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex gap-2 pt-4">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setShowAddModal(false)}
              >
                Отмена
              </Button>
              <Button
                className="flex-1"
                onClick={handleAddMember}
              >
                Добавить
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Card className="p-6 mt-6 bg-blue-50">
        <h3 className="text-lg font-semibold mb-2">Управление доступом</h3>
        <p className="text-sm text-gray-700 mb-4">
          Добавьте сотрудников вашей компании для совместной работы на платформе BestPrice.
        </p>
        <div className="space-y-2 text-sm text-gray-600">
          <p>
            <strong>Сотрудник:</strong> Имеет доступ к матрице, каталогу и созданию заказов.
          </p>
          <p>
            <strong>Повар:</strong> Такие же права, как у сотрудника, но с другой ролью для внутреннего разделения.
          </p>
          <p className="text-gray-500 mt-4">
            После добавления сотрудника, он получит email для входа и пароль по умолчанию:{' '}
            <code className="bg-white px-2 py-1 rounded">password123</code>
          </p>
        </div>
      </Card>
    </div>
  );
};
