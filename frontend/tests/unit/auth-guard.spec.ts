import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authGuard } from '../../src/router/authGuard'
import { authApi, sessionToken, clearSession } from '../../src/api/auth'
vi.mock('../../src/api/auth', () => ({authApi:{me:vi.fn()}, sessionToken:vi.fn(), clearSession:vi.fn()}))
beforeEach(() => vi.resetAllMocks())
describe('登录路由保护', () => {
  it('登录和注册页面公开', async () => {
    expect(await authGuard({meta:{layout:'auth'}})).toBe(true)
    expect(authApi.me).not.toHaveBeenCalled()
  })
  it('普通账号不能通过直接地址进入管理员页面', async () => {
    vi.mocked(sessionToken).mockReturnValue('token')
    vi.mocked(authApi.me).mockResolvedValue({id:'1',name:'用户',role:'user'})
    expect(await authGuard({meta:{adminOnly:true}})).toEqual({name:'home'})
    vi.mocked(authApi.me).mockResolvedValue({id:'2',name:'管理员',role:'admin'})
    expect(await authGuard({meta:{adminOnly:true}})).toBe(true)
  })
  it('未登录的直接地址访问返回登录页', async () => {
    vi.mocked(sessionToken).mockReturnValue('')
    expect(await authGuard({meta:{}})).toEqual({name:'login'})
  })
  it('只有服务端认可的会话可以进入功能页面', async () => {
    vi.mocked(sessionToken).mockReturnValue('saved-token')
    vi.mocked(authApi.me).mockResolvedValue({id:'1',name:'测试'})
    expect(await authGuard({meta:{}})).toBe(true)
    vi.mocked(authApi.me).mockRejectedValue(new Error('expired'))
    expect(await authGuard({meta:{}})).toEqual({name:'login'})
    expect(clearSession).toHaveBeenCalled()
  })
})
