'use client';

import { useState } from 'react';
import { useStorage } from '@/hooks/useStorage';
import { 
  FolderIcon, 
  DocumentIcon, 
  ChevronUpIcon, 
  PlusIcon,
  TrashIcon,
  ArrowDownTrayIcon
} from '@heroicons/react/24/outline';
import { formatBytes, formatDate } from '@/utils/format';

interface DeleteConfirmationProps {
  folderName: string;
  folderPath: string;
  onConfirm: () => void;
  onCancel: () => void;
  objectCount: number;
}

function DeleteConfirmation({ folderName, folderPath, onConfirm, onCancel, objectCount }: DeleteConfirmationProps) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
      <div className="bg-white rounded-lg p-6 w-96">
        <h3 className="text-lg font-medium mb-4">Delete Folder</h3>
        <p className="text-gray-600 mb-4">
          Are you sure you want to delete the folder "{folderName}"?
          {objectCount > 0 && (
            <span className="block mt-2 text-red-600">
              Warning: This folder contains {objectCount} item{objectCount !== 1 ? 's' : ''}.
              All contents will be permanently deleted.
            </span>
          )}
        </p>
        <div className="flex justify-end space-x-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-gray-600 hover:text-gray-900"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

export default function BucketPage({ params }: { params: { bucket: string } }) {
  const [newFolderName, setNewFolderName] = useState('');
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [deletingFolder, setDeletingFolder] = useState<{ name: string; path: string; count: number } | null>(null);
  
  const {
    objects,
    currentPrefix,
    parentPrefix,
    loading,
    error,
    createFolder,
    deleteFolder,
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

  const handleDeleteClick = (folderPath: string) => {
    const folder = objects.find(obj => obj.path === folderPath);
    if (folder) {
      // Count objects with this prefix
      const objectCount = objects.filter(obj => 
        obj.path.startsWith(folderPath) && obj.path !== folderPath
      ).length;
      
      setDeletingFolder({
        name: folder.name,
        path: folderPath,
        count: objectCount
      });
    }
  };

  const handleDeleteConfirm = async () => {
    if (deletingFolder) {
      try {
        await deleteFolder(deletingFolder.path);
        setDeletingFolder(null);
      } catch (err) {
        console.error('Failed to delete folder:', err);
      }
    }
  };

  const handleDownload = async (filePath: string, fileName: string) => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/storage/buckets/${params.bucket}/download?file_key=${filePath}`
      );
      
      if (!response.ok) {
        throw new Error('Failed to get download URL');
      }

      const data = await response.json();
      
      // Create a temporary link and trigger the download
      const link = document.createElement('a');
      link.href = data.download_url;
      link.download = fileName; // This suggests the filename to the browser
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      console.error('Download error:', err);
      alert('Failed to download file. Please try again.');
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
          <div className="col-span-3">Last Modified</div>
          <div className="col-span-1">Actions</div>
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
              <div className="col-span-3">{object.modified ? formatDate(object.modified) : '-'}</div>
              <div className="col-span-1">
                {object.type === 'folder' ? (
                  <button
                    onClick={() => handleDeleteClick(object.path)}
                    className="text-red-600 hover:text-red-800"
                    title="Delete folder"
                  >
                    <TrashIcon className="h-5 w-5" />
                  </button>
                ) : (
                  <div className="flex space-x-2">
                    <button
                      onClick={() => handleDownload(object.path, object.name)}
                      className="text-[#03619B] hover:text-[#024d7c]"
                      title="Download file"
                    >
                      <ArrowDownTrayIcon className="h-5 w-5" />
                    </button>
                  </div>
                )}
              </div>
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

      {deletingFolder && (
        <DeleteConfirmation
          folderName={deletingFolder.name}
          folderPath={deletingFolder.path}
          objectCount={deletingFolder.count}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeletingFolder(null)}
        />
      )}
    </div>
  );
} 