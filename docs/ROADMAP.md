# План разработки Spikatel Inventory

> Канонический roadmap проекта. Этот файл является рабочим чек-листом разработки и должен обновляться вместе с кодом.
>
> **Правило:** завершённые пункты отмечаются `[x]`, текущие — `[~]`, запланированные — `[ ]`.
> Если решение меняется, старый пункт не удаляется бесследно: он переносится в раздел «Изменённые / отложенные решения» с короткой причиной.
>
> **Последнее обновление:** 2026-08-31  
> **Production baseline:** `ef0eefb096e2fada46394c8b969b9e7cf6dd13fc`

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

- [ ] В movement хранится actor.
- [ ] В movement хранится фактический получатель / источник, если применимо.
- [ ] В истории показываются оба.
- [ ] Сохраняется snapshot отображаемого имени на момент операции.
- [ ] Изменение Telegram username позже не переписывает историю задним числом.

## 1.3. Локации и хранение у сотрудников

Оборудование может находиться:

```text
LOCATION → физическая складская локация
CUSTODY  → у конкретного пользователя
```

- [ ] Локации являются first-class сущностями.
- [ ] «На руках у пользователя» является полноценным состоянием учёта.
- [ ] Выдача: склад → пользователь.
- [ ] Возврат: пользователь → склад.
- [ ] Перемещение: склад → склад.
- [ ] Приход: внешний источник → склад.
- [ ] Списание: склад / пользователь → write-off.
- [ ] Коррекция: только отдельное adjustment movement.
- [ ] Админ видит, у кого сейчас находится каждая позиция.
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

- [ ] Поддержан serial mode.
- [ ] Один serial не может находиться одновременно в двух местах.
- [ ] Уже выданный serial нельзя выдать повторно.
- [ ] Serial можно искать глобальным поиском.
- [ ] Для serial-позиций отображается история конкретного экземпляра.

---

# 3. Пользователи, роли и доступ

## 3.1. Роли

Первая версия:

- `ADMIN`
- `USER`

- [ ] ADMIN имеет полный доступ к административным операциям.
- [ ] USER может работать только в разрешённом пользовательском сценарии.
- [ ] Ролевые проверки выполняются на backend, а не только скрытием кнопок в UI.
- [ ] Bootstrap первого ADMIN задаётся явно, а не правилом «первый вошедший становится админом».

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

- [x] Неизвестный пользователь не получает доступ к каталогу на frontend gate; production smoke ещё впереди.
- [x] Пользователь сначала видит понятный экран доступа и кликабельный контакт ADMIN.
- [x] Пользователь подтверждает запрос кнопкой «ОК, запросить доступ».
- [x] Создание запроса идемпотентно на уровне service + partial unique DB invariant.
- [ ] ADMIN получает Telegram-уведомление.
- [ ] Основной approve/reject workflow выполняется inline-кнопками **в чате с ботом**, а не в Mini App.
- [ ] В сообщении ADMIN есть `[ ✅ Разрешить ]` и `[ ❌ Отклонить ]`.
- [ ] Callback может выполнить только ADMIN.
- [ ] Повторное нажатие уже обработанного callback безопасно.
- [ ] После решения inline-кнопки убираются / сообщение помечается обработанным.
- [ ] Пользователь получает Telegram-уведомление об одобрении + кнопку «Открыть приложение».
- [ ] Пользователь получает уведомление об отказе + кликабельный контакт `@Humoristttt`.
- [ ] Отозванный доступ немедленно блокирует новые защищённые запросы.

---

# 4. Telegram Foundation

## 4.1. Уже готово

- [x] Создан production Telegram bot `@spik_inventory_bot`.
- [x] Mini App URL привязан к `https://app.spik-inventory.ru`.
- [x] Настроена Telegram menu button «Открыть приложение».
- [x] Mini App успешно открывается внутри Telegram.
- [x] Production HTTPS → Cloudflare → Tunnel → VM → Nginx → FastAPI → PostgreSQL проверен.

## 4.2. `/start`

- [ ] Реализовать webhook handler `/start`.
- [ ] Отправлять брендированное приветствие.
- [ ] Кратко описывать назначение приложения.
- [ ] Добавить кнопку «Открыть приложение».
- [ ] Добавить «Запросить доступ», если пользователь не APPROVED.
- [ ] Не дублировать бессмысленно приветствие при повторном `/start`.

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
- [x] Frontend gate не пропускает браузер без валидной session/Telegram initData; production smoke ещё впереди.

## 4.4. Telegram webhook

- [ ] Реализовать отдельный Telegram module.
- [ ] Webhook принимает только ожидаемые Telegram updates.
- [ ] Проверяется `X-Telegram-Bot-Api-Secret-Token`.
- [ ] Повторный `update_id` дедуплицируется.
- [ ] Обработчики идемпотентны.
- [ ] Webhook не выполняет долгие операции внутри HTTP request.

