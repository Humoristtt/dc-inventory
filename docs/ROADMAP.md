# План разработки Spikatel Inventory

> Канонический roadmap проекта. Этот файл является рабочим чек-листом разработки и должен обновляться вместе с кодом.
>
> **Правило:** завершённые пункты отмечаются `[x]`, текущие — `[~]`, запланированные — `[ ]`.
> Если решение меняется, старый пункт не удаляется бесследно: он переносится в раздел «Изменённые / отложенные решения» с короткой причиной.
>
> **Последнее обновление:** 2026-09-01
> **Production runtime code baseline:** `08aa052d2af3e9c7e9cb9a2bce670cf6674b6c97` — Stage 4 close; последующие docs-only commits не требуют rebuild runtime.
> **Production:** Stage 4 Telegram/auth/access foundation завершён 2026-09-01;
> Stage 5 и Stage 6 в production ещё не развёрнуты, real inventory entry
> заблокирован до backup + successful restore gate.
> **Current source:** Stage 5 Catalog Foundation и source-backed refinement
> merged в `main`. Stage 6 Warehouse Core реализован в текущем feature branch;
> local backend gate пройден, independent review ещё не завершён.

---

## 0. Цель продукта

Telegram Mini App для внутренней инвентаризации оборудования ЦОД.

Система должна давать достоверный ответ на четыре базовых вопроса:

1. Что есть в наличии?
2. Где это находится?
3. У кого это находится?
4. Кто, когда и на каком основании переместил / выдал / вернул оборудование?

Первая предметная версия охватывает:

- SFP / оптические трансиверы;
- оптику;
- медные сетевые кабели;
- кабели питания;
- сетевые карты;
- диски.

Категории имеют общий каркас карточки, но **разные схемы характеристик, фильтров, отображения и Excel-колонок**.

---

# 1. Неподвижные архитектурные инварианты

## 1.1. Складской учёт

- [ ] Источник истины — append-only журнал движений оборудования.
- [ ] Текущий остаток нельзя исправлять прямым редактированием числа.
- [ ] Любое изменение остатка создаётся через движение.
- [ ] Ошибочное движение исправляется компенсирующим движением / reversal.
- [ ] Исторические движения нельзя удалять через обычный API.
- [ ] Исторические движения нельзя редактировать задним числом.
- [ ] Остаток является транзакционной проекцией журнала.
- [ ] Отрицательные остатки запрещены.
- [ ] Одновременная выдача последней единицы должна завершиться успешно только у одного пользователя.
- [ ] Все связанные строки движения записываются атомарно одной DB-транзакцией.
- [ ] Повтор одного и того же клиентского запроса не должен создавать дубль движения — idempotency.

## 1.2. Кто физически получил и кто оформил

Каждая операция должна различать:

- **actor** — кто оформил действие в системе;
- **recipient / holder / source person** — кто физически получил, вернул или передал оборудование.

Пример:

```text
Выдача 4 × SFP
Основной склад → Иван Иванов
Операцию оформил: Вячеслав
```

- [x] В movement хранится actor.
- [x] В movement хранится фактический получатель / источник, если применимо.
- [x] Backend history возвращает оба.
- [x] Сохраняется snapshot отображаемого имени на момент операции.
- [x] Изменение Telegram username позже не переписывает историю задним числом.

## 1.3. Локации и хранение у сотрудников

Оборудование может находиться:

```text
LOCATION → физическая складская локация
CUSTODY  → у конкретного пользователя
```

- [x] Локации являются first-class сущностями.
- [x] «На руках у пользователя» является полноценным состоянием учёта.
- [x] Backend выдача: склад → пользователь.
- [x] Backend возврат: пользователь → склад.
- [x] Backend перемещение: склад → склад.
- [x] Backend приход: внешний источник → склад.
- [x] Backend списание: склад / пользователь → write-off.
- [x] Коррекция: только отдельное linked movement.
- [x] Approved/Admin API показывает current positions/holders.
- [ ] Пользователь видит экран «Моё оборудование».

---

# 2. Режимы учёта

## 2.1. QUANTITY

Для массовых позиций:

- количество;
- остаток по локациям;
- количество на руках;
- операции с количеством.

Примеры: кабели питания, оптика, большинство SFP.

- [ ] Поддержан количественный режим.
- [ ] Нельзя выдать количество > доступного.
- [ ] Нельзя создать движение с `quantity <= 0`.
- [ ] Остаток по каждой позиции и локации согласован с журналом.

## 2.2. SERIAL

Для индивидуально отслеживаемых единиц:

- serial number;
- optional asset tag;
- состояние;
- текущее местонахождение;
- текущий holder;
- optional WWN / firmware и т. п.

Предварительно:

| Категория | Режим по умолчанию |
|---|---|
| SFP | QUANTITY, с возможностью SERIAL для конкретной позиции |
| Оптика | QUANTITY |
| Кабели питания | QUANTITY |
| Сетевые карты | SERIAL |
| Диски | SERIAL |

- [x] Поддержан serial mode.
- [x] Один serial не может находиться одновременно в двух местах.
- [x] Уже выданный serial нельзя выдать повторно.
- [ ] Serial можно искать глобальным поиском.
- [x] Backend history фильтруется по конкретному InventoryUnit.

---

# 3. Пользователи, роли и доступ

## 3.1. Роли

Первая версия:

- `ADMIN`
- `USER`

- [ ] ADMIN имеет полный доступ к административным операциям.
- [ ] USER может работать только в разрешённом пользовательском сценарии.
- [x] Общий backend authorization foundation различает `Authenticated`, `Approved` и `Admin`.
- [x] Реализованные catalog/warehouse endpoints используют `Approved` / `Admin`
  согласно policy; future endpoints сохраняют тот же acceptance invariant.
- [x] Bootstrap первого ADMIN задаётся явно numeric Telegram ID, а не правилом «первый вошедший становится админом».

## 3.2. Статусы доступа

Планируемые статусы:

- `PENDING`
- `APPROVED`
- `REJECTED`
- `BLOCKED` / `DISABLED` при необходимости.

Первое открытие неизвестным пользователем:

```text
Нужен доступ

Это внутреннее приложение для учёта оборудования ЦОД.
Для получения доступа и по всем вопросам обратитесь к @Humoristttt.

[ ОК, запросить доступ ]
```

`@Humoristttt` должен быть кликабельным Telegram-контактом (`https://t.me/Humoristttt`); username и URL приходят из backend config, а не размазываются константами по frontend.

После запроса:

```text
Запрос отправлен
Статус: На рассмотрении

Если доступ нужен срочно, свяжитесь с @Humoristttt.
```

- [x] Неизвестный пользователь не получает доступ к каталогу на frontend gate; production smoke пройден 2026-09-01.
- [x] Пользователь сначала видит понятный экран доступа и кликабельный контакт ADMIN.
- [x] Пользователь подтверждает запрос кнопкой «ОК, запросить доступ».
- [x] Создание запроса идемпотентно на уровне service + partial unique DB invariant.
- [x] `REJECTED` допускает новый запрос; `BLOCKED` запрещает повторный запрос.
- [x] Backend security boundary не полагается на frontend gate.
- [x] Bootstrap ADMIN recovery закрывает оставшийся `PENDING` AccessRequest.
- [x] ADMIN получает Telegram-уведомление.
- [x] Основной approve/reject workflow выполняется inline-кнопками **в чате с ботом**, а не в Mini App.
- [x] В сообщении ADMIN есть `[ ✅ Разрешить ]` и `[ ❌ Отклонить ]`.
- [x] Callback может выполнить только ADMIN.
- [x] Повторное нажатие уже обработанного callback безопасно.
- [x] После решения inline-кнопки убираются / сообщение помечается обработанным.
- [x] Пользователь получает Telegram-уведомление об одобрении + кнопку «Открыть приложение».
- [x] Пользователь получает уведомление об отказе + кликабельный контакт `@Humoristttt`.
- [x] Отозванный доступ немедленно блокирует новые защищённые запросы.

