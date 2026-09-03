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
import { MyEquipmentPage } from "../pages/inventory/MyEquipmentPage";
import { PlaceholderPage } from "../pages/placeholder/PlaceholderPage";
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
        <Route path="mine" element={<MyEquipmentPage />} />
        <Route
          path="movements"
          element={
            <PlaceholderPage
              description="Журнал движений будет подключён отдельным рабочим срезом без имитации складских операций."
              eyebrow="Складской журнал"
              title="Движения"
            />
          }
        />
        <Route
          path="more"
          element={
            <PlaceholderPage
              description="Служебные и административные функции появятся по мере готовности следующих этапов."
              eyebrow="Дополнительно"
              title="Ещё"
            />
          }
        />
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
