import type { RouteRecordRaw } from 'vue-router'
import { agents } from '../config/agents'
export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'login', component: () => import('../views/auth/AuthView.vue'), meta: { title: '登录', layout: 'auth' } },
  { path: '/register', name: 'register', component: () => import('../views/auth/AuthView.vue'), meta: { title: '注册', layout: 'auth' } },
  { path: '/home', name: 'home', component: () => import('../views/home/HomeView.vue'), meta: { title: '首页工作台', group: '工作台', icon: 'home' } },
  { path: '/residents', name: 'residents', component: () => import('../views/residents/ResidentListView.vue'), meta: { title: '老人档案', group: '老人照护', icon: 'clipboard' } },
  { path: '/residents/new', name: 'resident-new', component: () => import('../views/residents/ResidentDetailView.vue'), meta: { title: '新建档案', adminOnly: true } },
  { path: '/residents/:id', name: 'resident-detail', component: () => import('../views/residents/ResidentDetailView.vue'), meta: { title: '档案详情' } },
  ...agents.map(a => ({ path: `/agent/${a.id}`, name: `agent-${a.id}`, component: () => import('../views/agent/AgentChatView.vue'), props: { id: a.id }, meta: { title: a.name, group: '智能体服务', icon: a.icon, color: a.color, tint: a.tint } })),
  { path: '/kb', name: 'kb', component: () => import('../views/knowledge/DocumentListView.vue'), meta: { title: '知识库管理', group: '知识库与 RAG', adminOnly: true, icon: 'book' } },
  { path: '/chunk', name: 'chunk', component: () => import('../views/knowledge/ChunkView.vue'), meta: { title: '文本切块', group: '知识库与 RAG', adminOnly: true, icon: 'scissors' } },
  { path: '/vector', name: 'vector', component: () => import('../views/knowledge/VectorizeView.vue'), meta: { title: '向量入库', group: '知识库与 RAG', adminOnly: true, icon: 'database' } },
  { path: '/search', name: 'search', component: () => import('../views/retrieval/RetrievalView.vue'), meta: { title: '向量检索', group: '知识库与 RAG', adminOnly: true, icon: 'search' } },
  { path: '/records', name: 'records', component: () => import('../views/retrieval/RetrievalLogsView.vue'), meta: { title: '检索记录', group: '知识库与 RAG', adminOnly: true, icon: 'history' } },
  { path: '/services', name: 'services', component: () => import('../views/ops/ServiceRecordsView.vue'), meta: { title: '服务记录', group: '运营管理', adminOnly: true, icon: 'clipboard' } },
  { path: '/:pathMatch(.*)*', redirect: '/home' }
]
