type SectionHeaderProps = {
  eyebrow: string
  title: string
  description: string
}

export function SectionHeader({ eyebrow, title, description }: SectionHeaderProps) {
  return (
    <header className="section-header">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{description}</p>
    </header>
  )
}
