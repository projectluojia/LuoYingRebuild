import { useState, useEffect } from 'react';
import { api } from '../api/client';

interface WorkspaceNode {
  name: string;
  path: string;
  type: 'directory' | 'file';
  children?: WorkspaceNode[];
  size?: number;
  modified_at?: number | null;
  url?: string;
}

interface TreeNodeProps {
  node: WorkspaceNode;
  depth: number;
}

function TreeNode({ node, depth }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(false);

  const handleClick = () => {
    if (node.type === 'directory') {
      setExpanded((v) => !v);
    } else if (node.url) {
      window.open(node.url, '_blank');
    }
  };

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (node.url) {
      const a = document.createElement('a');
      a.href = node.url;
      a.download = node.name;
      a.click();
    }
  };

  const indent = depth * 16;

  return (
    <div>
      <div
        className="flex items-center gap-1.5 py-1 px-2 rounded-lg cursor-pointer hover:bg-blue-50/60 transition-colors group"
        style={{ paddingLeft: indent + 8 }}
        onClick={handleClick}
        title={node.path}
      >
        {/* Indent guides */}
        {Array.from({ length: depth }).map((_, i) => (
          <div
            key={i}
            className="absolute w-px bg-blue-200/50"
            style={{ left: indent - (depth - i - 1) * 16 + 16, height: '100%' }}
          />
        ))}

        {/* Expand/collapse icon */}
        <span
          className={`w-4 h-4 flex items-center justify-center text-xs transition-transform ${
            node.type === 'directory' ? 'opacity-100' : 'opacity-0'
          }`}
          style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          {node.type === 'directory' ? '▶' : '📄'}
        </span>

        {/* Icon */}
        <span className="text-sm">
          {node.type === 'directory'
            ? expanded
              ? '📂'
              : '📁'
            : getFileIcon(node.name)}
        </span>

        {/* Name */}
        <span className="text-sm flex-1 truncate" style={{ color: 'var(--color-blue-deep)' }}>
          {node.name}
        </span>

        {/* Size */}
        {node.size != null && node.type === 'file' && (
          <span className="text-xs opacity-50">{formatSize(node.size)}</span>
        )}

        {/* Download button for files */}
        {node.type === 'file' && node.url && (
          <button
            onClick={handleDownload}
            className="opacity-0 group-hover:opacity-100 px-1.5 py-0.5 rounded text-xs transition-opacity"
            style={{
              background: 'rgba(74, 169, 255, 0.15)',
              color: 'var(--color-blue-deep)',
            }}
            title="下载"
          >
            ↓
          </button>
        )}
      </div>

      {/* Children */}
      {node.type === 'directory' && expanded && node.children && (
        <div>
          {node.children.map((child, i) => (
            <TreeNode key={`${child.path}-${i}`} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function getFileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  const icons: Record<string, string> = {
    // Images
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', webp: '🖼️', svg: '🖼️',
    // Code
    ts: '📜', tsx: '📜', js: '📜', jsx: '📜', py: '🐍', java: '☕',
    // Config
    json: '📋', yaml: '📋', yml: '📋', toml: '📋', env: '🔐',
    // Docs
    md: '📝', txt: '📝', pdf: '📑', doc: '📑', docx: '📑',
    // Data
    csv: '📊', xlsx: '📊',
    // Archives
    zip: '📦', tar: '📦', gz: '📦', rar: '📦',
    // Audio
    mp3: '🎵', wav: '🎵', flac: '🎵',
    // Video
    mp4: '🎬', mkv: '🎬', avi: '🎬',
    // 3D
    glb: '🎮', gltf: '🎮', obj: '🎮',
  };
  return icons[ext] ?? '📄';
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}K`;
  return `${(bytes / 1024 / 1024).toFixed(1)}M`;
}

export function WorkspaceTree() {
  const [tree, setTree] = useState<WorkspaceNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.getWorkspaceTree()
      .then((res) => setTree(res.root))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--color-blue-light)', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-4 text-xs" style={{ color: '#e53e3e' }}>
        <div className="mb-2">⚠️ {error}</div>
        <button
          onClick={() => setRefreshKey((k) => k + 1)}
          className="px-3 py-1 rounded text-xs transition-opacity hover:opacity-80"
          style={{ background: 'rgba(229, 62, 62, 0.1)', color: '#e53e3e' }}
        >
          重试
        </button>
      </div>
    );
  }

  if (!tree) {
    return (
      <div className="text-center py-4 text-xs" style={{ color: 'var(--color-blue-deep)', opacity: 0.6 }}>
        工作区为空
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {/* Root label + refresh */}
      <div className="flex items-center justify-between px-2 py-1 mb-1">
        <span className="text-xs font-semibold uppercase tracking-wider opacity-50" style={{ color: 'var(--color-blue-deep)' }}>
          {tree.name}
        </span>
        <button
          onClick={() => setRefreshKey((k) => k + 1)}
          className="w-5 h-5 rounded flex items-center justify-center text-xs opacity-40 hover:opacity-80 transition-opacity"
          title="刷新"
        >
          ↻
        </button>
      </div>

      {/* Children */}
      {tree.children?.map((child: WorkspaceNode, i: number) => (
        <TreeNode key={`${child.path}-${i}`} node={child} depth={0} />
      ))}
    </div>
  );
}