---

# 4. Telegram Foundation

## 4.1. Уже готово

- [x] Создан production Telegram bot `@spik_inventory_bot`.
- [x] Mini App URL привязан к `https://app.spik-inventory.ru`.
- [x] Настроена Telegram menu button «Открыть приложение».
- [x] Mini App успешно открывается внутри Telegram.
- [x] Production HTTPS → Cloudflare → Tunnel → VM → Nginx → FastAPI → PostgreSQL проверен.

## 4.2. `/start`

- [x] Реализовать webhook handler `/start`.
- [x] Отправлять брендированное приветствие.
- [x] Кратко описывать назначение приложения.
- [x] Добавить кнопку «Открыть приложение».
- [ ] UX polish: добавить в `/start` отдельную кнопку «Запросить доступ», если пользователь не APPROVED.
- [ ] UX polish: не дублировать бессмысленно приветствие при повторном `/start`.

Эти два UX-пункта не блокируют закрытие Stage 4 production MVP и остаются
явным backlog без изменения backend access/security boundary.

Ожидаемый смысл сообщения:

```text
Spikatel Inventory

Внутренняя система учёта оборудования ЦОД.

• поиск оборудования;
• выдача и возврат;
• фактические остатки;
• история движения.

[ Открыть приложение ]
```

## 4.3. Telegram WebApp authentication

- [x] Frontend передаёт оригинальный Telegram `initData` в `/api/auth/telegram`.
- [x] Backend validator реализует Telegram HMAC-SHA-256 verification.
- [x] Проверяется `auth_date` и ограничение свежести.
- [x] Просроченный / существенно будущий initData отклоняется.
- [x] Любое изменение подписанного payload ломает подпись.
- [x] Duplicate query fields отклоняются.
- [x] Нельзя доверять `initDataUnsafe` без server-side validation.
- [x] Реализована persistence-модель отзывной server-side session; в БД хранится только SHA-256 token hash.
- [x] Подключить реальный frontend → `/api/auth/telegram`.
- [x] `/api/auth/telegram` после validation создаёт/обновляет Telegram identity.
- [x] `/api/auth/telegram` выдаёт защищённую `HttpOnly` session cookie; в production `Secure`.
- [x] Bearer token не используется и не хранится в `localStorage`.
- [x] Frontend gate не пропускает браузер без валидной session/Telegram initData; production smoke пройден 2026-09-01.

## 4.4. Telegram webhook

- [x] Реализовать отдельный Telegram module.
- [x] Webhook принимает только ожидаемые Telegram updates.
- [x] Проверяется `X-Telegram-Bot-Api-Secret-Token`.
- [x] Повторный `update_id` дедуплицируется.
- [x] Обработчики идемпотентны.
- [x] Webhook не выполняет долгие операции внутри HTTP request.

## 4.5. Telegram Gateway через Cloudflare Worker

Причина: production VM не имеет стабильного прямого доступа к `api.telegram.org`.

```text
Backend
  ↓
Cloudflare Worker Telegram Gateway
  ↓
api.telegram.org
```

- [x] Создать отдельный Worker Gateway.
- [x] Worker хранит Telegram bot token как Cloudflare Secret для Bot API.
- [x] Backend получает тот же bot token только через production secret/env для HMAC-проверки initData; frontend/Git/logs его не получают.
- [x] Backend → Worker защищён отдельным gateway secret.
- [x] Worker не является универсальным open proxy.
- [x] Разрешён whitelist Bot API методов.
- [x] Нормализованы timeout/retry/error mapping.
- [x] Логи не содержат bot token.
- [x] Проверен реальный `sendMessage`.

Production Stage 4 whitelist:

- `sendMessage`
- `editMessageText`
- `editMessageReplyMarkup`
- `answerCallbackQuery`

`sendPhoto` не требуется Stage 4 и добавляется вместе с media workflow,
когда появится реальный consumer.

## 4.6. Production acceptance

- [x] Cloudflare Worker Gateway развёрнут и реальный `sendMessage` проверен.
- [x] Telegram webhook зарегистрирован на production hostname.
- [x] `/start` проходит полный маршрут Telegram → webhook → FastAPI → outbox → worker → Gateway → Telegram.
- [x] Cloudflare `1010` для стандартного Python urllib устранён явным service `User-Agent`.
- [x] Новый пользователь проходит access gate и создаёт запрос.
- [x] ADMIN получает запрос в Telegram и одобряет его inline-кнопкой.
- [x] Пользователь получает «Доступ предоставлен» и кнопку открытия Mini App.
- [x] После одобрения пользователь входит в Mini App.
- [x] Production VM имеет чистый worktree, только локальную ветку `main` и не содержит untracked project files.
- [x] Stage 4 production MVP закрыт 2026-09-01.

---

# 5. Общая модель каталога

Общие поля любой позиции:

- категория;
- бренд;
- клиентское / рабочее название;
- модель;
- manufacturer part number;
- internal code — optional;
- описание;
- режим учёта;
- статус `ACTIVE / ARCHIVED`;
- комментарий;
- datasheet URL — optional;
- источник технических характеристик;
- 0..N фотографий;
- primary photo.

- [x] Category.
- [x] Item.
- [x] Item archive вместо hard delete.
- [x] Manufacturer / brand.
- [x] Manufacturer part number.
- [x] Уникальность / duplicate detection продумана до миграции.
- [x] Datasheet/source metadata.
- [~] Нельзя удалить Item, если это ломает исторические movement references:
  публичного hard-delete API нет; future Movement FK должен сохранить RESTRICT.
- [ ] Исторические movement snapshots остаются читаемыми после rename Item.

---

# 6. Динамические схемы характеристик категорий

Не делать огромную таблицу с десятками nullable колонок.

Не размазывать по frontend:

```ts
if (category === "sfp") ...
else if (category === "disk") ...
```

Категория описывает собственные атрибуты:

- `key`;
- label;
- data type;
- unit;
- required;
- filterable;
- searchable;
- card visible;
- detail visible;
- table visible;
- Excel visible;
- sort order;
- filter type;
- allowed values / validation.

- [x] CategoryAttribute schema.
- [x] Typed attribute values.
- [x] Типы минимум: text, integer, decimal, boolean, enum.
- [x] Нормализация единиц измерения.
- [x] Backend валидирует атрибуты по схеме категории.
- [ ] Frontend формы строятся из metadata.
- [ ] Frontend карточки строятся из metadata.
- [ ] Frontend фильтры строятся из metadata.
- [ ] Excel-колонки строятся из metadata.
- [x] Первые 5 схем version-controlled.
- [x] Source-backed refinement добавляет шестую schema без category-specific
  application code.
- [x] Обычный ADMIN не может случайно удалить системный атрибут и сломать данные.

---

# 7. Категория SFP / трансиверы

## 7.1. Поля

Минимальный инженерный набор:

- бренд;
- модель;
- manufacturer part number;
- форм-фактор: SFP / SFP+ / SFP28 / QSFP+ / QSFP28 / QSFP56 / QSFP-DD / расширяемо;
- скорость;
- среда: SMF / MMF / Copper / DAC / AOC;
- стандарт / reach class: SR / LR / ER / ZR / BiDi / CWDM / DWDM / расширяемо;
- дальность;
- connector: LC Duplex / LC Simplex / MPO/MTP / RJ45 / расширяемо;
- TX wavelength;
- RX wavelength;
- DOM/DDM;
- vendor compatibility;
- datasheet URL;
- примечание.

