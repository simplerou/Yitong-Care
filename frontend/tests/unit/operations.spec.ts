import {beforeEach,it,expect,vi} from 'vitest'
import {ops} from '../../src/api/operations'
import {request} from '../../src/api/http'
vi.mock('../../src/api/http',()=>({request:vi.fn()}))
beforeEach(()=>vi.clearAllMocks())
it('岗位身份由服务端解析，客户端不提交角色卡',async()=>{await ops.identity();expect(request).toHaveBeenCalledWith('/operations/identity')})
it('Supervisor请求仅传业务任务与严格输入，不传账号身份',async()=>{await ops.run('incident',{resident_id:'assigned',severity:'routine',observation:'照护观察'},false);const [path,options]=vi.mocked(request).mock.calls[0];expect(path).toBe('/operations/run');const body=JSON.parse(String(options?.body));expect(body.task).toBe('incident');expect(body).not.toHaveProperty('account_id');expect(body).not.toHaveProperty('role')})
it('审批携带版本而不伪造审批人',async()=>{await ops.post('drafts/draft/decision',{version:3,action:'approve',note:'已核对'});expect(JSON.parse(String(vi.mocked(request).mock.calls[0][1]?.body))).toEqual({version:3,action:'approve',note:'已核对'})})
