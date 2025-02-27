'use client';

import { useState } from 'react';
import { useStorage } from '@/hooks/useStorage';
import { FolderIcon, DocumentIcon, ChevronUpIcon, PlusIcon } from '@heroicons/react/24/outline';
import { formatBytes, formatDate } from '@/utils/format';

export default function BucketPage({ params }: { params: { bucket: string } }) {
  const [newFolderName, setNewFolderName] = useState('');
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  
  const {
    objects,
    currentPrefix,
    parentPrefix,
    loading,
    error,
    createFolder,
    navigateToFolder,
    navigateUp
  } = useStorage(params.bucket);

  const handleCreateFolder = async () => {
    if (newFolderName) {
      const success = await createFolder(newFolderName);
      if (success) {
        setNewFolderName('');
        setShowNewFolderDialog(false);
      }
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#03619B]"></div>
    </div>;
  }

  if (error) {
    return <div className="text-red-500">{error}</div>;
  }

  return (
    <div className="max-w-7xl mx-auto p-8">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center space-x-4">
          <h1 className="text-3xl font-bold">{params.bucket}</h1>
          {currentPrefix && (
            <span className="text-gray-500">/{currentPrefix}</span>
          )}
        </div>
        <button
          onClick={() => setShowNewFolderDialog(true)}
          className="flex items-center px-4 py-2 bg-[#03619B] text-white rounded-lg hover:bg-[#024d7c]"
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          New Folder
        </button>
      </div>

      {parentPrefix !== undefined && (
        <button
          onClick={navigateUp}
          className="flex items-center mb-4 text-gray-600 hover:text-gray-900"
        >
          <ChevronUpIcon className="h-5 w-5 mr-1" />
          Up to parent folder
        </button>
      )}

      <div className="bg-white rounded-lg shadow">
        <div className="grid grid-cols-12 gap-4 p-4 border-b text-sm font-medium text-gray-500">
          <div className="col-span-6">Name</div>
          <div className="col-span-2">Size</div>
          <div className="col-span-4">Last Modified</div>
        </div>

        <div className="divide-y">
          {objects.map((object) => (
            <div key={object.path} className="grid grid-cols-12 gap-4 p-4 hover:bg-gray-50">
              <div className="col-span-6 flex items-center">
                {object.type === 'folder' ? (
                  <button
                    onClick={() => navigateToFolder(object.path)}
                    className="flex items-center text-[#03619B] hover:text-[#024d7c]"
                  >
                    <FolderIcon className="h-5 w-5 mr-2" />
                    {object.name}
                  </button>
                ) : (
                  <div className="flex items-center">
                    <DocumentIcon className="h-5 w-5 mr-2 text-gray-400" />
                    {object.name}
                  </div>
                )}
              </div>
              <div className="col-span-2">{object.size ? formatBytes(object.size) : '-'}</div>
              <div className="col-span-4">{object.modified ? formatDate(object.modified) : '-'}</div>
            </div>
          ))}
        </div>
      </div>

      {showNewFolderDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 w-96">
            <h3 className="text-lg font-medium mb-4">Create New Folder</h3>
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Folder name"
              className="w-full p-2 border rounded mb-4"
            />
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setShowNewFolderDialog(false)}
                className="px-4 py-2 text-gray-600 hover:text-gray-900"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateFolder}
                className="px-4 py-2 bg-[#03619B] text-white rounded hover:bg-[#024d7c]"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
} 