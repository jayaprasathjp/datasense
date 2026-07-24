import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid
} from 'recharts';

/**
 * A smart component that automatically identifies axes and renders a Recharts BarChart
 * from a raw array of tabular objects.
 */
export default function AutoChart({ data }) {
  if (!data || data.length === 0) return null;

  // 1. Heuristics: Analyze the first row to determine X and Y axes
  const firstRow = data[0];
  let xKey = null;
  let yKey = null;

  for (const [key, value] of Object.entries(firstRow)) {
    if (typeof value === 'string' && !xKey) {
      xKey = key;
    } else if (typeof value === 'number' && !yKey) {
      yKey = key;
    }
  }

  // Fallbacks if heuristics fail
  if (!xKey) {
    // If no string column, just pick the first key as X
    xKey = Object.keys(firstRow)[0];
  }
  if (!yKey) {
    // Pick the first numeric key we can find, or the second key
    const numKey = Object.keys(firstRow).find(k => typeof firstRow[k] === 'number' && k !== xKey);
    yKey = numKey || Object.keys(firstRow)[1];
  }

  if (!xKey || !yKey) return null; // Can't plot

  // Cap data to top 20 for charting to avoid over-rendering
  const plotData = data.slice(0, 20);

  // Modern aesthetic colors matching the app's dark theme
  const barColors = ['#f84824', '#ff7b5f', '#ff9a85', '#ffb8a8', '#ffd8d1'];

  return (
    <div className="auto-chart-container" style={{ width: '100%', height: 300, marginBottom: '2rem' }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={plotData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
          <XAxis 
            dataKey={xKey} 
            stroke="#666" 
            tick={{ fill: '#888', fontSize: 12 }} 
            tickLine={false}
            axisLine={false}
          />
          <YAxis 
            stroke="#666" 
            tick={{ fill: '#888', fontSize: 12 }} 
            tickLine={false}
            axisLine={false}
            tickFormatter={(val) => {
              if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
              if (val >= 1000) return `${(val / 1000).toFixed(0)}K`;
              return val;
            }}
          />
          <Tooltip 
            cursor={{ fill: 'rgba(255,255,255,0.05)' }}
            contentStyle={{ backgroundColor: '#111', borderColor: '#333', borderRadius: '4px', color: '#fff' }}
            itemStyle={{ color: '#f84824' }}
            formatter={(value) => new Intl.NumberFormat().format(value)}
            labelStyle={{ color: '#888', marginBottom: '4px' }}
          />
          <Bar dataKey={yKey} radius={[4, 4, 0, 0]} maxBarSize={60}>
            {plotData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={barColors[index % barColors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
