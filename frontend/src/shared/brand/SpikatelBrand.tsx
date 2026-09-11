type SpikatelBrandProps = {
  inverse?: boolean;
  size?: "default" | "compact";
  title: string;
};

export function SpikatelBrand({
  inverse = false,
  size = "default",
  title,
}: SpikatelBrandProps) {
  const className = [
    "compact-brand",
    size === "compact"
      ? "compact-brand--compact"
      : "",
    inverse
      ? "compact-brand--inverse"
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      <img
        alt="Спикател"
        className="compact-brand__logo"
        src={
          inverse
            ? "/brand/spikatel-logo-white.svg"
            : "/brand/spikatel-logo-black.svg"
        }
      />

      <strong className="compact-brand__title">
        {title}
      </strong>
    </div>
  );
}