- [x] Скорость хранится в нормализованном виде.
- [x] Дальность хранится в метрах, UI форматирует м/км.
- [x] Wavelength хранится в нормализованном виде.
- [x] Form factor — enum/controlled vocabulary.
- [x] Medium — controlled vocabulary.
- [x] Connector — controlled vocabulary.
- [x] Compatibility допускает текстовую спецификацию по выбранной модели данных.

## 7.2. Фильтры SFP

- [ ] Бренд.
- [ ] Форм-фактор.
- [ ] Скорость.
- [ ] Дальность.
- [ ] Тип волокна / среда.
- [ ] Разъём.
- [ ] SR/LR/ER/ZR/BiDi и т. п.
- [ ] Длина волны.
- [ ] DOM/DDM.
- [ ] Совместимость.
- [ ] Только в наличии.
- [ ] Локация.
- [ ] У пользователя / на складе — если это полезно в выбранном UX.

## 7.3. Карточка SFP

Компактный list card:

```text
[ФОТО]

Finisar FTLX1471D3BCL
10G · SFP+ · LR · SMF
10 км · 1310 нм · LC Duplex

На складе: 8 шт.
На руках: 3 шт.
```

Detail card:

- фото / gallery;
- название;
- бренд;
- модель;
- PN;
- полный набор характеристик;
- источник характеристик;
- datasheet;
- остатки по локациям;
- количество на руках;
- последние / связанные движения при наличии прав.

- [ ] Карточка корректна с фото.
- [ ] Карточка корректна без фото.
- [ ] Длинная модель не ломает layout.
- [ ] Длинный PN не ломает layout.
- [ ] Нулевой остаток отображается явно.
- [ ] 15–20 характеристик не ломают detail screen.

---

# 8. Категория «Оптика»

> Version-controlled schema создана миграцией Stage 5 и ориентирована на
> оптические патч-корды / пигтейлы / аналогичные позиции. Source reference
> review подтвердил границу Category, но не подтвердил закрытый connector/color/
> polarity vocabulary. Эти поля остаются TEXT; историческая `f4a5b6c7d8e9` не
> меняется.

Планируемые поля:

- тип изделия;
- бренд;
- part number;
- single mode / multi mode;
- стандарт: OS2 / OM2 / OM3 / OM4 / OM5 / расширяемо;
- разъём A;
- polish A;
- разъём B;
- polish B;
- simplex / duplex / количество волокон;
- длина;
- цвет;
- полярность — optional;
- комментарий.

Фильтры:

- [ ] Тип изделия.
- [ ] Бренд.
- [ ] SM/MM.
- [ ] OS2/OM2/OM3/OM4/OM5.
- [ ] Разъём A.
- [ ] Разъём B.
- [ ] UPC/APC.
- [ ] Длина.
- [ ] Количество волокон / simplex-duplex.
- [ ] Цвет.
- [ ] Наличие.
- [ ] Локация.

Normalization:

- [x] Длина хранится в базовой единице.
- [x] Connector и polish хранятся раздельно; connector остаётся normalized
  TEXT из-за неоднородных LC/MPO/LCHD/gender notations в reference examples.
- [x] Полировка не смешивается со строкой connector.
- [x] Цвет остаётся normalized TEXT: reference examples не доказывают полный
  controlled vocabulary.

---

# 9. Категория «Кабели питания»

Поля:

- connector A;
- connector B;
- длина;
- цвет;
- номинальный ток — optional;
- напряжение — optional;
- количество проводников — optional;
- сечение проводника — optional;
- бренд — optional;
- part number — optional;
- комментарий.

Типовой пример:

```text
IEC C13 → IEC C14
2 м
Красный
10 A
```

Фильтры:

- [ ] Connector A.
- [ ] Connector B.
- [ ] Длина.
- [ ] Цвет.
- [ ] Номинальный ток.
- [ ] Количество проводников / сечение.
- [ ] Наличие.
- [ ] Локация.

UX:

- [ ] Поиск `C13 C14` находит нужную позицию без обязательного открытия filters.
- [ ] Цвет заметен в карточке, но не заменяет текстовое название.
- [ ] Длина форматируется единообразно.

---

# 9.5. Категория «Медные сетевые кабели»

Recurring source examples подтверждают отдельную category boundary: RJ45 patch
cords не соответствуют fiber-required `optics` и не являются кабелями питания.

Поля:

- connector A;
- connector B;
- длина;
- категория кабеля;
- shielding — optional;
- бренд / model / part number — общие Item fields.

Normalization:

- [x] Добавлена versioned system Category `copper_network_cable`.
- [x] Default accounting — `QUANTITY`.
- [x] Длина хранится в metres как DECIMAL.
- [x] Cable category и shielding остаются TEXT: один observed value не
  доказывает полный controlled vocabulary.
- [ ] Search/facets/UI реализуются только в соответствующих будущих stages.

---

# 10. Категория «Сетевые карты»

Поля:

- бренд;
- модель;
- manufacturer part number;
- количество портов;
- скорость портов;
- media / port type: RJ45 / SFP+ / SFP28 / QSFP+ / QSFP28 / расширяемо;
- PCIe generation;
- PCIe lanes;
- protocol: Ethernet / Fibre Channel / InfiniBand / расширяемо;
- bracket: full profile / low profile / optional/unknown;
- SR-IOV — optional;
- RDMA / RoCE — optional;
- комментарий.

Фильтры:

- [ ] Бренд.
- [ ] Количество портов.
- [ ] Скорость.
- [ ] Media / port type.
- [ ] PCIe generation.
- [ ] PCIe lanes.
- [ ] Protocol.
- [ ] Bracket.
- [ ] Наличие.
- [ ] Локация.

Default accounting:

- [x] SERIAL по умолчанию.
- [ ] Serial number обязателен для отслеживаемой единицы либо вводится по согласованным правилам.
- [ ] Есть текущий holder конкретной карты.

---

# 11. Категория «Диски»

Поля позиции:

- бренд;
- модель;
- manufacturer part number;
- HDD / SSD / NVMe;
- ёмкость;
- форм-фактор: 2.5" / 3.5" / M.2 / U.2 / U.3 / расширяемо;
- интерфейс: SATA / SAS / NVMe / расширяемо;
- interface speed — optional;
- RPM — для HDD;
- sector format — optional;
- endurance — optional;
- datasheet;
- комментарий.

Поля конкретного serial unit:

- serial number;
- WWN — optional;
- firmware — optional;
- состояние;
- текущая локация / holder;
- комментарий.

Фильтры:

- [ ] Бренд.
- [ ] HDD/SSD/NVMe.
- [ ] Ёмкость.
- [ ] SATA/SAS/NVMe.
- [ ] Форм-фактор.
- [ ] RPM.
- [ ] Состояние.
- [ ] Наличие.
- [ ] Локация.

Default accounting:

- [x] SERIAL.
- [ ] Один serial только в одной позиции.
- [ ] Глобальный поиск по SN.
- [ ] Глобальный поиск по WWN при наличии.

---

# 12. Поиск

## 12.1. Глобальный поиск

Искать одновременно по:

- названию;
- бренду;
- модели;
- manufacturer part number;
- serial number;
- WWN;
- searchable category attributes;
- aliases / нормализованным синонимам.

Примеры:

```text
SFP-10G-LR
X710
1.92TB
C13
ABC12345
```

- [ ] Поиск нечувствителен к разумным различиям регистра.
- [ ] Нормализация пробелов.
- [ ] Поиск part number.
- [ ] Поиск serial.
- [ ] Поиск по техническим searchable fields.
- [ ] Нет неконтролируемого wildcard/full scan на больших данных.
- [ ] Pagination.

## 12.2. Поиск внутри категории

