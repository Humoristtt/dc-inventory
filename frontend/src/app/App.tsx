import {
  lazy,
  useEffect,
} from "react";

import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import { ApplicationShell } from "./ApplicationShell";
import {
  loadAdminUsersPage,
  loadCatalogLandingPage,
  loadCategoryPage,
  loadItemDetailPage,
  loadItemFormPage,
  loadLocationsPage,
  loadMorePage,
  loadMovementsPage,
  preloadApplicationRoutes,
} from "./routeModules";
import "../features/catalog/catalog.css";

const CategoryPage = lazy(loadCategoryPage);
const CatalogLandingPage = lazy(loadCatalogLandingPage);
const ItemDetailPage = lazy(loadItemDetailPage);
const ItemFormPage = lazy(loadItemFormPage);
const MovementsPage = lazy(loadMovementsPage);
const LocationsPage = lazy(loadLocationsPage);
const MorePage = lazy(loadMorePage);
const AdminUsersPage = lazy(loadAdminUsersPage);

export function ApplicationRoutes() {
  return (
    <Routes>
      <Route element={<ApplicationShell />}>
        <Route index element={<Navigate replace to="/catalog" />} />
        <Route path="catalog" element={<CatalogLandingPage />} />
        <Route path="catalog/new" element={<ItemFormPage />} />
        <Route path="catalog/items/:itemId/edit" element={<ItemFormPage />} />
        <Route path="catalog/items/:itemId" element={<ItemDetailPage />} />
        <Route path="catalog/:categoryKey" element={<CategoryPage />} />
        <Route path="movements" element={<MovementsPage />} />
        <Route path="more" element={<MorePage />} />
        <Route path="more/locations" element={<LocationsPage />} />
        <Route path="more/users" element={<AdminUsersPage />} />
        <Route path="*" element={<Navigate replace to="/catalog" />} />
      </Route>
    </Routes>
  );
}

export function App() {
  useEffect(() => {
    // Give the first visible page/API requests a short head start, then warm
    // the fixed and small MVP route set. These dynamic imports stay outside
    // the initial bundle and are browser-cached for subsequent navigation.
    const timer = window.setTimeout(() => {
      void preloadApplicationRoutes();
    }, 100);

    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <BrowserRouter>
      <ApplicationRoutes />
    </BrowserRouter>
  );
}
