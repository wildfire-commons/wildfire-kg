export interface BucketCategory {
  id: string;
  name: string;
  description: string;
  icon: 'folder' | 'chart' | 'cloud';
  itemCount: number;
  lastUpdated: Date;
} 