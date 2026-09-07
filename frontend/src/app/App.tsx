import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import { CategoryPage } from "../pages/catalog/CategoryPage";
import { CatalogLandingPage } from "../pages/catalog/CatalogLandingPage";
import { ItemDetailPage } from "../pages/catalog/ItemDetailPage";
import { ItemFormPage } from "../pages/catalog/ItemFormPage";
import { MovementsPage } from "../pages/inventory/MovementsPage";
import { LocationsPage } from "../pages/inventory/LocationsPage";
import { ApplicationShell } from "./ApplicationShell";

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
