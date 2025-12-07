import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Upload, FileText } from 'lucide-react';

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
  'Устав',
  'Свидетельство о регистрации',
  'ИНН',
  'ОГРН',
  'Договор аренды',
  'Другое'
];

export const CustomerDocuments = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [documentType, setDocumentType] = useState('');

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const response = await axios.get(`${API}/documents/my`);
      setDocuments(response.data);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile || !documentType) {
      setMessage('Выберите файл и тип документа');
      return;
    }

    setUploading(true);
    setMessage('');

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('document_type', documentType);

      await axios.post(`${API}/documents/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      setMessage('Документ успешно загружен');
      setSelectedFile(null);
      setDocumentType('');
      fetchDocuments();
    } catch (error) {
      setMessage('Ошибка при загрузке документа');
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Загрузка...</div>;
  }

  return (
    <div data-testid="customer-documents-page">
      <h2 className="text-2xl font-bold mb-6">Документы</h2>

      {message && (
        <Alert className="mb-4" variant={message.includes('успешно') ? 'default' : 'destructive'}>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      <Card className="p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Загрузить новый документ</h3>
        <form onSubmit={handleUpload} className="space-y-4">
          <div>
            <Label htmlFor="documentType">Тип документа</Label>
            <select
              id="documentType"
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            >
              <option value="">Выберите тип</option>
              {documentTypes.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="file">Файл</Label>
            <Input
              id="file"
              type="file"
              onChange={handleFileChange}
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
              required
            />
            {selectedFile && (
              <p className="text-sm text-gray-600 mt-1">Выбран: {selectedFile.name}</p>
            )}
          </div>
          <Button type="submit" disabled={uploading} data-testid="upload-document-btn">
            <Upload className="h-4 w-4 mr-2" />
            {uploading ? 'Загрузка...' : 'Загрузить'}
          </Button>
        </form>
      </Card>

      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">Загруженные документы</h3>
        {documents.length === 0 ? (
          <p className="text-gray-600 text-center py-4">Документы не загружены</p>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) => (
              <div key={doc.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                    <FileText className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="font-medium">{doc.type}</p>
                    <p className="text-sm text-gray-600">
                      {new Date(doc.createdAt).toLocaleDateString('ru-RU')}
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
    </div>
  );
};