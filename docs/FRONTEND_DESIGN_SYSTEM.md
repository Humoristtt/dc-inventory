# Frontend Design System

Этот документ является нормативным контрактом визуальной архитектуры
Spikatel Inventory.

Он определяет, где живут общие визуальные правила, какие UI primitives
разрешено использовать страницам и какие page-local CSS решения запрещены.

Если реализация, старый CSS, тест или историческая документация противоречат
этому документу, противоречие должно быть устранено в том же change set.
Нельзя сохранять второй визуальный контракт только ради совместимости со
старой разметкой.

## 1. Scope

Design system отвечает за:

- page shell и основные content boundaries;
- page header;
- brand toolbar;
- page title / section title / kicker;
- buttons;
- icon buttons;
- form fields;
- input / select / textarea / combobox geometry;
- dialog / sheet surface primitives;
- typography roles;
- spacing, radius, color и elevation tokens;
- responsive geometry общих UI primitives.

Feature CSS отвечает только за:

- layout конкретной предметной области;
- presentation специфичных сущностей;
- grid/list composition;
- уникальные визуальные элементы предметной области.

Feature CSS не должен заново определять базовую геометрию header, button,
input, select, textarea или dialog surface.

## 2. Current architecture baseline

Architecture refactor начат от source baseline:

`1a34aa407696163ad81e913d346bb8d334feafc6`

Рабочая ветка:

`refactor/frontend-design-system`

На момент начала refactor production runtime уже переведён на:

`1a34aa407696163ad81e913d346bb8d334feafc6`

Для этого revision подтверждены exact image provenance, successful migrations,
healthy runtime, Alembic `f8a9b0c1d2e3`, закрытый regular mutation gate,
internal/external health `200`, loopback-only web bind и active backup timer.

Последующий real Telegram Desktop review именно этого production revision
выявил visual/design-system inconsistencies, из-за которых начат текущий
architecture refactor.

Regular warehouse mutation gate остаётся:

`REAL_INVENTORY_MUTATIONS_ENABLED=false`

Design-system refactor не имеет права менять backend domain model,
database schema, warehouse mutation semantics или production safety gates.

## 3. Причина refactor

Frontend исторически развивался несколькими UX passes.

В результате общие визуальные элементы оказались распределены по feature CSS:

- catalog landing/category header;
- detail/create/edit header;
- warehouse header;
- More/Admin header;
- page toolbar;
- buttons;
- form controls;
- dialogs/sheets.

Это позволило страницам выглядеть похожими, но не гарантировало их
архитектурную идентичность.

Типичный дефект такого подхода: изменение общей шапки исправляет один route,
но не меняет другой route, потому что они используют разные selectors и
разные CSS ownership boundaries.

Текущий refactor устраняет эту возможность архитектурно.

## 4. CSS ownership

