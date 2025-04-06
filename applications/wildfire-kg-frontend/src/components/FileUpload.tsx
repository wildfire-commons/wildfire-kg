import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useFileUpload } from '../hooks/useFileUpload';  // Assuming the hook is in this path

export default function FileUpload() {
  const [fileType, setFileType] = useState('terrestrial'); // or 'aerial'
  const { uploading, success, error, uploadFile } = useFileUpload();
  
  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    const bucketName = "wifire-kg";

    if (file) {
      await uploadFile(file, bucketName, fileType);  // Pass the selected file type
    }
  }, [fileType, uploadFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/x-laz': ['.laz'],
      'application/x-las': ['.las'],
    },
    maxFiles: 1,
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
        {error && <p className="text-red-500">{error}</p>}
        {success && <p className="text-green-500">Upload successful!</p>}
      </div>
    </div>
  );
}
