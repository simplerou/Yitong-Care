import { beforeEach,expect,it,vi } from 'vitest'
import { copyWeek,monday,shiftDay,referenceMenu,mealsApi,tokenList,type MySlot } from '../../src/api/meals'
import { request } from '../../src/api/http'
vi.mock('../../src/api/http',()=>({request:vi.fn()}))
beforeEach(()=>vi.clearAllMocks())
it('跨年日期定位周一并正确计算周末',()=>{
 expect(monday('2027-01-01')).toBe('2026-12-28')
 expect(shiftDay('2026-12-28',6)).toBe('2027-01-03')
})
it('参考草稿完整覆盖7天三餐，每餐有两套实际菜品',()=>{
 const menu=referenceMenu('2030-01-07')
 expect(menu.slots).toHaveLength(21)
 expect(new Set(menu.slots.map(s=>s.day+':'+s.meal)).size).toBe(21)
 expect(menu.slots.every(s=>s.options.length===2&&s.options.every(o=>o.foods.length>0&&o.ingredients.length>0))).toBe(true)
})
it('复制下一周生成独立草稿，修改不会影响原发布菜单',()=>{
 const old={...referenceMenu('2030-01-07'),id:'old',status:'published' as const,version:3}
 const next=copyWeek(old,'2030-01-14')
 expect(next.status).toBe('draft');expect(next.version).toBe(0);expect(next.id).toBeUndefined()
 expect(next.slots[0].options[0].id).not.toBe(old.slots[0].options[0].id)
 next.slots[0].options[0].foods.push('新增菜')
 expect(old.slots[0].options[0].foods).not.toContain('新增菜')
})
it('保存菜单只提交允许字段，不能通过请求自设已发布状态',async()=>{
 const menu=referenceMenu('2030-01-07');menu.status='published';menu.id='old'
 await mealsApi.save(menu)
 const body=JSON.parse(String(vi.mocked(request).mock.calls[0][1]?.body))
 expect(body.status).toBeUndefined();expect(body.id).toBeUndefined();expect(body.slots).toHaveLength(21)
})
it('选餐提交原版本但不提交可伪造的老人ID',async()=>{
 const slot={...referenceMenu('2030-01-07').slots[0],date:'2030-01-07',closed:false,selection:{option_id:'old',version:2,needs_review:false}} as MySlot
 await mealsApi.choose('menu',slot,'choice')
 const body=JSON.parse(String(vi.mocked(request).mock.calls[0][1]?.body))
 expect(body).toEqual({menu_id:'menu',day:0,meal:'breakfast',option_id:'choice',version:2})
})
it('食材输入去空白去重，保留明确词项',()=>{
 expect(tokenList('鸡蛋， 大豆、鸡蛋;鱼\n')).toEqual(['鸡蛋','大豆','鱼'])
})

it('智能生成提交厨房约束和菜单版本，不提交老人身份或发布标记',async()=>{
 await mealsApi.generate({week_start:'2030-01-07',version:2,options_per_meal:2,available_ingredients:['大米','鸡肉'],kitchen_notes:'蒸炖为主',budget_notes:'使用时令食材',season:'冬季',capacity_per_option:90,avoid_previous:true,acknowledge_pending:false})
 const [path,options,timeout]=vi.mocked(request).mock.calls[0]
 const data=JSON.parse(String(options?.body))
 expect(path).toBe('/meals/generate');expect(timeout).toBe(900_000)
 expect(data.version).toBe(2);expect(data.available_ingredients).toEqual(['大米','鸡肉'])
 expect(data.resident_id).toBeUndefined();expect(data.published).toBeUndefined();expect(data.status).toBeUndefined()
})
it('生成失败不会静默使用参考模板冒充AI结果',async()=>{
 vi.mocked(request).mockRejectedValueOnce(new Error('模型超时'))
 await expect(mealsApi.generate({week_start:'2030-01-07',version:0,options_per_meal:2,available_ingredients:[],kitchen_notes:'',budget_notes:'',season:'',capacity_per_option:null,avoid_previous:true,acknowledge_pending:true})).rejects.toThrow('模型超时')
 expect(request).toHaveBeenCalledTimes(1)
})
