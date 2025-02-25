'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FolderIcon, ChartBarIcon, CloudIcon } from '@heroicons/react/24/outline';

interface BucketCategory {
  id: string;
  name: string;
  description: string;
  icon: 'folder' | 'chart' | 'cloud';
  itemCount: number;
  lastUpdated: Date;
}

export default function StoragePage() {
  const categories: BucketCategory[] = [
    {
      id: 'tls-metrics',
      name: 'Terrestrial LiDAR Plot Metrics',
      description: 'Processed metrics and measurements from TLS data',
      icon: 'chart',
      itemCount: 89,
      lastUpdated: new Date('2024-02-14'),
    },
    {
      id: 'tls-point-cloud',
      name: 'Terrestrial LiDAR TLS Point Cloud',
      description: 'Raw point cloud data from terrestrial laser scanning',
      icon: 'cloud',
      itemCount: 156,
      lastUpdated: new Date('2024-02-15'),
    },
    {
      id: 'als-point-cloud',
      name: 'Aerial LiDAR ALS Point Cloud',
      description: 'Point cloud data collected from aerial platforms',
      icon: 'cloud',
      itemCount: 234,
      lastUpdated: new Date('2024-02-13'),
    },
  ];

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
                <span>Updated {category.lastUpdated.toLocaleDateString()}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
} 