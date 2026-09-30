export const loadCatalogLandingPage = () =>
  import("../pages/catalog/CatalogLandingPage").then(
    (module) => ({ default: module.CatalogLandingPage }),
  );

export const loadCategoryPage = () =>
  import("../pages/catalog/CategoryPage").then(
    (module) => ({ default: module.CategoryPage }),
  );

export const loadItemDetailPage = () =>
  import("../pages/catalog/ItemDetailPage").then(
    (module) => ({ default: module.ItemDetailPage }),
  );

export const loadItemFormPage = () =>
  import("../pages/catalog/ItemFormPage").then(
    (module) => ({ default: module.ItemFormPage }),
  );

export const loadMovementsPage = () =>
  import("../pages/inventory/MovementsPage").then(
    (module) => ({ default: module.MovementsPage }),
  );

export const loadLocationsPage = () =>
  import("../pages/inventory/LocationsPage").then(
    (module) => ({ default: module.LocationsPage }),
  );

export const loadMorePage = () =>
  import("../pages/more/MorePage").then(
    (module) => ({ default: module.MorePage }),
  );

export const loadAdminUsersPage = () =>
  import("../pages/admin/AdminUsersPage").then(
    (module) => ({ default: module.AdminUsersPage }),
  );

export const loadProcurementListPage = () =>
  import("../pages/procurement/ProcurementListPage").then(
    (module) => ({ default: module.ProcurementListPage }),
  );

export const loadProcurementDetailPage = () =>
  import("../pages/procurement/ProcurementDetailPage").then(
    (module) => ({ default: module.ProcurementDetailPage }),
  );

export const loadProcurementCreatePage = () =>
  import("../pages/procurement/ProcurementCreatePage").then(
    (module) => ({ default: module.ProcurementCreatePage }),
  );