- [ ] Совмещается с category filters.
- [ ] Совмещается с sorting.
- [ ] Совмещается с availability.
- [ ] Фильтры сохраняются при возврате из карточки.
- [ ] Можно быстро очистить все фильтры.

---

# 13. Faceted filters

Фильтры должны показывать реальные значения из текущей выборки.

```text
Бренд
Cisco      12
Finisar     8
Intel       3

Скорость
1G         11
10G         9
25G         3
```

- [ ] Backend возвращает facet counts.
- [ ] Counts пересчитываются корректно при выбранных фильтрах.
- [ ] Не показываются бессмысленные пустые значения.
- [ ] Multi-select semantics определены и протестированы.
- [ ] Range filters определены и протестированы.
- [ ] «Только в наличии».
- [ ] Фильтр по локации.
- [ ] Filter metadata не захардкожен в каждом React screen.

---

# 14. Сортировка

- [ ] По названию.
- [ ] По бренду.
- [ ] По наличию.
- [ ] По количеству.
- [ ] Категорийные варианты, если инженерно полезны.
- [ ] Стабильная сортировка при pagination.

---

# 15. Фото и media

Фото добавляются постепенно и **не обязательны** для создания позиции.

```text
Item
 └─ Media[]
      primary
      sort_order
      mime_type
      width
      height
      storage_key
```

- [ ] 0..N images.
- [ ] Primary image.
- [ ] Reorder gallery.
- [ ] Branded/category placeholder без фото.
- [ ] JPEG.
- [ ] PNG.
- [ ] WebP при необходимости.
- [ ] MIME проверяется по содержимому, а не только расширению.
- [ ] Ограничение размера.
- [ ] Ограничение dimensions.
- [ ] Thumbnail generation.
- [ ] Нормализация orientation.
- [ ] Удаление лишней metadata по возможности.
- [ ] Нельзя загрузить произвольный non-image файл как `.jpg`.
- [ ] Media storage abstraction.

Начально:

```text
LocalMediaStorage
```

Позже без переписывания catalog:

```text
S3MediaStorage / R2MediaStorage
```

---

# 16. Характеристики производителя

Особенно важно для SFP, NIC и дисков.

Для технических данных хранить provenance:

- `MANUFACTURER`
- `LABEL`
- `IMPORT`
- `MANUAL`

- [x] Базовые поля `Item.datasheet_url` и free-text
  `Item.technical_data_source` реализованы в Stage 5.
- [ ] Structured source type (`MANUFACTURER` / `LABEL` / `IMPORT` / `MANUAL`).
- [ ] Optional отдельная source note.
- [ ] Дата последней проверки / обновления, если нужна.
- [ ] UI показывает, что данные взяты из manufacturer datasheet, а не «угаданы системой».
- [ ] Изменение характеристик попадает в administrative audit.

---

# 17. Рабочие операции

Реализованные Stage 6 movement types:

- `RECEIPT`
- `ISSUE`
- `RETURN`
- `TRANSFER`
- `WRITE_OFF`
- `CORRECTION` / `ADJUSTMENT`
- `REVERSAL`

Future controlled workflows, не реализованные generic Stage 6 movement API:

- `OPENING_BALANCE`
- `STOCKTAKE_ADJUSTMENT`

- [x] Все реализованные Stage 6 types имеют чёткие domain invariants.
- [x] Movement может содержать несколько ordered MovementLine.
- [x] Каждая MovementLine хранит Item / InventoryUnit и quantity согласно mode.
- [x] SERIAL и QUANTITY корректно сосуществуют в одном movement.
- [x] Optional comment хранится в movement history.
- [x] Optional purpose/reference хранится в movement history.
- [ ] Спроектировать отдельный `OPENING_BALANCE` workflow после production-data gate.
- [ ] Реализовать `STOCKTAKE_ADJUSTMENT` только вместе со Stage 14 workflow.

---

# 18. Batch-выдача

Обязательный рабочий сценарий.

```text
Выдача
----------------
2 × SFP Finisar
1 × Intel X710 SN ...
3 × C13-C14 2 m

Кому: Иванов
Откуда: Основной склад
Комментарий: монтаж сервера ...
```

- [ ] Корзина / batch movement draft.
- [ ] Несколько позиций.
- [ ] Несколько serial units.
- [ ] Финальная confirmation page.
- [ ] Одна DB transaction.
- [ ] Либо применяются все lines, либо ни одна.
- [ ] При конфликте пользователь получает понятное сообщение по конкретной строке.
- [ ] Нельзя double-submit.
- [ ] Повтор network request не создаёт второй movement.

---

# 19. «Моё оборудование»

Для USER:

- [ ] Список всего, что сейчас числится на пользователе.
- [ ] Группировка по категориям.
- [ ] Количество для QUANTITY.
- [ ] Serial для SERIAL.
- [ ] Быстрый переход к карточке.
- [ ] Быстрый старт возврата.
- [ ] История собственных движений при разрешённой политике.

Для ADMIN:

- [ ] Просмотр оборудования конкретного пользователя.
- [ ] Поиск пользователя.
- [ ] Общий экран «У сотрудников».

---

# 20. История движений

Фильтры:

- дата;
- тип операции;
- категория;
- Item;
- serial;
- фактический получатель;
- actor;
- локация;
- direction/source/destination.

- [ ] Pagination.
- [ ] Стабильный порядок.
- [ ] Movement detail.
- [ ] Все lines движения.
- [ ] Actor.
- [ ] Recipient / holder.
- [ ] Source / destination.
- [ ] Comment / purpose.
- [ ] Связь correction ↔ original movement.
- [ ] UI явно показывает исправленные операции.
- [ ] Никакой UI-кнопки «удалить историю».

---

# 21. Administrative audit

Не смешивать с физическим movement ledger.

Audit events:

- изменение Item;
- изменение manufacturer specs;
- добавление / удаление / primary switch фото;
- approval / reject пользователя;
- изменение роли;
- archive/unarchive Item;
- administrative correction;
- изменение важных category metadata.

- [ ] Отдельный AuditEvent.
- [ ] Actor.
- [ ] Timestamp.
- [ ] Entity type/id.
- [ ] Action.
- [ ] Безопасный before/after snapshot для значимых полей.
- [ ] Audit нельзя тихо удалить обычным UI.

---

# 22. Excel export

Формат — `.xlsx`.

В UI:

```text
Экспорт
├─ Вся категория
└─ Текущая выборка
```

- [ ] Export всей категории.
- [ ] Export текущего поиска и фильтров.
- [ ] Общие колонки.
- [ ] Категорийные колонки.
- [ ] Остатки по локациям.
- [ ] Всего на складе.
- [ ] На руках.
- [ ] Общий итог.
- [ ] Comment.
- [ ] Freeze header.
- [ ] AutoFilter.
- [ ] Разумная ширина колонок.
- [ ] Числа сохраняются числами.
- [ ] Даты сохраняются датами.
- [ ] Кириллица корректна.
- [ ] Порядок колонок максимально привычен относительно исходных рабочих таблиц.

Для SERIAL-категорий:

- [ ] Sheet `Остатки`.
- [ ] Sheet `Серийные номера`.
- [ ] Serial sheet: Model / PN / Serial / Location / Holder / Condition / Comment.
- [ ] Диски: WWN/Firmware при наличии.
- [ ] NIC: serial / asset tag при наличии.

Перед реализацией Excel export:

- [ ] Повторно открыть исходные пользовательские таблицы.
- [ ] Зафиксировать порядок и названия рабочих колонок.
- [ ] Согласовать только реальные расхождения, не переделывать формат ради «красоты».

---

# 23. Excel initial import

Текущие файлы `data/source/` не являются import input и не содержат
авторитетных opening balances. Этот future workflow применяется только к
отдельно согласованному dataset; quantity/serial/location должны быть проверены
владельцем, а не унаследованы из reference examples.

