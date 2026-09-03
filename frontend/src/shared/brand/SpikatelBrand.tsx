type SpikatelBrandProps = {
  inverse?: boolean;
  subtitle: string;
};

export function SpikatelBrand({
  inverse = false,
  subtitle,
}: SpikatelBrandProps) {
  return (
    <div className={inverse ? "compact-brand compact-brand--inverse" : "compact-brand"}>
      <img
        alt="Спикател"
        className="compact-brand__logo"
        src={
          inverse
            ? "/brand/spikatel-logo-white.svg"
            : "/brand/spikatel-logo-black.svg"
        }
      />
      <div>
        <strong>Inventory</strong>
        <small>{subtitle}</small>
      </div>
    </div>
  );
}
