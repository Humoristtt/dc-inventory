import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  type MouseEvent,
  type ReactNode,
  useEffect,
} from "react";

import {
  getAccessState,
  requestAccess,
  type AccessState,
} from "../../shared/api/access";
import {
  ApiRequestError,
  authenticateWithTelegram,
  getAuthState,
  type AuthState,
  type SupportContact,
} from "../../shared/api/auth";
import {
  getTelegramInitData,
  openTelegramContact,
  prepareTelegramWebApp,
} from "../../shared/telegram/webApp";
import "./access-gate.css";

const authQueryKey = ["auth", "state"] as const;
const accessQueryKey = ["access", "me"] as const;

class TelegramContextRequiredError extends Error {
  constructor() {
    super("Telegram context required");
    this.name = "TelegramContextRequiredError";
  }
}

async function resolveAuthState(signal?: AbortSignal): Promise<AuthState> {
  try {
    return await getAuthState(signal);
  } catch (error) {
    if (!(error instanceof ApiRequestError) || error.status !== 401) {
      throw error;
    }
  }

  const initData = getTelegramInitData();
  if (initData === "") {
    throw new TelegramContextRequiredError();
  }
  return authenticateWithTelegram(initData, signal);
}

type TelegramAccessGateProps = {
  children: ReactNode;
};

type AccessScreenProps = {
  eyebrow: string;
  title: string;
  children: ReactNode;
  support?: SupportContact;
  action?: ReactNode;
};

function SupportLink({ support }: { support: SupportContact }) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (openTelegramContact(support.url)) {
      event.preventDefault();
    }
  };

  return (
    <a
      className="access-gate__support"
      href={support.url}
      onClick={handleClick}
      rel="noreferrer"
      target="_blank"
    >
      @{support.username}
    </a>
  );
}

function AccessScreen({
  eyebrow,
  title,
  children,
  support,
  action,
}: AccessScreenProps) {
  return (
    <main className="access-gate">
      <div className="access-gate__glow" aria-hidden="true" />
      <section className="access-gate__card">
        <span className="access-gate__eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <div className="access-gate__body">{children}</div>
        {support === undefined ? null : (
          <div className="access-gate__contact">
            <span>Контакт администратора</span>
            <SupportLink support={support} />
          </div>
        )}
        {action === undefined ? null : (
          <div className="access-gate__action">{action}</div>
        )}
      </section>
    </main>
  );
}

function PendingAccessScreen({ support }: { support: SupportContact }) {
  return (
    <AccessScreen
      eyebrow="Запрос доступа"
      title="Запрос отправлен"
      support={support}
    >
      <p>
        Ваш запрос на вход находится на рассмотрении. Как только
        администратор разрешит доступ, бот пришлёт отдельное сообщение.
      </p>
      <p>
        Если оборудование нужно получить срочно, свяжитесь с
        администратором напрямую.
      </p>
    </AccessScreen>
  );
}

function RequestAccessScreen({
  support,
  onRequest,
  pending,
  failed,
}: {
  support: SupportContact;
  onRequest: () => void;
  pending: boolean;
  failed: boolean;
}) {
  return (
    <AccessScreen
      eyebrow="Spikatel Inventory"
      title="Нужен доступ"
      support={support}
      action={
        <button
          className="access-gate__button"
          disabled={pending}
          onClick={onRequest}
          type="button"
        >
          {pending ? "Отправляем запрос…" : "ОК, запросить доступ"}
        </button>
      }
    >
      <p>
        Это внутреннее приложение для учёта оборудования ЦОД.
        Доступ новым пользователям подтверждает администратор.
      </p>
      <p>
        По вопросам доступа можно написать администратору в Telegram —
        контакт ниже кликабельный.
      </p>
      {failed ? (
        <p className="access-gate__error">
          Не удалось отправить запрос. Попробуйте ещё раз.
        </p>
      ) : null}
    </AccessScreen>
  );
}

function RejectedAccessScreen({
  support,
  onRequest,
  pending,
  failed,
}: {
  support: SupportContact;
  onRequest: () => void;
  pending: boolean;
  failed: boolean;
}) {
  return (
    <AccessScreen
      eyebrow="Доступ"
      title="Запрос отклонён"
      support={support}
      action={
        <button
          className="access-gate__button"
          disabled={pending}
          onClick={onRequest}
          type="button"
        >
          {pending ? "Отправляем запрос…" : "Запросить доступ снова"}
        </button>
      }
    >
      <p>
        Предыдущий запрос отклонён. Если доступ всё ещё нужен,
        можно отправить новый запрос или связаться с администратором.
      </p>
      {failed ? (
        <p className="access-gate__error">
          Не удалось отправить новый запрос. Попробуйте ещё раз.
        </p>
      ) : null}
    </AccessScreen>
  );
}