Импорт не пишет сразу в production tables.

```text
Upload
  ↓
Staging
  ↓
Preview
  ↓
Normalization
  ↓
Validation
  ↓
Duplicate detection
  ↓
Manual review
  ↓
Commit
```

- [ ] Staging import.
- [ ] Preview.
- [ ] Mapping колонок.
- [ ] Категорийная validation.
- [ ] Нормализация бренда.
- [ ] Нормализация модели / PN.
- [ ] Нормализация units.
- [ ] Duplicate detection.
- [ ] Неизвестные значения не превращаются молча в «правильные».
- [ ] Пустое количество НЕ означает ноль.
- [ ] Пустое количество получает статус «требует пересчёта».
- [ ] Opening balance создаётся через `OPENING_BALANCE movement`.
- [ ] Импорт можно отменить до commit.
- [ ] Повторный commit одного staging batch невозможен.

---

# 24. Инвентаризация / физический пересчёт

```text
Начать пересчёт
Категория: SFP
Локация: Основной склад

Ожидалось: 8
Фактически: 7
Расхождение: -1
```

- [ ] Stocktake session.
- [ ] Локация.
- [ ] Категория / scope.
- [ ] Expected quantity.
- [ ] Actual quantity.
- [ ] Differences.
- [ ] Review before commit.
- [ ] Финальное расхождение создаёт `STOCKTAKE_ADJUSTMENT`.
- [ ] Никогда не выполняется прямой `balance = actual`.
- [ ] Кто проводил пересчёт.
- [ ] Когда.
- [ ] Причина / комментарий.
- [ ] История stocktake сохраняется.

---

# 25. Telegram notifications

Нельзя отправлять Telegram внутри основной складской DB-транзакции.

```text
BEGIN
  Movement
  Balance projection
  NotificationOutbox
COMMIT

Outbox Worker
  ↓
Telegram Gateway
```

- [x] Transactional NotificationOutbox.
- [x] Worker.
- [x] Retry.
- [x] Exponential bounded backoff.
- [x] Max attempts.
- [x] `DEAD` failed state.
- [ ] Diagnostics UI / operational tooling для failed delivery.
- [x] Dedupe-key based enqueue idempotency.
- [ ] Telegram failure не откатывает уже подтверждённую складскую операцию:
  требуется inventory-specific coupling после появления Movement.

Первые уведомления:

- [x] ADMIN: новый access request.
- [x] USER: access approved.
- [x] USER: access rejected.
- [ ] ADMIN: оборудование выдано.
- [ ] В notification выдачи: кому.
- [ ] В notification выдачи: кто оформил.
- [ ] В notification выдачи: позиции и количество.
- [ ] В notification выдачи: склад / локация.
- [ ] Не добавлять лишний технический alert spam.

---

# 26. UX / навигация

Предварительная нижняя навигация:

```text
Каталог
Моё
Движения
Ещё
```

ADMIN в «Ещё»:

- Запросы доступа;
- Пользователи;
- Приход;
- Перемещение;
- Инвентаризация;
- Каталог / управление;
- Экспорт;
- Audit / служебные разделы при необходимости.

- [ ] Mobile-first.
- [ ] Telegram safe areas.
- [ ] Корректный viewport.
- [ ] Telegram Desktop narrow window.
- [ ] Android-like viewport.
- [ ] iPhone-like viewport.
- [ ] Telegram BackButton semantics.
- [ ] BackButton закрывает внутренний экран / карточку, а не ломает навигацию.
- [ ] Если используется Escape на Desktop — закрывает только modal/card, не Mini App.
- [ ] Bottom navigation не перекрывает контент.
- [ ] Keyboard поиска не перекрывает primary action.
- [ ] Loading states.
- [ ] Empty states.
- [ ] Error states.
- [ ] Offline / network error с понятным retry.
- [ ] Skeletons там, где они реально улучшают UX.
- [ ] Никаких огромных hero-заголовков в рабочем интерфейсе.

---

# 27. Карточки оборудования

Общие требования:

- [ ] Фото либо корректный category placeholder.
- [ ] Категория.
- [ ] Бренд + модель.
- [ ] 3–5 наиболее полезных технических параметров.
- [ ] Остаток.
- [ ] На руках.
- [ ] Статус отсутствия.
- [ ] Переход в detail.
- [ ] Никакой перегрузки всеми характеристиками в list card.

Detail:

- [ ] Gallery.
- [ ] Manufacturer specs.
- [ ] Source/datasheet.
- [ ] Остатки по локациям.
- [ ] На руках.
- [ ] Serial units для SERIAL.
- [ ] Действия согласно роли.
- [ ] Item archived state.
- [ ] Comment.

---

# 28. Тестовая стратегия

## 28.1. Backend unit/domain tests

- [ ] Нельзя взять больше остатка.
- [ ] Нельзя quantity <= 0.
- [ ] Нельзя получить отрицательный balance.
- [ ] Нельзя вернуть serial, который не находится у пользователя.
- [ ] Нельзя выдать serial дважды.
- [ ] Нельзя serial одновременно в двух местах.
- [ ] Нельзя обычным API удалить movement.
- [ ] Correction создаёт новое движение.
- [ ] Reversal связан с original movement.
- [ ] Batch movement атомарен.
- [ ] Archived Item не нарушает старую историю.
- [ ] Role policies.

## 28.2. PostgreSQL integration tests

Использовать настоящий PostgreSQL 18.

- [ ] Migrations up.
- [ ] Migrations down там, где rollback поддерживается проектной политикой.
- [ ] Constraints реально действуют в PostgreSQL.
- [ ] Transactions.
- [ ] Locks.
- [ ] Idempotency.
- [ ] Concurrency.
- [x] Access foundation: два конкурентных request-access вызова дают ровно один `PENDING`.
- [x] Auth foundation: настоящий PostgreSQL отбрасывает revoked/expired sessions.

Критический acceptance:

```text
остаток = 1

request A → взять 1
request B → взять 1
одновременно

ожидаем:
ровно один SUCCESS
ровно один CONFLICT/OUT_OF_STOCK
остаток = 0
```

- [ ] Этот тест стабильно проходит многократно.

## 28.3. API tests

- [ ] UNKNOWN/PENDING → protected API denied.
- [ ] APPROVED USER → allowed user endpoints.
- [ ] USER → admin endpoint denied.
- [ ] ADMIN → admin endpoint allowed.
- [ ] Validation errors имеют стабильный API contract.
- [ ] Pagination.
- [ ] Search.
- [ ] Filters.
- [ ] Sort.
- [ ] Export authorization.
- [ ] Media authorization.

## 28.4. Telegram security tests

- [x] Valid initData → PASS.
- [x] Modified username → FAIL.
- [x] Modified user id → FAIL.
- [x] Modified hash → FAIL.
- [x] Expired auth_date → FAIL.
- [x] Invalid webhook secret → FAIL.
- [x] Duplicate update_id → exactly-once logical processing.
- [x] User access revoked → protected API denied.

## 28.5. Outbox tests

- [ ] Gateway success.
- [ ] Gateway timeout.
- [ ] Gateway 5xx.
- [ ] Retry.
- [ ] Final failed.
- [ ] Movement остаётся committed при сбое Telegram.
- [ ] Повтор worker не создаёт лишнюю складскую операцию.

---

# 29. Тесты категорий и фильтров

## 29.1. SFP

Fixture минимум:

```text
Cisco   1G   LX  10 km
Cisco   10G  LR  10 km
Finisar 10G  SR  300 m
Finisar 25G  LR  10 km
```

- [ ] `brand=Finisar` → 2.
- [ ] `speed=10G` → 2.
- [ ] `brand=Finisar + speed=10G` → 1.
- [ ] `reach>=10km` → ожидаемый набор.
- [ ] connector filter.
- [ ] medium filter.
- [ ] DOM filter.
- [ ] availability filter.
- [ ] location filter.
- [ ] facet counts.

