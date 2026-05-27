import React, { useEffect, useRef, useState, useCallback } from 'react';
import ForceGraph2D, { ForceGraphMethods } from 'react-force-graph-2d';
import { KnowledgeGraphData, GraphNode } from '../api/knowledge';

interface KnowledgeGraphProps {
  data: KnowledgeGraphData;
  onNodeClick?: (node: GraphNode) => void;
  width: number;
  height: number;
  isDark?: boolean;
}

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ data, onNodeClick, width, height, isDark = true }) => {
  const graphRef = useRef<any>(null);
  const [highlightNodes, setHighlightNodes] = useState(new Set<string>());
  const [highlightLinks, setHighlightLinks] = useState(new Set<any>());
  const [hoverNode, setHoverNode] = useState<string | null>(null);

  // Update graph data when props change
  useEffect(() => {
    if (graphRef.current) {
        // Apply force settings for better spacing
        graphRef.current.d3Force('charge').strength(-120);
        graphRef.current.d3Force('link').distance(70);
    }
  }, [data]);

  const handleNodeHover = (node: any | null) => {
    setHoverNode(node ? (node.id as string) : null);
    
    const newHighlightNodes = new Set<string>();
    const newHighlightLinks = new Set<any>();

    if (node) {
      newHighlightNodes.add(node.id as string);
      // Find neighbors
      (data.links || []).forEach((link: any) => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
        const targetId = typeof link.target === 'object' ? link.target.id : link.target;
        
        if (sourceId === node.id) {
            newHighlightNodes.add(targetId);
            newHighlightLinks.add(link);
        } else if (targetId === node.id) {
            newHighlightNodes.add(sourceId);
            newHighlightLinks.add(link);
        }
      });
    }

    setHighlightNodes(newHighlightNodes);
    setHighlightLinks(newHighlightLinks);
  };

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const isHover = hoverNode === node.id;
    const isNeighbor = highlightNodes.has(node.id);
    const isDimmed = hoverNode && !isHover && !isNeighbor;

    // Node Types
    // Group 1: Documents
    // Group 2: Concepts
    // Group 3: Keywords
    
    let color = isDark ? '#00f3ff' : '#0284c7'; // Default
    if (node.group === 1) color = isDark ? '#00f3ff' : '#0ea5e9'; // Documents (Cyan / Sky)
    if (node.group === 2) color = isDark ? '#bc13fe' : '#7c3aed'; // Concepts (Purple / Violet)
    if (node.group === 3) color = isDark ? '#ffffff' : '#4b5563'; // Keywords (White / Gray)

    if (isDimmed) {
        ctx.globalAlpha = 0.2;
    } else {
        ctx.globalAlpha = 1;
    }

    const radius = Math.max(3, Math.sqrt(node.val || 1) * 3);
    const x = node.x;
    const y = node.y;

    // Draw Glow
    if (!isDimmed) {
        ctx.shadowColor = color;
        ctx.shadowBlur = isHover ? 20 : (isDark ? 10 : 5);
    } else {
        ctx.shadowBlur = 0;
    }

    ctx.fillStyle = color;

    if (node.group === 1) {
        // Document: Square/Diamond
        ctx.beginPath();
        const s = radius * 1.5;
        ctx.rect(x - s/2, y - s/2, s, s);
        ctx.fill();
        
        // Inner detail
        ctx.fillStyle = isDark ? '#000' : '#fff';
        ctx.beginPath();
        ctx.rect(x - s/4, y - s/4, s/2, s/2);
        ctx.fill();
    } else {
        // Concept: Circle
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, 2 * Math.PI, false);
        ctx.fill();
        
        // Ring for hover
        if (isHover) {
            ctx.beginPath();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1;
            ctx.arc(x, y, radius * 1.5, 0, 2 * Math.PI, false);
            ctx.stroke();
        }
    }

    ctx.shadowBlur = 0; // Reset shadow for text

    // Draw Label
    const showLabel = isHover || isNeighbor || globalScale > 1.2 || node.val > 10;
    if (showLabel) {
        const label = node.name;
        const fontSize = 12 / globalScale;
        ctx.font = `${fontSize}px 'Rajdhani', sans-serif`;
        const textWidth = ctx.measureText(label).width;
        
        // Label Background
        ctx.fillStyle = isDark ? 'rgba(0, 0, 0, 0.8)' : 'rgba(255, 255, 255, 0.8)';
        ctx.fillRect(x - textWidth / 2 - 2, y + radius + 2, textWidth + 4, fontSize + 4);
        
        // Label Text
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = isDimmed ? (isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.5)') : (isDark ? '#fff' : '#000');
        ctx.fillText(label, x, y + radius + 4);
    }
  }, [hoverNode, highlightNodes, isDark]);

  const paintLink = useCallback((link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    let isHighlight = false;
    if (highlightLinks.has(link)) {
        isHighlight = true;
    }

    const isDimmed = hoverNode && !isHighlight;
    if (isDimmed) return;

    const start = link.source;
    const end = link.target;

    if (typeof start !== 'object' || typeof end !== 'object') return;

    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    
    // Sci-Fi Link Style
    ctx.lineWidth = isHighlight ? 2 / globalScale : 0.5 / globalScale;
    
    if (isHighlight) {
        ctx.strokeStyle = isDark ? '#fff' : '#0ea5e9';
        ctx.shadowColor = isDark ? '#00f3ff' : '#0ea5e9';
        ctx.shadowBlur = 5;
    } else {
        ctx.strokeStyle = isDark ? 'rgba(0, 243, 255, 0.2)' : 'rgba(148, 163, 184, 0.4)';
        ctx.shadowBlur = 0;
    }
    
    ctx.stroke();
    ctx.shadowBlur = 0; // Reset
  }, [hoverNode, highlightLinks, isDark]);

  return (
    <div style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
      <ForceGraph2D
        ref={graphRef}
        width={width}
        height={height}
        graphData={data}
        nodeLabel="name"
        backgroundColor="rgba(0,0,0,0)"
        onNodeHover={handleNodeHover}
        onNodeClick={(node) => onNodeClick && onNodeClick(node as any)}
        nodeCanvasObject={paintNode}
        linkCanvasObject={paintLink}
        cooldownTicks={100}
        d3VelocityDecay={0.1}
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}
      />
    </div>
  );
};

export default KnowledgeGraph;
