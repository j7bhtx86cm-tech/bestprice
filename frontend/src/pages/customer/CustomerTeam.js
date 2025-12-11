import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { User, Plus, Trash2, Mail, Phone } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const CustomerTeam = () => {
  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [teamMembers, setTeamMembers] = useState([
    { name: '', phone: '', email: '', position: '' }
  ]);

  useEffect(() => {
    fetchCompany();
  }, []);

  const fetchCompany = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/companies/my`, { headers });
      setCompany(response.data);
      
      // Load existing contact person as first team member
      if (response.data.contactPersonName) {
        setTeamMembers([{
          name: response.data.contactPersonName || '',
          phone: response.data.contactPersonPhone || '',
          email: response.data.email || '',
          position: response.data.contactPersonPosition || ''
        }]);
      }
    } catch (error) {
      console.error('Failed to fetch company:', error);
    } finally {
      setLoading(false);
    }
  };

  const addTeamMember = () => {
    setTeamMembers([...teamMembers, { name: '', phone: '', email: '', position: '' }]);
  };

  const removeTeamMember = (index) => {
    if (teamMembers.length > 1) {
      setTeamMembers(teamMembers.filter((_, i) => i !== index));
    }
  };

  const updateTeamMember = (index, field, value) => {
    const updated = [...teamMembers];
    updated[index][field] = value;
    setTeamMembers(updated);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage('');

    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      // Save primary contact (first team member)
      const primary = teamMembers[0];
      await axios.put(`${API}/companies/my`, {
        contactPersonName: primary.name,
        contactPersonPhone: primary.phone,
        contactPersonPosition: primary.position,
        email: primary.email
      }, { headers });
      
      setMessage('success');
      fetchCompany();
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('error');
      setTimeout(() => setMessage(''), 3000);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-team-page" className="max-w-4xl mx-auto">
      <h2 className="text-4xl font-bold mb-2">Ответственные лица и доступ</h2>
      <p className="text-base text-muted-foreground mb-6">
        Управление командой и доступом к платформе
      </p>

      {message === 'success' && (
        <Alert className="mb-6 bg-green-50 border-green-200">
          <AlertDescription className="text-green-800">
            ✓ Данные успешно сохранены
          </AlertDescription>
        </Alert>
      )}
      
      {message === 'error' && (
        <Alert className="mb-6 bg-red-50 border-red-200">
          <AlertDescription className="text-red-800">
            ✗ Ошибка при сохранении
          </AlertDescription>
        </Alert>
      )}

      <form onSubmit={handleSubmit} className=\"space-y-6\">
        {teamMembers.map((member, index) => (
          <Card key={index} className=\"p-6\">
            <div className=\"flex justify-between items-start mb-4\">
              <div className=\"flex items-center gap-3\">
                <div className=\"w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center\">
                  <User className=\"w-5 h-5 text-blue-600\" />
                </div>
                <div>
                  <h3 className=\"font-semibold\">{index === 0 ? 'Основной контакт' : `Сотрудник ${index + 1}`}</h3>
                  <p className=\"text-sm text-gray-600\">Ответственное лицо</p>
                </div>
              </div>
              {index > 0 && (
                <Button
                  type=\"button\"
                  variant=\"ghost\"
                  size=\"sm\"
                  onClick={() => removeTeamMember(index)}
                  className=\"text-red-600 hover:text-red-700\"
                >
                  <Trash2 className=\"h-4 w-4\" />
                </Button>
              )}
            </div>

            <div className=\"grid md:grid-cols-2 gap-4\">
              <div>
                <Label className=\"text-sm mb-2\">ФИО <span className=\"text-red-500\">*</span></Label>
                <Input
                  value={member.name}
                  onChange={(e) => updateTeamMember(index, 'name', e.target.value)}
                  placeholder=\"Иванов Иван Иванович\"
                  required
                />
              </div>

              <div>
                <Label className=\"text-sm mb-2\">Должность</Label>
                <Input
                  value={member.position}
                  onChange={(e) => updateTeamMember(index, 'position', e.target.value)}
                  placeholder=\"Директор, Менеджер...\"
                />
              </div>

              <div>
                <Label className=\"text-sm mb-2\">
                  <Phone className=\"h-3 w-3 inline mr-1\" />
                  Телефон <span className=\"text-red-500\">*</span>
                </Label>
                <Input
                  type=\"tel\"
                  value={member.phone}
                  onChange={(e) => updateTeamMember(index, 'phone', e.target.value)}
                  placeholder=\"+7 (999) 123-45-67\"
                  required
                />
              </div>

              <div>
                <Label className=\"text-sm mb-2\">
                  <Mail className=\"h-3 w-3 inline mr-1\" />
                  Email <span className=\"text-red-500\">*</span>
                </Label>
                <Input
                  type=\"email\"
                  value={member.email}
                  onChange={(e) => updateTeamMember(index, 'email', e.target.value)}
                  placeholder=\"ivanov@company.ru\"
                  required
                />
              </div>
            </div>
          </Card>
        ))}

        <Button
          type=\"button\"
          variant=\"outline\"
          onClick={addTeamMember}
          className=\"w-full\"
        >
          <Plus className=\"h-4 w-4 mr-2\" />
          Добавить сотрудника
        </Button>

        <Button type=\"submit\" disabled={saving} className=\"w-full\" size=\"lg\">
          {saving ? 'Сохранение...' : 'Сохранить все изменения'}
        </Button>
      </form>

      <Card className=\"p-6 mt-6 bg-blue-50\">
        <h3 className=\"text-lg font-semibold mb-2\">Управление доступом</h3>
        <p className=\"text-sm text-gray-700\">
          Добавьте сотрудников вашей компании для совместной работы на платформе BestPrice.
          В будущих версиях будет доступно управление правами доступа для каждого сотрудника.
        </p>
      </Card>
    </div>
  );
};
