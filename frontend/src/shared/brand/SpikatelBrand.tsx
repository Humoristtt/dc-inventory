type SpikatelBrandProps = {
  inverse?: boolean;
  title: string;
};

export function SpikatelBrand({
  inverse = false,
  title,
}: SpikatelBrandProps) {
  return (
    <div
      className={
        inverse
          ? "compact-brand compact-brand--inverse"
          : "compact-brand"
      }
    >
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
