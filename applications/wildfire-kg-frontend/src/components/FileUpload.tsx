import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useFileUpload } from '../hooks/useFileUpload';
import { DataCategory, LidarType } from '../hooks/useFileUpload';

export default function FileUpload() {
  const [dataCategory, setDataCategory] = useState<DataCategory>('lidar');
  const [lidarType, setLidarType] = useState<LidarType>('terrestrial');
  const { uploading, success, error, uploadFile } = useFileUpload();
  
  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    const bucketName = "wifire-kg";

    if (file) {
      try {
        if (dataCategory === 'lidar') {
          await uploadFile(file, bucketName, dataCategory, lidarType);
        } else {
          await uploadFile(file, bucketName, dataCategory);
        }
      } catch (err) {
        console.error('Drop error:', err);
      }
    }
  }, [dataCategory, lidarType, uploadFile]);

  // Define accepted file types based on data category
  const getAcceptedTypes = () => {
    switch (dataCategory) {
      case 'lidar':
        return {
          'application/x-laz': ['.laz'],
          'application/x-las': ['.las']
        };
      case 'metrics':
        return {
          'text/csv': ['.csv']
        };
      case 'ignitions':
        return {
          'application/json': ['.geojson'],
          'text/csv': ['.csv']
        };
      default:
        return {};
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: getAcceptedTypes(),
    maxFiles: 1,
  });

  return (
    <div className="w-full max-w-2xl">
      <div className="mb-4">
        <label className="block text-sm font-medium mb-2">Data Category:</label>
        <select
          value={dataCategory}
          onChange={(e) => setDataCategory(e.target.value as DataCategory)}
          className="w-full p-2 border rounded-md mb-2"
        >
          <option value="lidar">LiDAR Data</option>
          <option value="metrics">Plot Metrics</option>
          <option value="ignitions">Ignitions</option>
        </select>

        {dataCategory === 'lidar' && (
          <div className="mt-2">
            <label className="block text-sm font-medium mb-2">LiDAR Type:</label>
            <select
              value={lidarType}
              onChange={(e) => setLidarType(e.target.value as LidarType)}
              className="w-full p-2 border rounded-md"
            >
              <option value="terrestrial">Terrestrial</option>
              <option value="aerial">Aerial</option>
            </select>
          </div>
        )}
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
          <p>Drop the file here...</p>
        ) : (
          <p>
            Drag and drop a {dataCategory === 'lidar' ? `${lidarType} LiDAR` : dataCategory} file here, or click to select
          </p>
        )}
        {error && <p className="text-red-500 mt-2">{error}</p>}
        {success && <p className="text-green-500 mt-2">Upload successful!</p>}
      </div>
    </div>
  );
}
