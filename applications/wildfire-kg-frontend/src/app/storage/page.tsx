'use client';

import { FolderIcon } from '@heroicons/react/24/outline';
import { useStorage } from '@/hooks/useStorage';

export default function StoragePage() {
  const { buckets, loading, error } = useStorage();

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <h1 className="text-3xl font-bold mb-8">Data Storage</h1>
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#03619B]"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <h1 className="text-3xl font-bold mb-8">Data Storage</h1>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-8">S3 Buckets</h1>
      
      <div className="space-y-4">
        {buckets.map((bucket) => (
          <div 
            key={bucket.name}
            className="bg-white rounded-lg shadow-sm p-4 hover:shadow-md transition-shadow duration-200"
          >
            <div className="flex items-center">
              <FolderIcon className="h-6 w-6 text-[#03619B]" />
              <div className="ml-3">
                <h2 className="text-lg font-semibold text-gray-900">{bucket.name}</h2>
                <p className="text-sm text-gray-500">
                  Created: {new Date(bucket.created).toLocaleDateString()}
                </p>
              </div>
            </div>
          </div>
        ))}
        
        {buckets.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            No buckets found
          </div>
        )}
      </div>
    </div>
  );
} 