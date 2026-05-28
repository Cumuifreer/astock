import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Candidate } from '../../types';
import { getAnalysisReports } from '../../api/strategy';
import { Badge } from '../../design/Badge';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { useBootstrap } from '../../hooks/useBootstrap';
import { CandidateTable } from './CandidateTable';
import { CandidateEvidencePanel } from './CandidateEvidencePanel';

export function ResultsPage() {
  const bootstrap = useBootstrap();
  const reports = useQuery({ queryKey: ['analysis-reports'], queryFn: getAnalysisReports });
  const candidates = bootstrap.data?.candidates?.rows || [];
  const [selected, setSelected] = useState<Candidate | null>(candidates[0] || null);

  if (bootstrap.isLoading) return <LoadingState label="读取候选结果" />;

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>候选结果</h2>
            <p>支持列选择、多列排序、固定代码列和保存视图的表格框架已经就位。</p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{candidates.length} 个候选</Badge>
            <Badge>{reports.data?.groups?.length || 0} 组报告</Badge>
          </div>
        </div>
        {candidates.length ? (
          <CandidateTable candidates={candidates} onSelect={setSelected} />
        ) : (
          <EmptyState title="暂无候选" description="运行策略后，这里会展示候选表和结构化证据。" />
        )}
      </section>
      <CandidateEvidencePanel candidate={selected || candidates[0] || null} />
    </div>
  );
}
