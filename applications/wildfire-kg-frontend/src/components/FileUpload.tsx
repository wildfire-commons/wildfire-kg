import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

export default function FileUpload() {
  const [uploading, setUploading] = useState(false);
  const [fileType, setFileType] = useState('terrestrial'); // or 'aerial'

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setUploading(true);
    try {
      const file = acceptedFiles[0];
      const formData = new FormData();
      formData.append('file', file);
      formData.append('type', fileType);

      // TODO: Replace with your API endpoint
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      // Handle success
      alert('File uploaded successfully!');
    } catch (error) {
      console.error('Upload error:', error);
      alert('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }, [fileType]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/x-laz': ['.laz'],
      'application/x-las': ['.las']
    },
    maxFiles: 1
  });

  return (
    <div className="w-full max-w-2xl">
      <div className="mb-4">
        <label className="block text-sm font-medium mb-2">LiDAR Type:</label>
        <select 
          value={fileType}
          onChange={(e) => setFileType(e.target.value)}
          className="w-full p-2 border rounded-md"
        >
          <option value="terrestrial">Terrestrial LiDAR</option>
          <option value="aerial">Aerial LiDAR</option>
        </select>
      </div>

      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
          ${isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}`}
      >
        <input {...getInputProps()} />
        {uploading ? (
          <p>Uploading...</p>
        ) : isDragActive ? (
          <p>Drop the LiDAR file here...</p>
        ) : (
          <p>Drag and drop a LiDAR file here, or click to select file</p>
        )}
      </div>
    </div>
  );
} 