import { expect,it } from 'vitest'
import { safeWebUrl } from '../../src/api/chat'
it('网页引用只允许 HTTP 和 HTTPS 链接',()=>{
 for(const url of ['javascript:alert(1)','data:text/html,test','file:///tmp/test','not a URL'])expect(safeWebUrl(url)).toBeNull()
 expect(safeWebUrl('https://mz.hangzhou.gov.cn/policy')).toBe('https://mz.hangzhou.gov.cn/policy')
})
