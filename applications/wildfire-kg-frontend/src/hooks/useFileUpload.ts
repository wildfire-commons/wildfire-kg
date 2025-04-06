import { useState, useCallback } from 'react';

export interface PresignedUrlResponse {
  presigned_url: string;
  file_key: string;
  expires_in: number;
}

export function useFileUpload() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);

  const generatePresignedUrl = useCallback(
    async (bucketName: string, fileName: string, fileType: string) => {
      try {
        setUploading(true);
        setError(null);  // Reset previous errors
        setSuccess(false); // Reset success flag

        // Step 1: Request the presigned URL from the backend using the correct API URL prefix
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/storage/buckets/${bucketName}/presigned-url`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              file_name: `${fileType}/${fileName}`, // Include fileType (terrestrial/aerial) in the file path
            }),
          }
        );

        if (!response.ok) {
          throw new Error('Failed to fetch presigned URL');
        }

        const data: PresignedUrlResponse = await response.json();
        return data;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
        setUploading(false);
        throw err; // Re-throw the error after updating state
      }
    },
    []
  );

  const uploadFile = useCallback(
    async (file: File, bucketName: string, fileType: string) => {
      try {
        setUploading(true);
        setError(null); // Reset previous errors
        setSuccess(false); // Reset success flag

        // Step 2: Get the presigned URL for the file upload
        const presignedData = await generatePresignedUrl(bucketName, file.name, fileType);
        console.log(presignedData)
        
        // Step 3: Upload the file to S3 using the presigned URL
        const uploadResponse = await fetch(presignedData.presigned_url, {
          method: 'PUT',
          headers: {
            'Content-Type': file.type || 'application/octet-stream', // Fallback to application/octet-stream if no type is available
          },
          body: file,
        });

        console.log("upload succeeded")

        if (!uploadResponse.ok) {
          throw new Error('Failed to upload file to S3');
        }

        // Step 4: Update the state to reflect the successful upload
        setSuccess(true);
        alert('File uploaded successfully!');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
        alert('File upload failed. Please try again.');
      } finally {
        setUploading(false);
      }
    },
    [generatePresignedUrl]
  );

  return {
    uploading,
    success,
    error,
    uploadFile,
  };
}
