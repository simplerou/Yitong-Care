import {beforeEach,it,expect,vi} from 'vitest'
import {reviews} from '../../src/api/accountReviews'
import {request} from '../../src/api/http'
vi.mock('../../src/api/http',()=>({request:vi.fn()}))
beforeEach(()=>vi.clearAllMocks())
it('审核携带版本和资质，不提交审核人身份',async()=>{
 const data={version:1,action:'approve',role:'medical',qualification:'已核实',valid_until:'2099-01-01'}
 await reviews.decide('employee',data)
 expect(request).toHaveBeenCalledWith('/account-reviews/employee/decision',{method:'POST',body:JSON.stringify(data)})
})
it('重新申请仅携带申请信息，不开放账号角色或状态字段',async()=>{
 await reviews.reapply({version:2,requested_role:'finance',application_note:'入职安排'})
 const body=JSON.parse(String(vi.mocked(request).mock.calls[0][1]?.body))
 expect(body).not.toHaveProperty('status');expect(body).not.toHaveProperty('role')
})
it('审核记录按结果和页码查询，不提交账号身份',async()=>{
 await reviews.history('reject',2)
 expect(request).toHaveBeenCalledWith('/account-reviews/history?result=reject&page=2')
})