## 29.2. Оптика

- [ ] SM/MM filter.
- [ ] OS/OM filter.
- [ ] connector A/B.
- [ ] UPC/APC.
- [ ] length.
- [ ] color.
- [ ] availability/location.
- [ ] combined filters.

## 29.3. Кабели питания

- [ ] connector A.
- [ ] connector B.
- [ ] `C13 C14` text search.
- [ ] length.
- [ ] color.
- [ ] current.
- [ ] availability/location.
- [ ] combined filters.

## 29.4. Сетевые карты

- [ ] brand.
- [ ] port count.
- [ ] speed.
- [ ] media.
- [ ] PCIe generation.
- [ ] lanes.
- [ ] protocol.
- [ ] bracket.
- [ ] availability/location.
- [ ] serial search.

## 29.5. Диски

- [ ] HDD/SSD/NVMe.
- [ ] capacity.
- [ ] interface.
- [ ] form factor.
- [ ] RPM.
- [ ] condition.
- [ ] location.
- [ ] serial search.
- [ ] WWN search.
- [ ] combined filters.

---

# 30. Frontend component / visual tests

Карточки:

- [ ] Без фото.
- [ ] С фото.
- [ ] 1 фото.
- [ ] Несколько фото.
- [ ] Очень длинный manufacturer/model.
- [ ] Очень длинный Part Number.
- [ ] Нулевой остаток.
- [ ] Большой остаток.
- [ ] Несколько локаций.
- [ ] SERIAL item.
- [ ] QUANTITY item.
- [ ] Missing optional attributes.
- [ ] 20 detail attributes.
- [ ] Archived item.

Filters:

- [ ] Bottom sheet / modal открывается корректно.
- [ ] Скролл.
- [ ] Apply.
- [ ] Reset.
- [ ] Counts.
- [ ] Длинные значения.
- [ ] Empty result.
- [ ] Возврат из Item detail не теряет фильтры.

---

# 31. Playwright E2E

Viewport profiles:

- [ ] Telegram Desktop narrow.
- [ ] Android-like.
- [ ] iPhone-like.
- [ ] Desktop wide для admin workflows.

Критические E2E:

- [ ] PENDING → request access → ADMIN approve → USER enters catalog.
- [ ] Global search → Item detail.
- [ ] Category → filters → Item detail.
- [ ] QUANTITY issue.
- [ ] SERIAL issue.
- [ ] Batch issue.
- [ ] Return.
- [ ] Transfer.
- [ ] Admin receipt.
- [ ] Correction / reversal.
- [ ] «Моё оборудование».
- [ ] History movement detail.
- [ ] Export current filtered category.
- [ ] Image upload.
- [ ] Access revoked.
- [ ] Session expiry / re-auth.

---

# 32. Excel automated tests

Использовать `openpyxl`.

- [ ] Workbook открывается.
- [ ] Sheet names.
- [ ] Header order.
- [ ] Category-specific columns.
- [ ] Correct row values.
- [ ] Numbers are numbers.
- [ ] Dates are dates.
- [ ] Cyrillic.
- [ ] AutoFilter.
- [ ] Freeze panes.
- [ ] Filtered export не содержит лишних Items.
- [ ] Serial sheet содержит правильные units.
- [ ] Disk WWN/Firmware fields при наличии.
- [ ] Export из одинаковых данных детерминирован настолько, насколько это нужно для tests.

---

# 33. Media tests

- [ ] JPEG PASS.
- [ ] PNG PASS.
- [ ] Fake `.jpg` with text FAIL.
- [ ] Oversized file FAIL.
- [ ] Unsupported MIME FAIL.
- [ ] Unauthorized upload FAIL.
- [ ] USER cannot perform admin media mutation unless policy says otherwise.
- [ ] Thumbnail created.
- [ ] Primary image switch.
- [ ] Missing file handled safely.
- [ ] Orphan media audit.

---

# 34. Наблюдаемость и ошибки

- [ ] Structured application logs.
- [ ] Correlation/request id.
- [ ] Movement id в релевантных logs.
- [ ] Не логировать secrets.
- [ ] Не логировать Telegram initData целиком.
- [ ] Не логировать bot token.
- [ ] Нормальные 4xx domain errors.
- [ ] Нормальные 5xx diagnostics server-side.
- [x] Health live.
- [x] Health ready.
- [x] DB timeout boundaries.
- [x] Telegram gateway timeout boundaries.
- [ ] Media operation timeout/limits.
- [ ] Outbox diagnostics.
- [ ] Backup diagnostics.

---

# 35. Backup / restore

До реального production учёта:

- [ ] Автоматический PostgreSQL backup.
- [ ] Backup media.
- [ ] Retention policy.
- [ ] Backup вне самой VM.
- [ ] Проверка backup artifact.
- [ ] Реальный restore test в отдельное окружение.
- [ ] После restore запуск migrations/status checks.
- [ ] Проверка row counts / key invariants.
- [ ] Документированный runbook восстановления.
- [ ] Нельзя считать backup готовым без restore test.

---

# 36. Deployment

Текущее состояние:

- [x] Dev: Mac → GitHub.
- [x] Production VM — deployment target, не рабочая копия разработки.
- [x] Production runtime Docker Compose.
- [x] PostgreSQL не опубликован на host.
- [x] Backend не опубликован на host.
- [x] Nginx доступен только `127.0.0.1:8080`.
- [x] Cloudflare Tunnel outbound-only.
- [x] `cloudflared` enabled + active.
- [x] Production Swagger/OpenAPI отключён.
- [x] app/db Docker networks разделены.
- [x] CI backend/frontend/runtime зелёный.
- [x] Production source guard на `08aa052d2af3e9c7e9cb9a2bce670cf6674b6c97`.

До реальных данных:

- [ ] Pin/reproducible container images.
- [ ] Решить переход от build-on-VM к immutable image deployment.
- [ ] Документировать rollback.
- [ ] Migration gate.
- [ ] Post-deploy smoke.
- [ ] Backup before risky DB migrations.
- [ ] Source SHA visible in deployment diagnostics.

---

# 37. Этапы разработки

## Stage 1 — Runtime Skeleton

- [x] FastAPI.
- [x] PostgreSQL 18.
- [x] Alembic.
- [x] React/TypeScript/Vite.
- [x] Nginx.
- [x] Docker Compose.
- [x] Health endpoints.
- [x] CI.
- [x] Basic Russian docs.

**STATUS: DONE**

## Stage 2 — Production VM Runtime

- [x] VM configured.
- [x] Docker installed.
- [x] Runtime deployed.
- [x] DB internal only.
- [x] Backend internal only.
- [x] Web `127.0.0.1:8080`.
- [x] Migrations run successfully.
- [x] Production health PASS.

**STATUS: DONE**

## Stage 3 — Cloudflare / Domain / Tunnel

- [x] Domain `spik-inventory.ru`.
- [x] NS delegated to Cloudflare.
- [x] Cloudflare zone active.
- [x] Tunnel `dc-inventory-prod`.
- [x] Published application `app.spik-inventory.ru`.
- [x] CNAME → tunnel.
- [x] HTTPS external test PASS.
- [x] Full chain to PostgreSQL readiness PASS.

**STATUS: DONE**

## Stage 3.5 — Pre-Telegram Hardening

- [x] Proxy-chain corrected.
- [x] Production docs/OpenAPI disabled.
- [x] DB runtime boundaries.
- [x] SQLAlchemy naming convention.
- [x] app/db networks split.
- [x] web → postgres isolation.
- [x] CI production-shaped runtime job.
- [x] Docs updated.
- [x] Production deploy.
- [x] Source guard PASS.

