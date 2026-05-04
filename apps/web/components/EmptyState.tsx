type EmptyStateProps = {
  title: string;
  description: string;
};

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <section
      className="mt-10 border border-dashed border-rule bg-paper p-8 shadow-lift transition-colors duration-200"
      aria-label="Empty state"
    >
      <div className="max-w-measure border-l-2 border-accent pl-5">
        <h2 className="font-serif text-xl font-medium tracking-tight text-ink">{title}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted">{description}</p>
      </div>
    </section>
  );
}
