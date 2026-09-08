import { lazy } from "react";

import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import { ApplicationShell } from "./ApplicationShell";

const CategoryPage = lazy(() => import("../pages/catalog/CategoryPage").then((module) => ({ default: module.CategoryPage })));
const CatalogLandingPage = lazy(() => import("../pages/catalog/CatalogLandingPage").then((module) => ({ default: module.CatalogLandingPage })));
const ItemDetailPage = lazy(() => import("../pages/catalog/ItemDetailPage").then((module) => ({ default: module.ItemDetailPage })));
const ItemFormPage = lazy(() => import("../pages/catalog/ItemFormPage").then((module) => ({ default: module.ItemFormPage })));
const MovementsPage = lazy(() => import("../pages/inventory/MovementsPage").then((module) => ({ default: module.MovementsPage })));
const LocationsPage = lazy(() => import("../pages/inventory/LocationsPage").then((module) => ({ default: module.LocationsPage })));


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
        <Route path="more" element={<LocationsPage />} />
        <Route path="*" element={<Navigate replace to="/catalog" />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <ApplicationRoutes />
    </BrowserRouter>
  );
}
