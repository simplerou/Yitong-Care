import { routes } from '../router/routes'
export const menuGroups = ['工作台', '智能体服务', '知识库与 RAG', '运营管理'].map(title => ({ title, items: routes.filter(r => r.meta?.group === title) }))
