import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Upload, FileText, File, Paperclip } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const statusColors = {
  uploaded: 'bg-blue-100 text-blue-800',
  verified: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800'
};

const statusLabels = {
  uploaded: 'Загружен',
  verified: 'Проверен',
  rejected: 'Отклонен'
};

const documentTypes = [
  'Договор аренды',
  'Приказ о назначении',
  'Устав',
  'Свидетельство о регистрации',
  'Другое'
];

export const CustomerDocuments = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [company, setCompany] = useState(null);
  
  const [formData, setFormData] = useState({
    documentType: '',
    edo: '',
    guid: '',
    files: []
  });

  useEffect(() => {
    fetchDocuments();
    fetchCompany();
  }, []);

  const fetchCompany = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/companies/my`, { headers });
      setCompany(response.data);
    } catch (error) {
      console.error('Failed to fetch company:', error);
    }
  };

  const fetchDocuments = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await axios.get(`${API}/documents/my`, { headers });
      setDocuments(response.data);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files) {
      setFormData({
        ...formData,
        files: Array.from(e.target.files)
      });
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (formData.files.length === 0 || !formData.documentType) {
      setMessage('Выберите тип документа и прикрепите файлы');
      setTimeout(() => setMessage(''), 3000);
      return;
    }

    setUploading(true);
    setMessage('');

    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      for (const file of formData.files) {
        const uploadFormData = new FormData();
        uploadFormData.append('file', file);
        uploadFormData.append('document_type', formData.documentType);

        await axios.post(`${API}/documents/upload`, uploadFormData, {
          headers: {
            ...headers,
            'Content-Type': 'multipart/form-data'
          }
        });
      }

      setMessage('success');
      setFormData({
        documentType: '',
        edo: '',
        guid: '',
        files: []
      });
      const fileInput = document.getElementById('files');
      if (fileInput) fileInput.value = '';
      
      fetchDocuments();
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('error');
      setTimeout(() => setMessage(''), 3000);
    } finally {
      setUploading(false);
    }
  };

  const isFormValid = () => {
    return formData.documentType && 
           formData.edo && 
           formData.guid && 
           formData.files.length > 0;
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-documents-page" className="max-w-5xl mx-auto">
      <h2 className="text-4xl font-bold mb-2">Документы</h2>
      <p className="text-base text-muted-foreground mb-6">Управление документами по договорам с поставщиками</p>

      {/* Uploaded Documents List */}
      <Card className="p-6 mb-6">
        <h3 className="text-xl font-semibold mb-4">Загруженные документы</h3>
        {documents.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-3 opacity-50" />
            <p>Документы не загружены</p>
          </div>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) => (
              <div key={doc.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                    <FileText className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="font-medium">{doc.type}</p>
                    <p className="text-sm text-gray-600">
                      Загружен: {new Date(doc.createdAt).toLocaleDateString('ru-RU')}
                    </p>
                  </div>
                </div>
                <Badge className={statusColors[doc.status]}>
                  {statusLabels[doc.status]}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Messages */}
      {message === 'success' && (
        <Alert className="mb-6 bg-green-50 border-green-200">
          <AlertDescription className="text-green-800">
            ✓ Документы успешно загружены
          </AlertDescription>
        </Alert>
      )}
      
      {message === 'error' && (
        <Alert className="mb-6 bg-red-50 border-red-200">
          <AlertDescription className="text-red-800">
            ✗ Ошибка при загрузке документов
          </AlertDescription>
        </Alert>
      )}

      {message && !['success', 'error'].includes(message) && (
        <Alert className="mb-6">
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      {/* Upload Form */}
      <Card className="p-6">
        <h3 className="text-xl font-semibold mb-4">Загрузить новый документ</h3>
        <p className="text-sm text-muted-foreground mb-6">
          Загрузите документы, связанные с договорами поставщиков
        </p>
        
        <form onSubmit={handleUpload} className="space-y-5">
          {/* 1. Document Type */}
          <div>
            <Label htmlFor="documentType" className="text-sm font-medium mb-2">
              1. Тип документа <span className="text-red-500">*</span>
            </Label>
            <select
              id="documentType"
              value={formData.documentType}
              onChange={(e) => setFormData({ ...formData, documentType: e.target.value })}
              className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            >
              <option value="">Выберите тип</option>
              {documentTypes.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>

          {/* 2. ЭДО Number */}
          <div>
            <Label htmlFor="edo" className="text-sm font-medium mb-2">
              2. Номер ЭДО <span className="text-red-500">*</span>
            </Label>
            <Input
              id="edo"
              value={formData.edo}
              onChange={(e) => setFormData({ ...formData, edo: e.target.value })}
              placeholder="Введите номер электронного документооборота"
              required
            />
          </div>

          {/* 3. GUID */}
          <div>
            <Label htmlFor="guid" className="text-sm font-medium mb-2">
              3. GUID <span className="text-red-500">*</span>
            </Label>
            <Input
              id="guid"
              value={formData.guid}
              onChange={(e) => setFormData({ ...formData, guid: e.target.value })}
              placeholder="Введите GUID"
              required
            />
          </div>

          {/* 4. Attach Documents */}
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 bg-gray-50">
            <div className="text-center">
              <Paperclip className="h-10 w-10 mx-auto mb-3 text-gray-400" />
              <Label htmlFor="files" className="text-base font-medium mb-2 block">
                4. Прикрепить документы <span className="text-red-500">*</span>
              </Label>
              <p className="text-sm text-gray-500 mb-4">
                PDF, DOC, DOCX, JPG, PNG (макс. 10 МБ)
              </p>
              <Input
                id="files"
                type="file"
                onChange={handleFileChange}
                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                multiple
                required
                className="cursor-pointer"
              />
              {formData.files.length > 0 && (
                <div className="mt-4 text-left">
                  <p className="text-sm font-medium mb-2">Выбрано файлов: {formData.files.length}</p>
                  <ul className="text-sm text-gray-600 space-y-1">
                    {formData.files.map((file, idx) => (
                      <li key={idx} className="flex items-center gap-2">
                        <File className="h-3 w-3" />
                        {file.name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          <Button 
            type="submit" 
            disabled={uploading || !isFormValid()} 
            data-testid="submit-moderation-btn"
            size="lg"
            className="w-full"
          >
            <Upload className="h-4 w-4 mr-2" />
            {uploading ? 'Загрузка...' : 'Отправить на модерацию'}
          </Button>
          
          {!isFormValid() && (
            <p className="text-sm text-amber-600 text-center">
              Заполните все обязательные поля (Тип, ЭДО, GUID) и прикрепите документы
            </p>
          )}
        </form>
      </Card>
    </div>
  );
};
