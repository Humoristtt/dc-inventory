import {
  Button,
  Input,
  Select,
  Textarea,
  inventoryError,
  inventoryRequest,
  type StorageLocation,
  useEffect,
  useQuery,
  useQueryClient,
  useState,
  } from "../../shared/api/inventory";
import { refreshAfterLocationEdit } from "../../shared/api/inventoryCache";
import "../../features/inventory/inventory.css";
import { PageHeader,
  } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
import {
  getLocations,
  } from "react";
import {
  useMutation,
} from "../../shared/ui";

type LocationDraft = {
  code: string;
  name: string;
  location_type: "WAREHOUSE" | "DATACENTER";
  address: string;
};

const blank: LocationDraft = {
  code: "",
  name: "",
  location_type: "WAREHOUSE",
  address: "",
};

export function LocationsPage() {
  const auth = useAuthState();
  const client = useQueryClient();

  const locations = useQuery({
    queryKey: ["inventory", "locations"],
    queryFn: ({ signal }) =>
      getLocations(signal),
  });

  const [editing, setEditing] =
    useState<string | null>(null);
  const [open, setOpen] =
    useState(false);
  const [draft, setDraft] =
    useState<LocationDraft>(blank);

  const mutation = useMutation({
    mutationFn: ({
      id,
      body,
      action,
    }: {
      id?: string;
      body?: unknown;
      action?: string;
    }) =>
      inventoryRequest<StorageLocation>(
        `/api/admin/inventory/locations${
          id ? `/${id}` : ""
        }${action ? `/${action}` : ""}`,
        body ?? {},
        id && !action
          ? "PATCH"
          : "POST",
      ),

    onSuccess: async () => {
      setOpen(false);
      setEditing(null);
      setDraft(blank);

      await refreshAfterLocationEdit(
        client,
      );
    },
  });

  const canManageLocations = hasCapability(
    auth.data?.user,
    "inventory.admin",
  );
  const canManageCatalog = hasCapability(
    auth.data?.user,
    "catalog.manage",
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    if (!canManageLocations) {
      const closeTimer =
        window.setTimeout(() => {
          setOpen(false);
        }, 0);

      return () => {
        window.clearTimeout(closeTimer);
      };
    }

    const previousOverflow =
      document.body.style.overflow;

    document.body.style.overflow =
      "hidden";

    return () => {
      document.body.style.overflow =
        previousOverflow;
    };
  }, [canManageLocations, open]);

  const closeEditor = () => {
    if (mutation.isPending) {
      return;
    }

    setOpen(false);
    setEditing(null);
    mutation.reset();
  };

  const openCreate = () => {
    setEditing(null);
    setDraft(blank);
    mutation.reset();
    setOpen(true);
  };

  const openEdit = (
    location: StorageLocation,
  ) => {
    setEditing(location.id);
    setDraft({
      code: location.code,
      name: location.name,
      location_type:
        location.location_type,
      address:
        location.address ?? "",
    });
    mutation.reset();
    setOpen(true);
  };

  return (
    <main className="catalog-page">
      <PageHeader
        kicker="Склад"
        title="Места хранения"
      />

      <div className="catalog-page__body">
        {canManageLocations || canManageCatalog ? (
          <div className="warehouse-actions">
            {canManageLocations ? (
              <Button
                className="button button--dark"
                onClick={openCreate}
                type="button"
              >
                Добавить место хранения
              </Button>
            ) : null}

            {canManageCatalog ? (
              <Link
                className="button"
                to="/catalog/new"
              >
                Добавить оборудование
              </Link>
            ) : null}
          </div>
        ) : null}

        {locations.isError ? (
          <p role="alert">
            Не удалось загрузить места
            хранения.{" "}
            <Button
              onClick={() =>
                void locations.refetch()
              }
              type="button"
            >
              Повторить
            </Button>
          </p>
        ) : null}

        {locations.data?.map(
          (row) => (
            <section
              className="detail-panel"
              key={row.id}
            >
              <h2>{row.name}</h2>

              <p>
                {row.location_type ===
                "WAREHOUSE"
                  ? "Склад"
                  : "ЦОД"}{" "}
                · {row.code}
                {row.status ===
                "ARCHIVED"
                  ? " · Архив"
                  : ""}
              </p>

              {row.address ? (
                <p>{row.address}</p>
              ) : null}

              {canManageLocations ? (
                <div className="warehouse-actions">
                  <Button
                    className="button"
                    disabled={
                      mutation.isPending
                    }
                    onClick={() =>
                      openEdit(row)
                    }
                    type="button"
                  >
                    Редактировать
                  </Button>

                  <Button
                    className="button"
                    disabled={
                      mutation.isPending
                    }
                    onClick={() => {
                      mutation.reset();

                      mutation.mutate({
                        id: row.id,
                        action:
                          row.status ===
                          "ACTIVE"
                            ? "archive"
                            : "unarchive",
                      });
                    }}
                    type="button"
                  >
                    {row.status ===
                    "ACTIVE"
                      ? "Архивировать"
                      : "Вернуть из архива"}
                  </Button>
                </div>
              ) : null}
            </section>
          ),
        )}

        {mutation.isError &&
        !open ? (
          <p role="alert">
            {inventoryError(
              mutation.error,
            )}
          </p>
        ) : null}
      </div>

      {open && canManageLocations ? (
        <div
          className="location-editor-backdrop"
          onMouseDown={(event) => {
            if (
              event.target ===
              event.currentTarget
            ) {
              closeEditor();
            }
          }}
        >
          <section
            aria-labelledby="location-editor-title"
            aria-modal="true"
            className="location-editor"
            role="dialog"
          >
            <header className="location-editor__header">
              <div>
                <span className="section-kicker">
                  {editing
                    ? "Редактирование"
                    : "Новое место"}
                </span>

                <h2 id="location-editor-title">
                  {editing
                    ? "Редактировать место"
                    : "Новое место хранения"}
                </h2>
              </div>

              <Button
                aria-label="Закрыть редактор места хранения"
                autoFocus
                className="icon-button"
                data-escape-dismiss=""
                disabled={
                  mutation.isPending
                }
                onClick={closeEditor}
                type="button"
              >
                ×
              </Button>
            </header>

            <form
              className="warehouse-form location-editor__form form-surface"
              onSubmit={(event) => {
                event.preventDefault();

                const {
                  code,
                  ...fields
                } = draft;

                mutation.mutate({
                  id:
                    editing ??
                    undefined,
                  body: editing
                    ? fields
                    : {
                        ...fields,
                        code,
                      },
                });
              }}
            >
              <div className="location-editor__body">
                <fieldset
                  disabled={
                    mutation.isPending
                  }
                >
                  {!editing ? (
                    <label>
                      <span>Код</span>
                      <Input
                        autoComplete="off"
                        maxLength={64}
                        onChange={(
                          event,
                        ) =>
                          setDraft({
                            ...draft,
                            code:
                              event
                                .target
                                .value,
                          })
                        }
                        required
                        value={draft.code}
                      />
                    </label>
                  ) : null}

                  <label>
                    <span>Название</span>
                    <Input
                      autoComplete="off"
                      maxLength={255}
                      onChange={(
                        event,
                      ) =>
                        setDraft({
                          ...draft,
                          name:
                            event
                              .target
                              .value,
                        })
                      }
                      required
                      value={draft.name}
                    />
                  </label>

                  <label>
                    <span>Тип</span>
                    <Select
                      onChange={(
                        event,
                      ) =>
                        setDraft({
                          ...draft,
                          location_type:
                            event
                              .target
                              .value as LocationDraft["location_type"],
                        })
                      }
                      value={
                        draft.location_type
                      }
                    >
                      <option value="WAREHOUSE">
                        Склад
                      </option>
                      <option value="DATACENTER">
                        ЦОД
                      </option>
                    </Select>
                  </label>

                  <label className="location-editor__wide">
                    <span>Адрес</span>
                    <Textarea
                      autoComplete="off"
                      maxLength={2000}
                      onChange={(
                        event,
                      ) =>
                        setDraft({
                          ...draft,
                          address:
                            event
                              .target
                              .value,
                        })
                      }
                      value={
                        draft.address
                      }
                    />
                  </label>
                </fieldset>

                {mutation.isError ? (
                  <p
                    className="location-editor__error"
                    role="alert"
                  >
                    {inventoryError(
                      mutation.error,
                    )}
                  </p>
                ) : null}
              </div>

              <footer className="location-editor__footer">
                <Button
                  className="button button--ghost"
                  disabled={
                    mutation.isPending
                  }
                  onClick={
                    closeEditor
                  }
                  type="button"
                >
                  Отмена
                </Button>

                <Button
                  className="button button--accent"
                  disabled={
                    mutation.isPending
                  }
                  type="submit"
                >
                  {mutation.isPending
                    ? "Сохраняем…"
                    : "Сохранить"}
                </Button>
              </footer>
            </form>
          </section>
        </div>
      ) : null}
    </main>
  );
}
