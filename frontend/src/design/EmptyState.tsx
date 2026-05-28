type EmptyStateProps = {
  title?: string;
  description?: string;
};

export function EmptyState({ title = '暂无数据', description = '完成数据同步后这里会自动更新。' }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </div>
  );
}
