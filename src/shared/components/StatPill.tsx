type StatPillProps = {
  label: string
  value: string | number
}

export function StatPill({ label, value }: StatPillProps) {
  return (
    <span className="stat-pill">
      <strong>{value}</strong>
      <small>{label}</small>
    </span>
  )
}
