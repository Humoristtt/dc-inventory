import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthState } from "../../features/auth/useAuthState";
import { getLocations, inventoryError, inventoryRequest, type StorageLocation } from "../../shared/api/inventory";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import { TelegramFullscreenButton } from "../../shared/telegram/TelegramFullscreenButton";
import "../../features/inventory/inventory.css";

const blank = {code:"",name:"",location_type:"WAREHOUSE" as "WAREHOUSE" | "DATACENTER",address:""};
export function LocationsPage() {
  const auth = useAuthState(); const client = useQueryClient();
  const locations = useQuery({queryKey:["inventory","locations"],queryFn:({signal}) => getLocations(signal)});
  const [editing,setEditing] = useState<string | null>(null); const [open,setOpen] = useState(false); const [draft,setDraft] = useState(blank);
  const mutation = useMutation({mutationFn:({id,body,action}:{id?:string;body?:unknown;action?:string}) => inventoryRequest<StorageLocation>(`/api/admin/inventory/locations${id ? `/${id}` : ""}${action ? `/${action}` : ""}`,body ?? {}, id && !action ? "PATCH" : "POST"),onSuccess:()=>{setOpen(false);void client.invalidateQueries({queryKey:["inventory"]});}});
  const admin = auth.data?.user.role === "ADMIN";
  return <main className="catalog-page"><header className="category-header warehouse-page-header">
    <div className="page-toolbar page-toolbar--brand">
     <SpikatelBrand inverse title="Инвентаризация ЦОД" />
     <TelegramFullscreenButton />
   </div>
    <div className="warehouse-page-header__title">
      <span className="section-kicker">Склад</span>
      <h1>Места хранения</h1>
    </div>
  </header><div className="catalog-page__body">
    {admin ? <div className="warehouse-actions"><button className="button button--dark" onClick={()=>{setEditing(null);setDraft(blank);setOpen(true);mutation.reset();}}>Добавить место хранения</button><Link className="button" to="/catalog/new">Добавить оборудование</Link></div>:null}
    {locations.isError ? <p role="alert">Не удалось загрузить места хранения. <button onClick={()=>void locations.refetch()}>Повторить</button></p>:null}
    {locations.data?.map(row => <section className="detail-panel" key={row.id}><h2>{row.name}</h2><p>{row.location_type === "WAREHOUSE" ? "Склад" : "ЦОД"} · {row.code}{row.status === "ARCHIVED" ? " · Архив" : ""}</p>{row.address ? <p>{row.address}</p>:null}{admin ? <div className="warehouse-actions"><button className="button" disabled={mutation.isPending} onClick={()=>{setEditing(row.id);setDraft({code:row.code,name:row.name,location_type:row.location_type,address:row.address ?? ""});setOpen(true);mutation.reset();}}>Редактировать</button><button className="button" disabled={mutation.isPending} onClick={()=>mutation.mutate({id:row.id,action:row.status === "ACTIVE" ? "archive" : "unarchive"})}>{row.status === "ACTIVE" ? "Архивировать" : "Вернуть из архива"}</button></div>:null}</section>)}
    {mutation.isError ? <p role="alert">{inventoryError(mutation.error)}</p>:null}
    {open && admin ? <form className="detail-panel warehouse-form" onSubmit={event=>{event.preventDefault();const {code,...fields}=draft;mutation.mutate({id:editing ?? undefined,body:editing ? fields : {...fields,code}});}}><h2>{editing ? "Редактировать место" : "Новое место хранения"}</h2><fieldset disabled={mutation.isPending}>
      {!editing ? <div className="warehouse-form__field">
      <label htmlFor="location-code">Код</label>
      <input
        id="location-code"
        aria-describedby="location-code-hint"
        required
        maxLength={64}
        placeholder="Например: SKLAD-01"
        value={draft.code}
        onChange={e=>setDraft({...draft,code:e.target.value})}
      />
      <small className="warehouse-form__hint" id="location-code-hint">
        Короткий уникальный идентификатор места. Например: SKLAD-01 или DC-MSK-RACK-12.
      </small>
    </div>:null}
      <label>Название<input required maxLength={255} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
      <label>Тип<select value={draft.location_type} onChange={e=>setDraft({...draft,location_type:e.target.value as "WAREHOUSE" | "DATACENTER"})}><option value="WAREHOUSE">Склад</option><option value="DATACENTER">ЦОД</option></select></label>
      <label>Адрес<textarea maxLength={2000} value={draft.address} onChange={e=>setDraft({...draft,address:e.target.value})}/></label>
      <div className="warehouse-actions"><button className="button button--dark" type="submit">Сохранить</button><button className="button" type="button" onClick={()=>setOpen(false)}>Отмена</button></div></fieldset>
    </form>:null}
  </div></main>;
}
