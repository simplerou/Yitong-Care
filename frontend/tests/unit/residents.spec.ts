import { beforeEach, expect, it, vi } from 'vitest'
import { residentsApi, emptyResident, bindingApi } from '../../src/api/residents'
import { request } from '../../src/api/http'
vi.mock('../../src/api/http',()=>({request:vi.fn()}))
beforeEach(()=>vi.clearAllMocks())
it('新建档案不伪造健康或联系人资料',()=>{
 const form=emptyResident()
 expect(form.allergies).toBe('');expect(form.birth_date).toBeNull();expect(form.care_level).toBe('未评估');expect(form.assigned_account_ids).toEqual([])
})
it('保存修改携带读取时的版本及人工修改原因',async()=>{
 const form={...emptyResident(),name:'测试',source:'资料核对',assigned_account_ids:['worker']}
 await residentsApi.update('resident',form,2,'核对过敏信息')
 const options=vi.mocked(request).mock.calls[0][1]!
 expect(JSON.parse(String(options.body))).toEqual({...form,version:2,change_reason:'核对过敏信息'})
})
it('姓名筛选中的特殊字符不会变成额外请求参数',async()=>{
 await residentsApi.list('张&status=discharged','in_care',2)
 const url=String(vi.mocked(request).mock.calls[0][0])
 const params=new URLSearchParams(url.split('?')[1])
 expect(params.get('q')).toBe('张&status=discharged');expect(params.get('status')).toBe('in_care');expect(params.get('page')).toBe('2')
})

it('本人档案由登录凭证决定，不提交可伪造的老人ID',async()=>{
 await bindingApi.mine()
 expect(request).toHaveBeenCalledWith('/residents/me')
})
it('账号绑定携带版本与身份核对说明，并支持显式解绑',async()=>{
 await bindingApi.set('elder','account',3,'当面核对')
 expect(JSON.parse(String(vi.mocked(request).mock.calls[0][1]?.body))).toEqual({account_id:'account',version:3,reason:'当面核对'})
 await bindingApi.set('elder',null,4,'本人申请解绑')
 expect(JSON.parse(String(vi.mocked(request).mock.calls[1][1]?.body)).account_id).toBeNull()
})
