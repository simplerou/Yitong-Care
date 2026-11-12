import {it,expect} from 'vitest'
import {roleNavigation} from '../../src/config/roleNavigation'
import {roleTabs} from '../../src/config/roleTabs'
import {routes} from '../../src/router/routes'
it('正式导航只展示六岗位，院长没有护工分配或旧智能体',()=>{
 expect(Object.keys(roleNavigation).sort()).toEqual(['admin','finance','kitchen','medical','nursing','user'])
 expect(roleNavigation.admin.some(n=>n.path==='/caregivers')).toBe(false)
 expect(roleNavigation.nursing.some(n=>n.path==='/caregivers')).toBe(true)
 expect(routes.some(r=>r.path.startsWith('/agent/')||r.path==='/kb'||r.path==='/meal-management')).toBe(false)
})
it('各岗位只提供对应业务页签',()=>{
 expect(roleTabs.admin.map(t=>t.id)).toEqual(['dashboard','drafts'])
 expect(roleTabs.finance.some(t=>['profiles','inbox','executions'].includes(t.id))).toBe(false)
 expect(roleTabs.kitchen.some(t=>['profiles','staff','audit'].includes(t.id))).toBe(false)
 expect(roleNavigation.user.some(n=>n.task==='meal_swap')).toBe(true)
})
