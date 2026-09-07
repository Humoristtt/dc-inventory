import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useAuthState } from "../../features/auth/useAuthState";
import { AttributeControl } from "../../features/catalog/AttributeControl";
import { draftAttributesFromItem, validateDraftAttributes, type AttributeDraft } from "../../features/catalog/itemForm";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";
import { ApiRequestError } from "../../shared/api/auth";
import { createCatalogItem, createCatalogManufacturer, getCatalogCategories, getCatalogCategory, getCatalogItem, getCatalogManufacturers, patchCatalogItem, type CatalogItem, type ItemWritePayload } from "../../shared/api/catalog";
import "../../features/catalog/admin-catalog.css";
import "../../features/inventory/inventory.css";

const manufactured = new Set(["transceiver_ethernet", "transceiver_fc", "network_ethernet", "network_fc", "ssd", "hdd", "ram", "pcie_adapter"]);
type Draft = {category:string;manufacturer:string;model:string;name:string;attributes:AttributeDraft};
const empty:Draft = {category:"",manufacturer:"",model:"",name:"",attributes:{}};
function itemDraft(item:CatalogItem):Draft {return {category:item.category.key,manufacturer:item.manufacturer?.id ?? "",model:item.model ?? "",name:item.name,attributes:draftAttributesFromItem(item)};}
export function ItemFormPage() {
  const {itemId} = useParams(); const [params] = useSearchParams();
  const auth = useAuthState(); const navigate = useNavigate(); const back = useInternalBackNavigation(); const client = useQueryClient();
  const [state,setState] = useState<Draft | null>(null); const [family,setFamily] = useState("");
  const [errors,setErrors] = useState<Record<string,string>>({}); const [manufacturerName,setManufacturerName] = useState("");
  const [manufacturerSearch,setManufacturerSearch] = useState("");
  const item = useQuery({queryKey:["catalog","item",itemId],queryFn:({signal})=>getCatalogItem(itemId ?? "",signal),enabled:!!itemId});
  const categories = useQuery({queryKey:["catalog","categories"],queryFn:({signal})=>getCatalogCategories(signal)});
  const draft = state ?? (item.data ? itemDraft(item.data) : {...empty,category:params.get("category") ?? ""});
  const selected = categories.data?.find(x=>x.key === draft.category);
  const familyId = family || selected?.parent_id || "";
  const leaves = categories.data?.filter(x=>x.parent_id === familyId) ?? [];
  const schema = useQuery({queryKey:["catalog","category",draft.category],queryFn:({signal})=>getCatalogCategory(draft.category,signal),enabled:!!draft.category});
  const definitions = schema.data?.attributes.filter(x=>x.key !== "reach_m") ?? [];
  const manufacturers = useInfiniteQuery({queryKey:["catalog","manufacturers",manufacturerSearch],queryFn:({signal,pageParam})=>getCatalogManufacturers({q:manufacturerSearch,limit:100,offset:pageParam},signal),initialPageParam:0,getNextPageParam:last=>last.offset+last.items.length < last.total ? last.offset+last.items.length : undefined});
  const manufacturerOptions = new Map((manufacturers.data?.pages.flatMap(x=>x.items) ?? []).map(x=>[x.id,x]));
  if(item.data?.manufacturer && !manufacturerOptions.has(item.data.manufacturer.id)) manufacturerOptions.set(item.data.manufacturer.id,{...item.data.manufacturer,created_at:"",updated_at:""});
  const makerMutation = useMutation({mutationFn:()=>createCatalogManufacturer(manufacturerName),onSuccess:maker=>{setState({...draft,manufacturer:maker.id});setManufacturerName("");setManufacturerSearch("");void client.invalidateQueries({queryKey:["catalog","manufacturers"]});}});
  const mutation = useMutation({mutationFn:(payload:ItemWritePayload)=>{if(itemId){const {category_key:_,...patch}=payload;return patchCatalogItem(itemId,patch);}return createCatalogItem(payload);},onSuccess:saved=>{client.setQueryData(["catalog","item",saved.id],saved);void client.invalidateQueries({queryKey:["catalog","items"]});void client.invalidateQueries({queryKey:["catalog","facets"]});navigate(`/catalog/items/${saved.id}`,{replace:true});}});
  const update = (next:Partial<Draft>)=>{setState({...draft,...next});setErrors({});mutation.reset();};
  if(auth.isPending || itemId && item.isPending) return <p role="status">Загрузка…</p>;
  if(auth.data?.user.role !== "ADMIN") return <Navigate replace to="/catalog"/>;
  if(itemId && item.isError) return <p role="alert">Не удалось загрузить оборудование. <button onClick={()=>void item.refetch()}>Повторить</button></p>;
  const identityRequired = manufactured.has(draft.category);
  return <main className="catalog-page"><header className="detail-header"><button className="icon-button icon-button--light" type="button" onClick={back} aria-label="Назад">←</button><h1>{itemId ? "Редактировать оборудование" : "Добавить оборудование"}</h1></header><div className="catalog-page__body">
    <form className="catalog-form" onSubmit={event=>{event.preventDefault();const validation=validateDraftAttributes(definitions,draft.attributes);const next={...validation.errors};if(!draft.category) next.category="Выберите категорию";if(!draft.name.trim()) next.name="Укажите название";if(identityRequired && (!draft.manufacturer || !draft.model.trim())) next.identity="Укажите производителя и модель";setErrors(next);if(Object.keys(next).length || !schema.isSuccess || mutation.isPending)return;mutation.mutate({category_key:draft.category,manufacturer_id:identityRequired ? draft.manufacturer || null : null,model:identityRequired ? draft.model.trim() || null : null,name:draft.name.trim(),attributes:validation.values});}}>
      <fieldset className="detail-panel" disabled={mutation.isPending}>
        {!itemId ? <><label className="catalog-form__field">Семейство<select required value={familyId} onChange={event=>{setFamily(event.target.value);const options=categories.data?.filter(x=>x.parent_id === event.target.value) ?? [];update({...empty,category:options.length === 1 ? options[0].key : ""});}}><option value="">Выберите семейство</option>{categories.data?.filter(x=>x.parent_id === null).map(x=><option key={x.id} value={x.id}>{x.display_name}</option>)}</select></label><label className="catalog-form__field">Категория<select required value={draft.category} onChange={event=>update({...empty,category:event.target.value})}><option value="">Выберите категорию</option>{leaves.map(x=><option key={x.id} value={x.key}>{x.display_name}</option>)}</select></label></>:<p>{selected?.display_name}</p>}
        {categories.isError ? <p role="alert">Не удалось загрузить категории. <button type="button" onClick={()=>void categories.refetch()}>Повторить</button></p>:null}
        {identityRequired ? <><label className="catalog-form__field">Поиск производителя<input value={manufacturerSearch} onChange={e=>setManufacturerSearch(e.target.value)}/></label><label className="catalog-form__field">Производитель<select required value={draft.manufacturer} onChange={e=>update({manufacturer:e.target.value})}><option value="">Выберите производителя</option>{[...manufacturerOptions.values()].map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>{manufacturers.hasNextPage ? <button type="button" onClick={()=>void manufacturers.fetchNextPage()}>Ещё производители</button>:null}{manufacturers.isError ? <p role="alert">Не удалось загрузить производителей. <button type="button" onClick={()=>void manufacturers.refetch()}>Повторить</button></p>:null}<details><summary>Добавить производителя</summary><label className="catalog-form__field">Название производителя<input maxLength={255} value={manufacturerName} onChange={e=>setManufacturerName(e.target.value)}/></label><button className="button" type="button" disabled={!manufacturerName.trim() || makerMutation.isPending} onClick={()=>makerMutation.mutate()}>Создать производителя</button>{makerMutation.isError ? <p role="alert">Не удалось создать производителя. Возможно, он уже существует.</p>:null}</details><label className="catalog-form__field">Модель<input required maxLength={255} value={draft.model} onChange={e=>update({model:e.target.value})}/></label></>:null}
        <label className="catalog-form__field">Название оборудования<input required maxLength={255} value={draft.name} onChange={e=>update({name:e.target.value})}/></label>
      </fieldset>
      {draft.category ? <fieldset className="detail-panel" disabled={mutation.isPending}><legend>Характеристики</legend>{schema.isPending ? <p>Загружаем поля…</p>:null}{schema.isError ? <p role="alert">Не удалось загрузить поля. <button type="button" onClick={()=>void schema.refetch()}>Повторить</button></p>:null}{definitions.map(attribute=><AttributeControl key={attribute.key} attribute={attribute} value={draft.attributes[attribute.key]} error={errors[attribute.key]} onChange={value=>{const attributes={...draft.attributes};if(value === undefined) delete attributes[attribute.key];else attributes[attribute.key]=value;update({attributes});}}/>)}</fieldset>:null}
      {Object.keys(errors).length ? <p role="alert">{Object.values(errors).join(". ")}</p>:null}
      {mutation.isError ? <p role="alert">{mutation.error instanceof ApiRequestError && mutation.error.status === 409 ? "Такая позиция уже существует. Проверьте полную техническую идентичность." : mutation.error instanceof ApiRequestError && mutation.error.status === 423 ? "Изменения каталога пока отключены администратором." : "Не удалось сохранить. Проверьте обязательные поля и дальность."}</p>:null}
      <button className="button button--dark" disabled={mutation.isPending || !schema.isSuccess} type="submit">{mutation.isPending ? "Сохраняем…" : "Сохранить"}</button>
    </form>
  </div></main>;
}