Целевая структура:

    frontend/src/app/styles/tokens.css
        только design tokens и responsive token values

    frontend/src/app/styles/global.css
        reset, document defaults, accessibility globals

    frontend/src/shared/ui/
        reusable React UI primitives
        shared visual contracts

    frontend/src/shared/ui/design-system.css
        implementation общих UI primitives

    frontend/src/features/*/*.css
        только feature-specific presentation/layout

    frontend/src/pages/
        composition; page не создаёт собственную design system

`catalog.css` не является глобальной design system.

Ни один другой feature stylesheet также не может становиться скрытой
design system.

## 5. Design tokens

Числовое значение, которое относится к общему UI contract, должно иметь
semantic token.

Не допускается создавать несколько tokens с одинаковым смыслом.

Например, одновременно иметь общий control radius и отдельный form control
radius без различия semantics запрещено.

### Typography roles

Канонические semantic roles:

- `kicker`;
- `meta`;
- `secondary`;
- `body`;
- `control`;
- `emphasis`;
- `card-title`;
- `section-title`;
- `page-title`.

Страница выбирает роль, а не произвольный `font-size`.

Feature-specific мелкий текст допускается только если он действительно имеет
отдельную semantic роль. Такое исключение сначала добавляется в design-system
contract, затем используется в feature CSS.

### Form controls

Single-line input/select/combobox используют один geometry contract.

Высота:

- default/mobile: `52px`;
- `>=680px`: `56px`;
- `>=1100px`: `60px`.

Для одного breakpoint должны совпадать:

- height;
- min-height;
- font-size;
- horizontal padding;
- radius;
- border treatment.

Textarea использует тот же font/radius/padding contract, но отдельный
shared minimum-height.

Нельзя после применения shared textarea token повторно перебивать его
page-local `min-height`.

## 6. PageHeader

Все основные application pages используют один reusable `PageHeader`.

Его anatomy:

    PageHeader
      BrandToolbar
        SpikatelBrand
        TelegramFullscreenButton

      HeadingRow
        optional Back action
        TitleBlock
          kicker
          h1
          optional description
        optional actions

      optional HeaderContent
        search / contextual controls

Один `PageHeader` используется для:

- Catalog landing;
- Category;
- Item detail;
- Item create;
- Item edit;
- Movements;
- Locations;
- More;
- Admin users.

Страницы не рисуют собственный branded header вручную.

### Visual contract

Основная branded header surface всегда использует единый
`--brand-header-background`.

Page title использует `--font-page-title`.

Kicker использует `--font-kicker` и acid brand color.

Верхняя brand toolbar, вертикальный rhythm, responsive paddings и decorative
surface принадлежат `PageHeader`, а не конкретной странице.

Back action и page actions являются slots одного header, а не поводом создавать
новый header class.

`PageHeader` всегда сохраняет structural back/title/actions slots в DOM,
даже когда optional back/action content отсутствует. Это не позволяет CSS grid
auto-placement сдвигать title между разными страницами.

## 7. Buttons

Основные actions используют единый Button contract.

Разрешённые semantic variants:

- primary/dark;
- accent;
- ghost;
- danger.

Отдельно допускаются:

- icon button;
- compact toolbar/filter control;
- text action.

Каждый такой variant имеет собственный shared contract.

Запрещено создавать feature-specific button только потому, что существующий
button отличается на несколько пикселей.

Feature CSS может управлять placement (`width`, grid position, alignment), но
не базовыми:

- height;
- padding;
- radius;
- typography;
- focus treatment.

## 8. Form fields

Общий form-field contract определяет:

- label typography;
- label/control gap;
- required marker;
- help/meta text;
- error text;
- invalid state.

Native input, select и combobox должны визуально совпадать.

`SuggestionInput` не должен иметь отдельную геометрию от обычного input.

Location editor, catalog create/edit, movement filters и admin filters должны
потреблять один control contract.

## 9. Dialogs and sheets

Modal dialog и bottom sheet могут иметь разную responsive placement, но общие:

- surface color;
- border;
- radius family;
- heading hierarchy;
- footer action layout;
- focus treatment

должны исходить из shared UI layer.

Feature определяет содержимое dialog, а не заново его visual foundation.

## 10. Responsive policy

Текущий visual acceptance workflow — desktop-first.

Это означает:

- desktop правится и принимается первым;
- responsive architecture сохраняется сразу;
- tablet/mobile не переводятся в fixed desktop layout;
- final tablet/mobile visual polish выполняется после desktop feature set.

Width policy:

- application content центрирован;
- ultrawide не растягивает content бесконечно;
- текущий максимальный application width остаётся bounded.

Height policy:

- интерфейс не масштабируется по физической диагонали монитора;
- длинный content использует normal document scroll;
- dialogs ограничены viewport и имеют внутренний scroll при необходимости;
- actions не должны становиться недоступными на меньшей высоте viewport.

## 11. Allowed exceptions

Не каждый control обязан иметь одинаковый размер.

Отдельные shared contracts допустимы для:

- icon buttons;
- compact filter controls;
- search field;
- bottom navigation;
- switches;
- status badges.

Но исключение должно быть:

1. семантически названо;
2. реализовано в shared UI layer;
3. описано здесь;
4. покрыто regression contract.

Исключение нельзя реализовывать случайным hardcoded size внутри feature CSS.

## 12. Запрещённые patterns

После завершения migration запрещены:

- branded page header implementation в feature CSS;
- `.detail-header`, `.category-header`, `.warehouse-page-header`,
  `.more-page__header`, `.admin-users-page__header` как независимые visual
  systems;
- общая `.page-toolbar` внутри `catalog.css`;
- generic input/select/textarea geometry внутри feature CSS;
- generic button geometry внутри feature CSS;
- повторное объявление одного selector ниже файла как `refinement`;
- hardcoded page-local form-control height;
- hardcoded page-local base radius для обычного form control;
- импорт feature CSS только ради получения shared primitive;
- исправление shared component через cascade override вместо изменения
  shared component/token.

## 13. Testing contract

Design system должен защищаться автоматически.

Required frontend gate после migration включает:

1. static design-system architecture check;
2. Vitest;
3. TypeScript typecheck;
4. oxlint;
5. production build;
6. Playwright responsive acceptance.

Browser regression обязан проверять минимум:

- одинаковую header surface на основных routes;
- одинаковую page-title typography;
- одинаковую form-control height внутри одного viewport;
- одинаковую input/select geometry;
- Button geometry по variant;
- отсутствие horizontal overflow;
- bounded ultrawide content;
- dialog viewport fit;
- bottom-navigation clearance.

Нельзя считать UI унифицированным только потому, что два screenshot выглядят
похоже.

## 14. Static architecture gate

После migration frontend получает script:

    npm run check:design-system

Он должен fail при возврате известных архитектурных нарушений.

Минимальные invariants:

- page-level branded header classes не возвращаются;
- `page-toolbar` не возвращается в feature CSS;
- generic form control geometry не определяется вне shared UI;
- запрещённые duplicate design tokens не возвращаются;
- canonical shared UI stylesheet подключён из application entrypoint.

Static gate не заменяет visual/browser acceptance.

## 15. Migration sequence

### Phase A — contract and inventory

- зафиксировать этот документ;
- зафиксировать known architecture findings;
- синхронизировать ROADMAP/ARCHITECTURE/DEVELOPMENT/HISTORY.

### Phase B — shared foundation

- создать `shared/ui`;
- создать canonical `PageHeader`;
- перенести shared toolbar/header styles;
- создать canonical button/control/field contracts;
- добавить static architecture gate.

### Phase C — page migration

Перевести все application routes на shared primitives.

После каждого migration старый visual CSS удаляется, а не оставляется
параллельно.

### Phase D — cleanup and enforcement

- удалить obsolete selectors;
- убрать cascade refinements;
- убрать feature-to-feature style dependency;
- пройти static/unit/typecheck/lint/build/E2E;
- провести source audit на отсутствие второго design-system layer.

### Phase E — real application acceptance

После merge/deploy:

- desktop Telegram acceptance;
- затем отдельный tablet/mobile visual pass по завершении desktop feature set.

## 16. Documentation rule

Любое изменение общего визуального контракта обязано в том же PR обновить этот
документ.

Если изменение касается только feature-specific content/layout и не меняет
общий contract, этот файл менять не требуется.

Новые общие primitives нельзя вводить только кодом без документации.
