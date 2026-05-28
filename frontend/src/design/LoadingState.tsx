import { Progress } from './Progress';

type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label = '加载中' }: LoadingStateProps) {
  return (
    <div className="loading-state">
      <div style={{ width: 'min(320px, 100%)' }}>
        <strong>{label}</strong>
        <div style={{ marginTop: 12 }}>
          <Progress />
        </div>
      </div>
    </div>
  );
}
