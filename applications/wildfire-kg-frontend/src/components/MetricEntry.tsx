import { useState } from 'react';

interface MetricData {
  plotId: string;
  pointDensity: number;
  canopyHeight: number;
  groundElevation: number;
  notes: string;
}

export default function MetricEntry() {
  const [metrics, setMetrics] = useState<MetricData>({
    plotId: '',
    pointDensity: 0,
    canopyHeight: 0,
    groundElevation: 0,
    notes: ''
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // TODO: Replace with your API endpoint
      const response = await fetch('/api/metrics', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(metrics),
      });

      if (!response.ok) {
        throw new Error('Failed to save metrics');
      }

      alert('Metrics saved successfully!');
      // Reset form
      setMetrics({
        plotId: '',
        pointDensity: 0,
        canopyHeight: 0,
        groundElevation: 0,
        notes: ''
      });
    } catch (error) {
      console.error('Save error:', error);
      alert('Failed to save metrics. Please try again.');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">Plot ID:</label>
          <input
            type="text"
            value={metrics.plotId}
            onChange={(e) => setMetrics({...metrics, plotId: e.target.value})}
            className="w-full p-2 border rounded-md"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Point Density (points/m²):</label>
          <input
            type="number"
            value={metrics.pointDensity}
            onChange={(e) => setMetrics({...metrics, pointDensity: Number(e.target.value)})}
            className="w-full p-2 border rounded-md"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Canopy Height (m):</label>
          <input
            type="number"
            value={metrics.canopyHeight}
            onChange={(e) => setMetrics({...metrics, canopyHeight: Number(e.target.value)})}
            className="w-full p-2 border rounded-md"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Ground Elevation (m):</label>
          <input
            type="number"
            value={metrics.groundElevation}
            onChange={(e) => setMetrics({...metrics, groundElevation: Number(e.target.value)})}
            className="w-full p-2 border rounded-md"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Notes:</label>
          <textarea
            value={metrics.notes}
            onChange={(e) => setMetrics({...metrics, notes: e.target.value})}
            className="w-full p-2 border rounded-md"
            rows={4}
          />
        </div>

        <button
          type="submit"
          className="w-full bg-blue-500 text-white py-2 px-4 rounded-md hover:bg-blue-600 transition-colors"
        >
          Save Metrics
        </button>
      </div>
    </form>
  );
} 