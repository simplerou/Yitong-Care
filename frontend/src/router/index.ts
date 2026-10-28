import { createRouter, createWebHashHistory } from 'vue-router'
import { routes } from './routes'
export const router = createRouter({ history: createWebHashHistory(), routes, scrollBehavior: () => ({ top: 0 }) })
router.afterEach(to => { document.title = to.meta.title ? `${to.meta.title} · 颐养通` : '颐养通 · 智能养老服务平台' })
