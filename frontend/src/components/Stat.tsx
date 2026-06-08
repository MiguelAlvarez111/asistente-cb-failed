type Props = {
  label: string;
  value: string | number;
};

export function Stat({ label, value }: Props) {
  return (
    <div className="rounded border border-line bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-ink/55">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

