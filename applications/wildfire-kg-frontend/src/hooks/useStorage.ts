import { useState, useEffect } from 'react';
import { BucketCategory } from '@/types/storage';

export function useStorage() {
  const [categories, setCategories] = useState<BucketCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCategories();
  }, []);

  const fetchCategories = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/storage/categories`);
      if (!response.ok) {
        throw new Error('Failed to fetch storage categories');
      }
      const data = await response.json();
      setCategories(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      // Fallback to static data if API fails
      setCategories([
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
      ]);
    } finally {
      setLoading(false);
    }
  };

  return { categories, loading, error };
} 