function BlockedAccessScreen({ support }: { support: SupportContact }) {
  return (
    <AccessScreen
      eyebrow="Доступ"
      title="Доступ ограничен"
      support={support}
    >
      <p>
        Вход для этой учётной записи отключён. По всем вопросам
        обратитесь к администратору.
      </p>
    </AccessScreen>
  );
}

function LoadingScreen() {
  return (
    <AccessScreen eyebrow="Spikatel Inventory" title="Проверяем доступ">
      <p>Подтверждаем Telegram-сессию и состояние учётной записи…</p>
    </AccessScreen>
  );
}

function ErrorScreen({
  telegramRequired,
  retry,
}: {
  telegramRequired: boolean;
  retry: () => void;
}) {
  if (telegramRequired) {
    return (
      <AccessScreen
        eyebrow="Spikatel Inventory"
        title="Откройте приложение через Telegram"
      >
        <p>
          Для безопасного входа требуется запуск через кнопку
          «Открыть приложение» в нашем Telegram-боте.
        </p>
      </AccessScreen>
    );
  }

  return (
    <AccessScreen
      eyebrow="Spikatel Inventory"
      title="Не удалось проверить доступ"
      action={
        <button className="access-gate__button" onClick={retry} type="button">
          Повторить
        </button>
      }
    >
      <p>Проверьте соединение и попробуйте ещё раз.</p>
    </AccessScreen>
  );
}

export function TelegramAccessGate({ children }: TelegramAccessGateProps) {
  const queryClient = useQueryClient();

  useEffect(() => {
    prepareTelegramWebApp();
  }, []);

  const authQuery = useQuery({
    queryKey: authQueryKey,
    queryFn: ({ signal }) => resolveAuthState(signal),
    retry: false,
    staleTime: 60_000,
  });

  const authState = authQuery.data;
  const accessQuery = useQuery({
    queryKey: accessQueryKey,
    queryFn: ({ signal }) => getAccessState(signal),
    enabled: authState?.user.access_status === "PENDING",
    refetchInterval: (query) =>
      (
        query.state.data?.access_status
        ?? authState?.user.access_status
      ) === "PENDING"
        ? 15_000
        : false,
    retry: false,
  });

  const observedAccessStatus = accessQuery.data?.access_status;

  useEffect(() => {
    if (observedAccessStatus === undefined) {
      return;
    }

    queryClient.setQueryData<AuthState>(authQueryKey, (current) => {
      if (
        current === undefined
        || current.user.access_status === observedAccessStatus
      ) {
        return current;
      }

      return {
        ...current,
        user: {
          ...current.user,
          access_status: observedAccessStatus,
        },
      };
    });
  }, [observedAccessStatus, queryClient]);

  const requestMutation = useMutation({
    mutationFn: requestAccess,
    onSuccess: (state: AccessState) => {
      queryClient.setQueryData(accessQueryKey, state);
    },
  });

  if (authQuery.isPending) {
    return <LoadingScreen />;
  }

  if (authQuery.isError) {
    return (
      <ErrorScreen
        retry={() => {
          void authQuery.refetch();
        }}
        telegramRequired={authQuery.error instanceof TelegramContextRequiredError}
      />
    );
  }

  if (authState === undefined) {
    return <LoadingScreen />;
  }

  const effectiveAccessStatus =
    accessQuery.data?.access_status ?? authState.user.access_status;

  if (effectiveAccessStatus === "APPROVED") {
    return children;
  }

  if (effectiveAccessStatus === "REJECTED") {
    return (
      <RejectedAccessScreen
        onRequest={() => requestMutation.mutate()}
        failed={requestMutation.isError}
        pending={requestMutation.isPending}
        support={authState.support}
      />
    );
  }

  if (effectiveAccessStatus === "BLOCKED") {
    return <BlockedAccessScreen support={authState.support} />;
  }

  if (accessQuery.isPending) {
    return <LoadingScreen />;
  }

  if (accessQuery.isError) {
    return (
      <ErrorScreen
        retry={() => {
          void accessQuery.refetch();
        }}
        telegramRequired={false}
      />
    );
  }

  if (accessQuery.data.request !== null) {
    return <PendingAccessScreen support={authState.support} />;
  }

  return (
    <RequestAccessScreen
      onRequest={() => requestMutation.mutate()}
      failed={requestMutation.isError}
      pending={requestMutation.isPending}
      support={authState.support}
    />
  );
}
