import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthState } from "../auth/useAuthState";
import { createMovement, getInventorySummary, getLocations, inventoryError, type MovementType } from "../../shared/api/inventory";
import "./inventory.css";
import { refreshAfterMovement } from "../../shared/api/inventoryCache";

const actionNames = { ISSUE: "Взять", RETURN: "Вернуть", TRANSFER: "Переместить", RECEIPT: "Приход", WRITE_OFF: "Списать" } as const;
type Action = keyof typeof actionNames;
export function ItemInventoryPanel({itemId, archived = false}: {itemId: string; archived?: boolean}) {
  const auth = useAuthState();
  const client = useQueryClient();
  const summary = useQuery({queryKey: ["inventory", "summary", itemId], queryFn: ({signal}) => getInventorySummary(itemId, signal)});
  const locations = useQuery({queryKey: ["inventory", "locations"], queryFn: ({signal}) => getLocations(signal)});
  const [action, setAction] = useState<Action | null>(null);
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [notice, setNotice] = useState("");
  const active = locations.data?.filter(x => x.status === "ACTIVE") ?? [];
  const stocked = active.filter(x => summary.data?.locations.some(row => row.location.location_id === x.id && row.quantity > 0));
  const sourceId = source || (stocked.length === 1 ? stocked[0].id : "");
  const destinations = active.filter(x => action !== "TRANSFER" || x.id !== sourceId);
  const destinationId = destination || (destinations.length === 1 ? destinations[0].id : "");
  const needsSource = action === "ISSUE" || action === "TRANSFER" || action === "WRITE_OFF";
  const needsDestination = action === "RETURN" || action === "TRANSFER" || action === "RECEIPT";
  const available = summary.data?.locations.find(row => row.location.location_id === sourceId)?.quantity ?? 0;
  const amount = Number(quantity);
  const valid = Number.isSafeInteger(amount) && amount > 0 && (!needsSource || (sourceId !== "" && amount <= available)) && (!needsDestination || destinationId !== "") && (action !== "TRANSFER" || sourceId !== destinationId);
  const mutation = useMutation({
    mutationFn: () => createMovement({movement_type: action as MovementType, client_request_id: requestId,
      ...(needsSource ? {source_location_id: sourceId} : {}), ...(needsDestination ? {destination_location_id: destinationId} : {}), lines: [{item_id: itemId, quantity: amount}]}),
    onSuccess: async () => { setNotice("Операция записана в журнал."); setAction(null); setRequestId(crypto.randomUUID());
      await refreshAfterMovement(client, itemId); },
    onError: () => { void client.invalidateQueries({queryKey: ["inventory", "summary", itemId]}); },
  });
  const changed = () => { setRequestId(crypto.randomUUID()); mutation.reset(); };
  return <section aria-labelledby="stock-title" className="detail-panel">
    <h2 id="stock-title">В наличии: {summary.data?.total_count ?? "…"}</h2>
    {summary.isError ? <p role="alert">Не удалось загрузить остаток. <button onClick={() => void summary.refetch()}>Повторить</button></p> : null}
    <dl className="detail-list">{summary.data?.locations.map(row => <div key={row.id}><dt>{row.location.name}</dt><dd>{row.quantity}</dd></div>)}</dl>
    {summary.data?.total_count === 0 ? <p>Оборудования в местах хранения пока нет.</p> : null}
    {locations.isError ? <p role="alert">Не удалось загрузить места хранения. <button onClick={() => void locations.refetch()}>Повторить</button></p> : null}
    <div className="warehouse-actions">{(Object.keys(actionNames) as Action[]).filter(key => auth.data?.user.role === "ADMIN" || key === "ISSUE" || key === "RETURN").filter(key => !archived || key !== "ISSUE" && key !== "RECEIPT").map(key => <button type="button" className="button button--dark" key={key} disabled={summary.isPending || summary.isError || locations.isError || locations.isPending || mutation.isPending} onClick={() => {setAction(key); setSource(""); setDestination(""); setQuantity("1"); setNotice(""); changed();}}>{actionNames[key]}</button>)}</div>
    {notice ? <p role="status">{notice} <Link to="/movements">Движения</Link></p> : null}
    {action ? <form className="warehouse-form form-surface" onSubmit={event => {event.preventDefault(); if(valid && !mutation.isPending) mutation.mutate();}}>
      <h3>{actionNames[action]}</h3>
      <fieldset disabled={mutation.isPending}>
      {needsSource ? <label>Откуда<select required value={sourceId} onChange={event => {setSource(event.target.value); setDestination(""); changed();}}><option value="">Выберите место хранения</option>{stocked.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select><small>Доступно: {available}</small></label> : null}
      {needsDestination ? <label>Куда<select required value={destinationId} onChange={event => {setDestination(event.target.value); changed();}}><option value="">Выберите место хранения</option>{destinations.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label> : null}
      <label>Количество<input required type="number" inputMode="numeric" min="1" step="1" max={needsSource ? available : Number.MAX_SAFE_INTEGER} value={quantity} onChange={event => {setQuantity(event.target.value); changed();}} /></label>
      {mutation.isError ? <p role="alert">{inventoryError(mutation.error)}</p> : null}
      <div className="warehouse-actions"><button className="button button--accent" disabled={!valid || mutation.isPending} type="submit">{mutation.isPending ? "Записываем…" : "Подтвердить"}</button><button className="button button--ghost" type="button" onClick={() => setAction(null)}>Отмена</button></div>
      </fieldset>
    </form> : null}
  </section>;
}