## 4.5. Telegram Gateway через Cloudflare Worker

Причина: production VM не имеет стабильного прямого доступа к `api.telegram.org`.

```text
Backend
  ↓
Cloudflare Worker Telegram Gateway
  ↓
api.telegram.org
```

- [ ] Создать отдельный Worker Gateway.
- [ ] Worker хранит Telegram bot token как Cloudflare Secret для Bot API.
- [ ] Backend получает тот же bot token только через production secret/env для HMAC-проверки initData; frontend/Git/logs его не получают.
- [ ] Backend → Worker защищён отдельным gateway secret.
- [ ] Worker не является универсальным open proxy.
- [ ] Разрешён whitelist Bot API методов.
- [ ] Нормализованы timeout/retry/error mapping.
- [ ] Логи не содержат bot token.
- [ ] Проверен реальный `sendMessage`.

Начальный whitelist:

- `sendMessage`
- `sendPhoto`
- `editMessageText`
- `editMessageReplyMarkup`
- `answerCallbackQuery`

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

- [ ] Category.
- [ ] Item.
- [ ] Item archive вместо hard delete.
- [ ] Manufacturer / brand.
- [ ] Manufacturer part number.
- [ ] Уникальность / duplicate detection продумана до миграции.
- [ ] Datasheet/source metadata.
- [ ] Нельзя удалить Item, если это ломает исторические movement references.
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

- [ ] CategoryAttribute schema.
- [ ] Typed attribute values.
- [ ] Типы минимум: text, integer, decimal, boolean, enum.
- [ ] Нормализация единиц измерения.
- [ ] Backend валидирует атрибуты по схеме категории.
- [ ] Frontend формы строятся из metadata.
- [ ] Frontend карточки строятся из metadata.
- [ ] Frontend фильтры строятся из metadata.
- [ ] Excel-колонки строятся из metadata.
- [ ] Первые 5 схем version-controlled.
- [ ] Обычный ADMIN не может случайно удалить системный атрибут и сломать данные.

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

- [ ] Скорость хранится в нормализованном виде.
- [ ] Дальность хранится в метрах, UI форматирует м/км.
- [ ] Wavelength хранится в нормализованном виде.
- [ ] Form factor — enum/controlled vocabulary.
- [ ] Medium — controlled vocabulary.
- [ ] Connector — controlled vocabulary.
- [ ] Compatibility допускает несколько значений / текстовую спецификацию по выбранной модели данных.

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

> Начальная модель ориентирована на оптические патч-корды / пигтейлы / аналогичные позиции. Финальный словарь сверить по реальному Excel и складу до предметной миграции.

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

- [ ] Длина хранится в базовой единице.
- [ ] Разъёмы имеют controlled vocabulary.
- [ ] Полировка не смешивается со строкой connector.
- [ ] Цвет не является свободным хаотичным текстом, если возможно.

---

# 9. Категория «Кабели питания»

Поля:

- connector A;
- connector B;
- длина;
- цвет;
- номинальный ток — optional;
- напряжение — optional;
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
- [ ] Наличие.
- [ ] Локация.

UX:

- [ ] Поиск `C13 C14` находит нужную позицию без обязательного открытия filters.
- [ ] Цвет заметен в карточке, но не заменяет текстовое название.
- [ ] Длина форматируется единообразно.

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

- [ ] SERIAL по умолчанию.
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

- [ ] SERIAL.
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

- [ ] Datasheet URL.
- [ ] Source type.
- [ ] Optional source note.
- [ ] Дата последней проверки / обновления, если нужна.
- [ ] UI показывает, что данные взяты из manufacturer datasheet, а не «угаданы системой».
- [ ] Изменение характеристик попадает в administrative audit.

---

# 17. Рабочие операции

Типы movements первой версии:

- `OPENING_BALANCE`
- `RECEIPT`
- `ISSUE`
- `RETURN`
- `TRANSFER`
- `WRITE_OFF`
- `CORRECTION` / `ADJUSTMENT`
- `REVERSAL`
- `STOCKTAKE_ADJUSTMENT`

- [ ] Все типы имеют чёткие domain invariants.
- [ ] Movement может содержать несколько MovementLine.
- [ ] Каждая MovementLine хранит Item / InventoryUnit и количество.
- [ ] SERIAL и QUANTITY корректно сосуществуют в одном movement.
- [ ] Причина / комментарий доступна там, где нужна.
- [ ] Optional purpose/reference: сервер, стойка, тикет и т. п.

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

- [ ] Transactional NotificationOutbox.
- [ ] Worker.
- [ ] Retry.
- [ ] Backoff.
- [ ] Max attempts.
- [ ] Failed state.
- [ ] Diagnostics.
- [ ] Duplicate delivery prevention / idempotency where possible.
- [ ] Telegram failure не откатывает уже подтверждённую складскую операцию.