**STATUS: DONE**

## Stage 4 — Telegram Foundation + Access Control

- [x] Bot created.
- [x] Mini App enabled.
- [x] Menu button configured.
- [x] First Mini App launch PASS.
- [x] Telegram backend foundation: webhook/outbox/access decisions.
- [x] Cloudflare Telegram Gateway.
- [x] `/start`.
- [x] Webhook.
- [x] Webhook secret.
- [x] Telegram update dedupe.
- [x] initData validation — backend + frontend integration + production Telegram smoke.
- [x] Auth session — persistence/API + frontend session reuse + production Telegram smoke.
- [x] User entity persistence.
- [x] ADMIN/USER persistence.
- [x] AccessStatus persistence.
- [x] Request access backend API + first-entry/pending frontend flow.
- [x] Stage 4.3a: rejected retry, polling sync, backend authz boundary, bootstrap consistency, PostgreSQL/CI coverage, docs.
- [x] Повторный source audit Stage 4.3a выполнен; stale frontend access-cache вынесен в Stage 4.3b.
- [x] Stage 4.3b: user-scoped access cache, PENDING-only authority, identity race test, CI topology regression.
- [x] Stage 4.4: transactional outbox, Telegram webhook/update dedupe, ADMIN decisions, worker и Cloudflare gateway.
- [x] Admin approve через inline callback в Telegram-чате.
- [x] Admin reject через inline callback в Telegram-чате.
- [x] Admin Telegram notification.
- [x] User approval notification.
- [x] User rejection notification.
- [x] Security tests.
- [x] Production smoke.

**GATE:** неизвестный пользователь не получает каталог; после approval получает доступ; поддельный initData не принимается.

**STATUS: DONE — production acceptance пройден 2026-09-01.**

## Stage 5 — Catalog Foundation

- [x] Category.
- [x] Item.
- [x] Brand/manufacturer.
- [x] CategoryAttribute.
- [x] Typed attribute values.
- [x] Archive/unarchive.
- [x] Technical data source.
- [x] Datasheet.
- [x] Duplicate detection.
- [x] Initial SFP schema.
- [x] Initial optics schema.
- [x] Initial power cable schema.
- [x] Initial NIC schema.
- [x] Initial disk schema.
- [x] Source reference review: 3 workbook / 6 sheets / 176 non-empty data rows.
- [x] Source-backed copper network cable schema.
- [x] Source-backed power conductor attributes и SFP vocabulary refinement.
- [x] Explicit no-import decision для reference quantities/balances/operational state.
- [x] Admin catalog API.
- [x] Migrations.
- [x] Domain/API tests.
- [x] Update `docs/CATALOG_SCHEMA.md`.

**GATE:** можно корректно создать и прочитать позиции всех versioned system
categories без category-specific schema hacks.

Foundation gate выполнен. Source reference reconciliation и metadata refinement
merged в `main` через PR #10. В production Stage 5 ещё не развёрнут.

## Stage 6 — Inventory Ledger

- [x] Location.
- [x] Normalized Location/holder custody positions.
- [x] InventoryUnit.
- [x] Movement.
- [x] MovementLine.
- [x] Balance projection.
- [x] Explicit no-opening-balance/no-import decision; real stock entry отдельно
  заблокирован до backup/restore production-data gate.
- [x] Receipt.
- [x] Issue.
- [x] Return.
- [x] Transfer.
- [x] Write-off.
- [x] Correction.
- [x] Reversal.
- [x] Idempotency.
- [x] Locks.
- [x] Serial invariants.
- [x] Quantity invariants.
- [x] Actor/recipient semantics.
- [x] Movement snapshots.
- [x] Concurrency tests.
- [x] Archived Location reversal invariant.
- [x] Archived Item QUANTITY/SERIAL lifecycle policy.
- [x] Global WWN identity and deterministic lock graph.
- [x] Stable MovementLine order and WWN snapshots.
- [x] Retryable PostgreSQL conflict mapping and BIGINT bounds.
- [x] Read-only projection reconciliation runbook.
- [~] Independent remediation review and CI.

**GATE:** journal mathematically consistent; last-unit race passes; historical movement immutable.

**STATUS: IN REVIEW — remediation реализована локально; Stage 6 не становится
DONE до повторного independent review и CI.**

## Stage 7 — Catalog Read API / Search / Filters

- [x] Базовый Category listing реализован в Stage 5.
- [x] Базовый Item listing реализован в Stage 5.
- [x] Детерминированная limit/offset pagination foundation реализована в Stage 5.
- [ ] Sorting.
- [ ] Global search.
- [ ] Category search.
- [ ] Facets.
- [ ] Availability.
- [ ] Location.
- [ ] SFP filters.
- [ ] Optics filters.
- [ ] Power cable filters.
- [ ] NIC filters.
- [ ] Disk filters.
- [ ] Filter fixture matrices.

**GATE:** every filter combination returns exact expected fixtures; frontend does not contain category-branch spaghetti.

## Stage 8 — Working Mini App UX

- [ ] Replace runtime hero.
- [ ] Telegram viewport integration.
- [ ] Safe areas.
- [ ] Home.
- [ ] Categories.
- [ ] Global search.
- [ ] Category listing.
- [ ] Filters.
- [ ] Sorting.
- [ ] Compact cards.
- [ ] Item detail.
- [ ] Manufacturer specs.
- [ ] Stock by location.
- [ ] Holder summary.
- [ ] «Моё».
- [ ] Loading/error/empty states.
- [ ] Telegram BackButton.
- [ ] Responsive tests.
- [ ] Playwright visual/E2E.

**GATE:** UI комфортен в Telegram Desktop narrow и mobile viewports; данные отображаются без обрезки.

## Stage 9 — Warehouse Operations UI

- [ ] Issue to self.
- [ ] Issue to another user.
- [ ] Batch cart.
- [ ] Quantity selection.
- [ ] Serial selection.
- [ ] Confirmation.
- [ ] Receipt.
- [ ] Return.
- [ ] Transfer.
- [ ] Purpose/comment.
- [ ] Optimistic/double-submit protection.
- [ ] E2E all operations.

**GATE:** UI action → committed movement → balances/holder/history all consistent.

## Stage 10 — History + Admin

- [x] Backend history list с stable database-generated `journal_seq` ordering и pagination.
- [x] Backend filters по movement type, Item и InventoryUnit.
- [x] Backend movement detail с ordered lines, actor/recipient, positions,
  purpose/comment и original link.
- [x] Backend correction relationship имеет Item + position invariants.
- [ ] History list UI.
- [ ] History presentation filters UI.
- [ ] Movement detail UI.
- [ ] Correction relationship UI.
- [ ] Users.
- [ ] Access request admin screen.
- [ ] Roles.
- [ ] User holdings.
- [ ] All holdings.
- [ ] Audit log.
- [ ] Admin correction flow.

**GATE:** администратор может ответить «кто, когда, что, кому и откуда выдал».

## Stage 11 — Media

- [ ] Media model.
- [ ] Local storage adapter.
- [ ] Upload API.
- [ ] Validation.
- [ ] Thumbnail.
- [ ] Primary image.
- [ ] Gallery.
- [ ] Placeholder.
- [ ] Admin UI.
- [ ] Backup media.
- [ ] Tests.

**GATE:** карточки с фото и без фото работают одинаково стабильно; media не может повредить runtime/storage.

## Stage 12 — Excel Export / Import

Export:

- [ ] Category export.
- [ ] Current filtered export.
- [ ] SFP workbook.
- [ ] Optics workbook.
- [ ] Power cable workbook.
- [ ] NIC workbook.
- [ ] Disk workbook.
- [ ] Serial sheets.
- [ ] Automated openpyxl tests.

