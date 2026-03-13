import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, FileJson, Database } from 'lucide-react';
import { Mermaid } from './Mermaid'; // Assuming we'll extract Mermaid too
import { CodeBlock } from './CodeBlock'; // Assuming we'll extract CodeBlock too

interface ArtifactViewerProps {
  artifacts: Record<string, string>;
  selectedFile: string | null;
  onSelectFile: (filename: string) => void;
  filteredArtifacts: string[];
  t: (key: string) => string;
}

export const ArtifactViewer: React.FC<ArtifactViewerProps> = ({
  artifacts,
  selectedFile,
  onSelectFile,
  filteredArtifacts,
  t
}) => {
  const getFileIcon = (filename: string) => {
    if (filename.endsWith('.sql')) return <Database size={16} className="text-purple-500" />;
    if (filename.endsWith('.yaml') || filename.endsWith('.json')) return <FileJson size={16} className="text-yellow-500" />;
    return <FileText size={16} className="text-blue-500" />;
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-wrap gap-2 mb-6">
        {filteredArtifacts.map((filename) => (
          <button
            key={filename}
            onClick={() => onSelectFile(filename)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs transition-all ${
              selectedFile === filename
                ? 'bg-indigo-50 border-indigo-200 text-indigo-700 shadow-sm font-bold'
                : 'bg-white border-gray-100 text-gray-500 hover:border-gray-200 hover:bg-gray-50'
            }`}
          >
            {getFileIcon(filename)}
            {filename}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto bg-white rounded-2xl border border-gray-100 shadow-sm p-6 sm:p-10 min-h-[500px]">
        {selectedFile ? (
          <div className="prose prose-sm prose-slate max-w-none prose-headings:text-gray-800 prose-headings:font-black prose-a:text-indigo-600 prose-strong:text-gray-900 prose-code:text-indigo-600 prose-pre:bg-transparent prose-pre:p-0">
            <ReactMarkdown 
              remarkPlugins={[remarkGfm]}
              components={{
                code: CodeBlock
              }}
            >
              {artifacts[selectedFile]}
            </ReactMarkdown>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-4 opacity-60 py-20">
             <div className="p-6 bg-gray-50 rounded-full">
                <FileText size={48} strokeWidth={1} />
             </div>
             <p className="text-sm font-medium">{t('projectDetail.selectFileToPreview')}</p>
          </div>
        )}
      </div>
    </div>
  );
};
