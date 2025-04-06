'use client';

import FileUpload from '@/components/FileUpload';
import MetricEntry from '@/components/MetricEntry';
import { useState } from 'react';

export default function UploadPage() {
  const [activeTab, setActiveTab] = useState<'upload' | 'manual'>('upload');

  return (
    <div className="min-h-screen p-8">
      <main className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">LiDAR Data Entry</h1>
        
        <div className="mb-8">
          <div className="flex gap-4 mb-6">
            <button
              onClick={() => setActiveTab('upload')}
              className={`px-4 py-2 rounded-md ${
                activeTab === 'upload'
                  ? 'bg-[#03619B] text-white'
                  : 'bg-gray-100'
              }`}
            >
              File Upload
            </button>
            <button
              onClick={() => setActiveTab('manual')}
              className={`px-4 py-2 rounded-md ${
                activeTab === 'manual'
                  ? 'bg-[#03619B] text-white'
                  : 'bg-gray-100'
              }`}
            >
              Manual Entry
            </button>
          </div>

          {activeTab === 'upload' ? (
            <div className="bg-white p-6 rounded-lg shadow-sm">
              <FileUpload />
            </div>
          ) : (
            <div className="bg-white p-6 rounded-lg shadow-sm">
              <MetricEntry />
            </div>
          )}
        </div>
      </main>
    </div>
  );
} 