Import:

- [ ] Upload.
- [ ] Staging.
- [ ] Preview.
- [ ] Mapping.
- [ ] Normalization.
- [ ] Validation.
- [ ] Duplicate detection.
- [ ] Blank quantity → recount.
- [ ] Opening balance movements.
- [ ] Commit gate.
- [ ] Import report.

**GATE:** экспорт соответствует рабочему формату; импорт никогда молча не портит каталог/остатки.

## Stage 13 — Notifications / Outbox Expansion

- [x] Transactional outbox foundation реализован в Stage 4.
- [x] Worker foundation реализован в Stage 4.
- [x] Bounded retry/backoff/max-attempts policy реализована в Stage 4.
- [ ] Failed diagnostics UI / operations.
- [ ] Issue notification.
- [x] Access notifications productionized в Stage 4.
- [ ] No alert spam.
- [ ] Inventory-notification tests; Stage 4 outbox/access tests уже реализованы.

**GATE:** Telegram outage не влияет на достоверность складской операции.

## Stage 14 — Physical Stocktake

- [ ] Session.
- [ ] Scope.
- [ ] Expected.
- [ ] Actual.
- [ ] Difference.
- [ ] Review.
- [ ] Adjustment movement.
- [ ] History/audit.
- [ ] Tests.

**GATE:** физическое расхождение исправляется без переписывания прошлого.

## Stage 15 — Production Hardening Before Real Inventory

**BLOCKING POLICY:** real inventory entry остаётся запрещён до выполненных
PostgreSQL automated backup + verified artifact + real restore test в отдельное
окружение. Deploy Stage 5/6 не снимает этот gate.

- [ ] PostgreSQL automated backup.
- [ ] Media backup.
- [ ] Off-VM storage.
- [ ] Retention.
- [ ] Real restore test.
- [ ] Restore runbook.
- [ ] Image pinning / immutable deployment decision.
- [ ] Rollback.
- [ ] Full migration check.
- [ ] Full concurrency suite.
- [ ] Full Playwright E2E.
- [ ] Security pass.
- [ ] Production smoke.
- [ ] Documentation audit.
- [ ] Final archive/source audit if required.

**GATE:** систему можно использовать как реальный источник складского учёта, а не только демонстрационную Mini App.

---

# 38. Deferred / не входит в первый рабочий scope

Не делать раньше времени:

- [ ] QR на каждую единицу оборудования.
- [ ] Barcode scanner.
- [ ] NetBox integration.
- [ ] Автоматический scraping manufacturer datasheets.
- [ ] Procurement / закупки.
- [ ] Резервирование оборудования.
- [ ] Заявки на выдачу до прихода на склад.
- [ ] Advanced analytics dashboards.
- [ ] Redis без фактической необходимости.
- [ ] Microservices.
- [ ] Полный S3/R2 migration до появления потребности.

Эти пункты допускаются позже, но текущая архитектура не должна делать их невозможными.

---

# 39. Документация, которая должна жить рядом с кодом

- [x] `README.md`
- [x] `docs/ARCHITECTURE.md`
- [x] `docs/DEVELOPMENT.md`
- [x] `docs/DEPLOYMENT.md`
- [x] `docs/HISTORY.md`
- [~] `docs/ROADMAP.md` — этот файл.
- [ ] `docs/PRODUCT_REQUIREMENTS.md` — пользовательские сценарии, роли, бизнес-правила.
- [x] `docs/CATALOG_SCHEMA.md` — точные поля/enum/filter/card/export definitions 5 категорий.
- [ ] `docs/OPERATIONS.md` — backup/restore/deploy/rollback/runbook по мере появления.
- [ ] API contract docs остаются генерируемыми, production Swagger наружу не включать.

Правило:

- [ ] Каждый feature PR обновляет релевантную документацию.
- [ ] Каждый завершённый Stage обновляет этот roadmap.
- [ ] Для закрытого Stage указывать PR/commit/SHA в `docs/HISTORY.md`.
- [ ] Не оставлять документацию «на потом» после больших архитектурных изменений.

---

# 40. Definition of Done для любого feature

Фича не считается завершённой, пока:

- [ ] Domain semantics определены.
- [ ] Migration корректна, если меняется DB.
- [ ] Backend validation.
- [ ] Permissions.
- [ ] API tests.
- [ ] Domain/integration tests.
- [ ] Frontend loading/error/empty states.
- [ ] Mobile/Telegram rendering.
- [ ] CI green.
- [ ] `git diff --check` clean.
- [ ] Production compatibility не нарушена.
- [ ] Документация обновлена.
- [ ] Нет временного/legacy кода без явной причины.
- [ ] Нет секретов в Git/logs.
- [ ] Acceptance gate конкретного этапа пройден.

---

# 41. Правила ведения roadmap

1. Не удалять завершённые пункты — отмечать `[x]`.
2. Текущий этап обозначать `[~]`.
3. Новые требования сначала добавлять сюда, затем реализовывать.
4. Если категория меняет схему, сначала обновлять `CATALOG_SCHEMA.md` и этот roadmap.
5. Не начинать следующий критический domain stage, пока не закрыт gate предыдущего.
6. Не добавлять «временное MVP-решение», которое заведомо потребует переписывания фундаментальной модели.
7. Не блокировать прогресс лишней архитектурой, если требование можно безопасно добавить позже.
8. После каждого крупного Stage проводить отдельный review до merge/deploy.
9. Production source SHA фиксировать в истории после каждого deploy.
10. Roadmap — рабочий документ: при каждом завершённом PR соответствующие checkbox должны обновляться.

---

# 42. Следующий фактический шаг

**CURRENT: Stage 6 — Inventory Ledger independent review**

Завершено:

- [x] Сверить source workbook как reference examples с требованиями Stage 5.
- [x] Зафиксировать source-to-canonical mapping и A–F decisions в
  `docs/CATALOG_SOURCE_REFERENCE.md`.
- [x] Зафиксировать первую каноническую модель каталога в `docs/CATALOG_SCHEMA.md`.
- [x] Спроектировать `Category`, `Item` и Brand/Manufacturer contract.
- [x] Спроектировать `CategoryAttribute` и typed attribute values.
- [x] Зафиксировать duplicate-detection и archive/unarchive invariants до миграции.
- [x] Зафиксировать initial schemas для SFP, оптики, кабелей питания, NIC и дисков.
- [x] Реализовать catalog persistence + Alembic migration.
- [x] Реализовать APPROVED read API и ADMIN mutation API.
- [x] Добавить PostgreSQL/domain/API tests.
- [x] Провести технический Stage 5 gate: пять категорий создаются и читаются без
  category-specific schema hacks.
- [x] Добавить source-backed metadata migration без backend contract changes.
- [x] Source-reference refinement merged в `main` через PR #10.
- [x] Спроектировать Stage 6 invariants в `docs/WAREHOUSE_DOMAIN.md`.
- [x] Добавить migration `b7c8d9e0f1a2` поверх `a6b7c8d9e0f1`.
- [x] Реализовать Location, InventoryUnit, Movement/Line и StockBalance.
- [x] Реализовать Approved read/Admin mutation API.
- [x] Добавить quantity/serial/idempotency/authorization/PostgreSQL tests.
- [x] Добавить real last-quantity и serial-allocation concurrency tests.
- [x] Исправить independent-review P1/P2 findings Stage 6 и добавить focused
  PostgreSQL lifecycle/integrity/concurrency regressions.
- [x] Выполнить remediation final backend gate: diff-check, Ruff, strict mypy и
  полный PostgreSQL pytest.
- [~] Провести independent review/CI Stage 6.

Следующий фактический шаг: повторный independent Stage 6 source review/CI после
отдельного разрешения на commit/push/PR. Stage 7 не начинается в этом change set.
