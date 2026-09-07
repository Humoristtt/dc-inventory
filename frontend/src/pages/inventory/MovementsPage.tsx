import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getCatalogCategories } from "../../shared/api/catalog";
import { getLocations, inventoryRequest, movementLabels, type Movement, type InventoryPage } from "../../shared/api/inventory";
import "../../features/inventory/inventory.css";

export function MovementsPage() {
  const [period, setPeriod] = useState("3m");
  const [actor, setActor] = useState("");
  const [equipment, setEquipment] = useState("");
  const [location, setLocation] = useState("");
  const [movementType, setMovementType] = useState("");
  const [offset, setOffset] = useState(0);
  const hierarchy = useQuery({queryKey:["catalog", "categories"], queryFn:({signal}) => getCatalogCategories(signal)});
  const locations = useQuery({queryKey:["inventory", "locations"], queryFn:({signal}) => getLocations(signal)});
  const actors = useQuery({queryKey:["inventory", "actors"], queryFn:({signal}) => inventoryRequest<{id:string;name:string}[]>("/api/inventory/movement-actors", undefined, "GET", signal)});
  const params = new URLSearchParams({period, offset: String(offset), limit:"30"});
  if(actor) params.set("actor_user_id",actor);
  if(equipment) params.set("category",equipment === "long-range" ? "transceivers" : equipment);
  if(equipment === "long-range") params.set("long_range","true");
  if(location) params.set("location_id",location);
  if(movementType) params.set("movement_type",movementType);
  const history = useQuery({queryKey:["inventory","movements",params.toString()], queryFn:({signal}) => inventoryRequest<InventoryPage<Movement>>(`/api/inventory/movements?${params}`, undefined,"GET",signal)});
  const change = (setter:(value:string)=>void, value:string) => {setter(value);setOffset(0);};
  return <main className="catalog-page"><header className="category-header"><span className="section-kicker">Складской журнал</span><h1>Движения</h1></header><div className="catalog-page__body">
    <div className="history-filters">
      <label>Период<select value={period} onChange={e => change(setPeriod,e.target.value)}>{[["7d","7 дней"],["30d","30 дней"],["3m","3 месяца"],["year","Год"],["all","Всё время"]].map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Тип движения<select value={movementType} onChange={e => change(setMovementType,e.target.value)}><option value="">Все типы</option>{Object.entries(movementLabels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Сотрудник<select value={actor} onChange={e => change(setActor,e.target.value)}><option value="">Все доступные</option>{actors.data?.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label>Оборудование<select value={equipment} onChange={e => change(setEquipment,e.target.value)}><option value="">Всё оборудование</option>{hierarchy.data?.filter(x => x.parent_id === null).map(family => <optgroup label={family.display_name} key={family.id}><option value={family.key}>{family.display_name} — всё</option>{hierarchy.data.filter(x => x.parent_id === family.id).map(leaf => <option value={leaf.key} key={leaf.id}>{leaf.display_name}</option>)}{family.key === "transceivers" ? <option value="long-range">Дальние</option>:null}</optgroup>)}</select></label>
      <label>Место хранения<select value={location} onChange={e => change(setLocation,e.target.value)}><option value="">Все места</option>{locations.data?.map(x => <option key={x.id} value={x.id}>{x.name}{x.status === "ARCHIVED" ? " (архив)" : ""}</option>)}</select></label>
    </div>
    {actors.isError || hierarchy.isError || locations.isError ? <p role="alert">Не удалось загрузить часть фильтров. <button onClick={() => {void actors.refetch();void hierarchy.refetch();void locations.refetch();}}>Повторить</button></p>:null}
    {history.isPending ? <p role="status">Загружаем журнал…</p>:null}
    {history.isError ? <p role="alert">Не удалось загрузить журнал. <button onClick={() => void history.refetch()}>Повторить</button></p>:null}
    {history.data?.items.length === 0 ? <p>За выбранный период движений нет.</p>:null}
    {history.data?.items.map(movement => <article className="movement-entry" key={movement.id}><header><span>№ {movement.journal_seq}</span><time dateTime={movement.occurred_at}>{new Date(movement.occurred_at).toLocaleString("ru-RU")}</time></header><p><strong>{movement.actor_display_name_snapshot}</strong> · {movementLabels[movement.movement_type]}</p><ul>{movement.lines.map(line => <li key={line.id}>{line.item_name_snapshot} — <strong>{line.quantity} шт.</strong></li>)}</ul><p>{movement.source_location_name_snapshot ? `Из: ${movement.source_location_name_snapshot}` : ""}{movement.source_location_name_snapshot && movement.destination_location_name_snapshot ? " → " : ""}{movement.destination_location_name_snapshot ? `В: ${movement.destination_location_name_snapshot}` : ""}</p></article>)}
    <div className="warehouse-actions">{offset > 0 ? <button className="button" onClick={() => setOffset(Math.max(0,offset-30))}>Назад</button>:null}{history.data && offset + history.data.items.length < history.data.total ? <button className="button" onClick={() => setOffset(offset+30)}>Следующая страница</button>:null}</div>
  </div></main>;
}
