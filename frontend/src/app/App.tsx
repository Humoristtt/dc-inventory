import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import { ApplicationShell } from "./ApplicationShell";
import {
  APP_DEFAULT_PATH,
  APP_ROUTES,
} from "./appRoutes";
import "../features/catalog/catalog.css";
import "../features/catalog/catalog-responsive.css";
import "../features/inventory/inventory-responsive.css";
import "../features/admin/access-admin-responsive.css";
import "../features/procurement/procurement-responsive.css";

export function ApplicationRoutes() {
  return (
    <Routes>
      <Route element={<ApplicationShell />}>
        <Route
          index
          element={
            <Navigate
              replace
              to={APP_DEFAULT_PATH}
            />
          }
        />

        {APP_ROUTES.map((definition) => {
          const Page = definition.component;

          return (
            <Route
              element={<Page />}
              key={definition.id}
              path={definition.path.slice(1)}
            />
          );
        })}

        <Route
          path="*"
          element={
            <Navigate
              replace
              to={APP_DEFAULT_PATH}
            />
          }
        />
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
