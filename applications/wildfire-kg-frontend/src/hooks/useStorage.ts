import { useState, useEffect } from 'react';

export interface Bucket {
  name: string;
  created: string;
}

export interface BucketList {
  buckets: Bucket[];
}

export function useStorage() {
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBuckets();
  }, []);

  const fetchBuckets = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/storage/buckets`);
      if (!response.ok) {
        throw new Error('Failed to fetch buckets');
      }
      const data: BucketList = await response.json();
      setBuckets(data.buckets);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      // Fallback to empty buckets list if API fails
      setBuckets([]);
    } finally {
      setLoading(false);
    }
  };

  return { buckets, loading, error };
} 