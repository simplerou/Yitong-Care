import { request } from './http'
export type Meal='breakfast'|'lunch'|'dinner'
export type Texture='normal'|'soft'|'minced'|'pureed'
export interface MealOption {id:string;name:string;foods:string[];ingredients:string[];allergens:string[];tags:string[];texture:Texture;capacity:number;notes:string}
export interface MenuSlot {day:number;meal:Meal;cutoff:string;options:MealOption[]}
export interface WeeklyMenu {id?:string;week_start:string;status:'draft'|'published';version:number;slots:MenuSlot[]}
export interface Profile {version:number;resident_version:number;allergy_status:'unknown'|'known'|'confirmed_none';confirmed:boolean;allergens:string[];avoid_ingredients:string[];required_tags:string[];allowed_textures:Texture[];source:string;notes:string}
export interface Requirement {id:string;name:string;record_no:string;location:string;resident_version:number;allergies:string;chronic_conditions:string;dietary_notes:string;profile:Profile|null;reviewed:boolean}
export interface Coverage {in_care:number;reviewed_count:number;pending:{id:string;name:string}[];missing:{resident_id:string;name:string;day:number;meal:Meal}[]}
export interface MySlot extends MenuSlot {date:string;closed:boolean;options:(MealOption & {reasons:string[];remaining:number})[];selection:{option_id:string;version:number;needs_review:boolean}|null}
export interface MyMeals {menu:{id:string;week_start:string;version:number}|null;resident_name:string;reviewed:boolean;in_care?:boolean;slots:MySlot[]}
export interface Kitchen {date:string;meal:Meal;in_care:number;options:{id:string;name:string;foods:string[];count:number;capacity:number}[];needs_review:{id:string;name:string;location:string}[];unselected:{id:string;name:string;location:string}[]}
export const mealNames:Record<Meal,string>={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
export const textures:Record<Texture,string>={normal:'普通质地',soft:'软食',minced:'细碎食',pureed:'泥糊状食物'}
export function monday(value?:string){const d=value?new Date(value+'T12:00:00'):new Date();d.setDate(d.getDate()-(d.getDay()+6)%7);return localDate(d)}
export function localDate(d:Date){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
export function shiftDay(value:string,n:number){const d=new Date(value+'T12:00:00');d.setDate(d.getDate()+n);return localDate(d)}
export function emptyMenu(week:string):WeeklyMenu{return {week_start:week,status:'draft',version:0,slots:Array.from({length:7},(_,day)=>(['breakfast','lunch','dinner'] as Meal[]).map(meal=>({day,meal,cutoff:{breakfast:'06:00',lunch:'10:00',dinner:'16:00'}[meal],options:[]}))).flat()}}
export function emptyOption():MealOption{return {id:crypto.randomUUID(),name:'',foods:[],ingredients:[],allergens:[],tags:[],texture:'normal',capacity:100,notes:''}}
export function tokenList(value:string){return [...new Set(value.split(/[,，、;；\n]/).map(v=>v.trim()).filter(Boolean))]}
export function copyWeek(menu:WeeklyMenu,week:string):WeeklyMenu{return {...menu,id:undefined,week_start:week,status:'draft',version:0,slots:menu.slots.map(s=>({...s,options:s.options.map(o=>({...o,id:crypto.randomUUID(),foods:[...o.foods],ingredients:[...o.ingredients],allergens:[...o.allergens],tags:[...o.tags]}))}))}}
export function referenceMenu(week:string):WeeklyMenu{
 const result=emptyMenu(week)
 const recipes=[
  {name:'清蒸鱼搭配',foods:['米饭','清蒸鱼','炖冬瓜'],ingredients:['大米','鱼','冬瓜'],allergens:['鱼']},
  {name:'鸡肉豆腐搭配',foods:['米饭','鸡肉炖豆腐','清炒青菜'],ingredients:['大米','鸡肉','大豆','青菜'],allergens:['大豆']},
  {name:'番茄牛肉搭配',foods:['米饭','番茄炖牛肉','蒸南瓜'],ingredients:['大米','番茄','牛肉','南瓜'],allergens:[]},
  {name:'冬瓜瘦肉搭配',foods:['米饭','冬瓜炖猪肉','炒白菜'],ingredients:['大米','冬瓜','猪肉','白菜'],allergens:[]},
 ]
 const offset=Math.floor(new Date(week+'T12:00:00').getTime()/604800000)%recipes.length
 result.slots.forEach(s=>{s.options=[0,1].map(n=>{
  const o=emptyOption()
  if(s.meal==='breakfast')return {...o,name:n?'小米粥鸡蛋搭配':'馒头豆浆搭配',foods:n?['小米粥','蒸蛋','蒸南瓜']:['馒头','豆浆','拌青菜'],ingredients:n?['小米','鸡蛋','南瓜']:['小麦','大豆','青菜'],allergens:n?['鸡蛋']:['小麦','大豆']}
  return {...o,...recipes[(s.day+offset+n+(s.meal==='dinner'?1:0))%recipes.length]}
 })})
 return result
}
export interface GenerateMenuRequest {
 week_start:string;version:number;options_per_meal:number;available_ingredients:string[];kitchen_notes:string;budget_notes:string;season:string;capacity_per_option:number|null;avoid_previous:boolean;acknowledge_pending:boolean
}
export interface RecipeReference {status:'success'|'disabled';provider:string;count:number;recipes:{id:string;name:string;category:string;ingredients:string[];steps:string[];source_url:string|null}[]}
export interface GeneratedMenu {
 recipe_reference?:RecipeReference;
 menu:WeeklyMenu;coverage:Coverage;summary:{in_care:number;reviewed_count:number;pending_count:number};warnings:string[];repetition:{same_as_previous:number;options:number;repeated_within_week:number;previous_available:boolean};repairs:number;model:string;saved:false;published:false;context_changed:boolean
}
export interface ProfileReading {suggestion:Omit<Profile,'version'|'resident_version'>;evidence:{field:string;value:string;source:string;quote:string}[];questions:string[];rejected_count:number;model:string;saved:false;resident_version:number;resident_id:string}
export const mealsApi={
 recipeSource:()=>request<{enabled:boolean;configured:boolean;provider:string}>('/meals/recipe-source'),
 readProfile:(id:string)=>request<ProfileReading>(`/meals/profiles/${id}/read`,{method:'POST'},180_000),
 generate:(data:GenerateMenuRequest)=>request<GeneratedMenu>('/meals/generate',{method:'POST',body:JSON.stringify(data)},900_000),
 requirements:()=>request<{items:Requirement[]}>('/meals/requirements'),
 profile:(id:string,data:Profile)=>request<Profile>(`/meals/profiles/${id}`,{method:'PUT',body:JSON.stringify(data)}),
 menu:(week:string)=>request<{menu:WeeklyMenu|null}>(`/meals/menus?week_start=${week}`),
 save:(menu:WeeklyMenu)=>request<WeeklyMenu>('/meals/menus',{method:'PUT',body:JSON.stringify({week_start:menu.week_start,slots:menu.slots,version:menu.version})}),
 coverage:(id:string)=>request<Coverage>(`/meals/menus/${id}/coverage`),
 publish:(id:string,version:number,acknowledge_pending:boolean)=>request<WeeklyMenu>(`/meals/menus/${id}/publish`,{method:'POST',body:JSON.stringify({version,acknowledge_pending})}),
 mine:(week:string)=>request<MyMeals>(`/meals/mine?week_start=${week}`),
 choose:(menu_id:string,slot:MySlot,option_id:string)=>request('/meals/mine',{method:'PUT',body:JSON.stringify({menu_id,day:slot.day,meal:slot.meal,option_id,version:slot.selection?.version||0})}),
 kitchen:(id:string,date:string,meal:Meal)=>request<Kitchen>(`/meals/menus/${id}/kitchen?meal_date=${date}&meal=${meal}`),
}
