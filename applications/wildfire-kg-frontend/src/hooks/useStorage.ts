import { useState, useEffect } from 'react';

export interface Bucket {
  name: string;
  created: string;
}

export interface S3Object {
  name: string;
  path: string;
  type: 'folder' | 'file';
  size?: number;
  modified?: string;
}

export interface BucketListResponse {
  buckets: Bucket[];
}

export interface S3ListResponse {
  objects: S3Object[];
  prefix: string;
  parent_prefix?: string;
}

export function useStorage(bucketName?: string, prefix: string = "") {
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [objects, setObjects] = useState<S3Object[]>([]);
  const [currentPrefix, setCurrentPrefix] = useState(prefix);
  const [parentPrefix, setParentPrefix] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (bucketName) {
      fetchObjects();
    } else {
      fetchBuckets();
    }
  }, [bucketName, currentPrefix]);

  const fetchBuckets = async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/storage/buckets`
      );
      if (!response.ok) {
        throw new Error('Failed to fetch buckets');
      }
      const data: BucketListResponse = await response.json();
      setBuckets(data.buckets);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const fetchObjects = async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/storage/buckets/${bucketName}/objects?prefix=${currentPrefix}`
      );
      if (!response.ok) {
        throw new Error('Failed to fetch objects');
      }
      const data: S3ListResponse = await response.json();
      setObjects(data.objects);
      setParentPrefix(data.parent_prefix);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const createFolder = async (folderName: string) => {
    try {
      const newPrefix = `${currentPrefix}${folderName}/`;
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/storage/buckets/${bucketName}/folders?prefix=${newPrefix}`,
        { method: 'POST' }
      );
      if (!response.ok) {
        throw new Error('Failed to create folder');
      }
      await fetchObjects();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      return false;
    }
  };

  const navigateToFolder = (newPrefix: string) => {
    setCurrentPrefix(newPrefix);
  };

  const navigateUp = () => {
    if (parentPrefix !== undefined) {
      setCurrentPrefix(parentPrefix);
    }
  };

  return {
    buckets,
    objects,
    currentPrefix,
    parentPrefix,
    loading,
    error,
    createFolder,
    navigateToFolder,
    navigateUp
  };
} 