Первые уведомления:

- [ ] ADMIN: новый access request.
- [ ] USER: access approved.
- [ ] USER: access rejected.
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

- [ ] Valid initData → PASS.
- [ ] Modified username → FAIL.
- [ ] Modified user id → FAIL.
- [ ] Modified hash → FAIL.
- [ ] Expired auth_date → FAIL.
- [ ] Invalid webhook secret → FAIL.
- [ ] Duplicate update_id → exactly-once logical processing.
- [ ] User access revoked → protected API denied.

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
- [ ] Telegram gateway timeout boundaries.
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
- [x] Production source guard на `ef0eefb096e2fada46394c8b969b9e7cf6dd13fc`.

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
- [~] Реализовать Telegram backend foundation.
- [ ] Cloudflare Telegram Gateway.
- [ ] `/start`.
- [ ] Webhook.
- [ ] Webhook secret.
- [ ] Telegram update dedupe.
- [~] initData validation — backend + frontend integration implemented, production Telegram smoke pending.
- [~] Auth session — persistence/API + frontend session reuse implemented, production Telegram smoke pending.
- [x] User entity persistence.
- [x] ADMIN/USER persistence.
- [x] AccessStatus persistence.
- [x] Request access backend API + first-entry/pending frontend flow.
- [ ] Admin approve через inline callback в Telegram-чате.
- [ ] Admin reject через inline callback в Telegram-чате.
- [ ] Admin Telegram notification.
- [ ] User approval notification.
- [ ] User rejection notification.
- [ ] Security tests.
- [ ] Production smoke.

**GATE:** неизвестный пользователь не получает каталог; после approval получает доступ; поддельный initData не принимается.

## Stage 5 — Catalog Foundation

- [ ] Category.
- [ ] Item.
- [ ] Brand/manufacturer.
- [ ] CategoryAttribute.
- [ ] Typed attribute values.
- [ ] Archive/unarchive.
- [ ] Technical data source.
- [ ] Datasheet.
- [ ] Duplicate detection.
- [ ] Initial SFP schema.
- [ ] Initial optics schema.
- [ ] Initial power cable schema.
- [ ] Initial NIC schema.
- [ ] Initial disk schema.
- [ ] Admin catalog API.
- [ ] Migrations.
- [ ] Domain/API tests.
- [ ] Update `docs/CATALOG_SCHEMA.md`.

**GATE:** можно корректно создать и прочитать позиции всех пяти категорий без category-specific schema hacks.

## Stage 6 — Inventory Ledger

- [ ] Location.
- [ ] InventoryPosition / custody model.
- [ ] InventoryUnit.
- [ ] Movement.
- [ ] MovementLine.
- [ ] Balance projection.
- [ ] Opening balance.
- [ ] Receipt.
- [ ] Issue.
- [ ] Return.
- [ ] Transfer.
- [ ] Write-off.
- [ ] Correction.
- [ ] Reversal.
- [ ] Idempotency.
- [ ] Locks.
- [ ] Serial invariants.
- [ ] Quantity invariants.
- [ ] Actor/recipient semantics.
- [ ] Movement snapshots.
- [ ] Concurrency tests.

**GATE:** journal mathematically consistent; last-unit race passes; historical movement immutable.

## Stage 7 — Catalog Read API / Search / Filters

- [ ] Category listing.
- [ ] Item listing.
- [ ] Pagination.
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

- [ ] History list.
- [ ] History filters.
- [ ] Movement detail.
- [ ] Correction relationship.
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

- [ ] Transactional outbox.
- [ ] Worker.
- [ ] Retry policy.
- [ ] Failed diagnostics.
- [ ] Issue notification.
- [ ] Access notifications productionized.
- [ ] No alert spam.
- [ ] Tests.

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
- [ ] `docs/CATALOG_SCHEMA.md` — точные поля/enum/filter/card/export definitions 5 категорий.
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

**CURRENT: Stage 4 — Telegram Foundation + Access Control**

Ближайшая последовательность:

- [x] Спроектировать User / TelegramIdentity / AccessRequest.
- [x] Реализовать User / TelegramIdentity / AccessRequest persistence + migration.
- [x] Спроектировать session/auth contract.
- [x] Реализовать Telegram initData validator + auth session API + security tests.
- [ ] Реализовать `/start` webhook.
- [ ] Развернуть Telegram Gateway Worker.
- [ ] Проверить outbound `sendMessage`.
- [x] Реализовать request access + кликабельный `@Humoristttt` + pending screen.
- [ ] Реализовать ADMIN approve/reject.
- [ ] Уведомить ADMIN.
- [ ] Уведомить USER.
- [ ] Сделать production Telegram smoke.
- [ ] Обновить `docs/HISTORY.md`.
- [ ] Отметить Stage 4 DONE только после acceptance gate.
