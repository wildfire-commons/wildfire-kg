'use client';

import { FolderIcon, ChartBarIcon, CloudIcon } from '@heroicons/react/24/outline';
import Link from 'next/link';
import { useStorage } from '@/hooks/useStorage';

export default function StoragePage() {
  const { categories, loading, error } = useStorage();

  const getIcon = (type: string) => {
    switch (type) {
      case 'folder':
        return <FolderIcon className="h-8 w-8 text-[#03619B]" />;
      case 'chart':
        return <ChartBarIcon className="h-8 w-8 text-[#03619B]" />;
      case 'cloud':
        return <CloudIcon className="h-8 w-8 text-[#03619B]" />;
      default:
        return <FolderIcon className="h-8 w-8 text-[#03619B]" />;
    }
  };

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
      <h1 className="text-3xl font-bold mb-8">Data Storage</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {categories.map((category) => (
          <Link 
            href={`/storage/${category.id}`} 
            key={category.id}
            className="block bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow duration-200"
          >
            <div className="p-6">
              <div className="flex items-center mb-4">
                {getIcon(category.icon)}
                <h2 className="ml-3 text-xl font-semibold text-gray-900">{category.name}</h2>
              </div>
              <p className="text-gray-600 mb-4">{category.description}</p>
              <div className="flex justify-between text-sm text-gray-500">
                <span>{category.itemCount} items</span>
                <span>Updated {new Date(category.lastUpdated).toLocaleDateString()}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
} 