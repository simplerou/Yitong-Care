import type { RouteRecordRaw } from 'vue-router'
import { agents } from '../config/agents'
export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'login', component: () => import('../views/auth/AuthView.vue'), meta: { title: '登录', layout: 'auth' } },
  { path: '/register', name: 'register', component: () => import('../views/auth/AuthView.vue'), meta: { title: '注册', layout: 'auth' } },
  { path: '/home', name: 'home', component: () => import('../views/home/HomeView.vue'), meta: { title: '首页工作台', group: '工作台', icon: 'home' } },
  { path: '/meal-management', name: 'meal-management', component: () => import('../views/meals/MealAdminView.vue'), meta: { title: '每周餐食管理', group: '院内餐食', adminOnly: true, icon: 'leaf' } },
  { path: '/my-meals', name: 'my-meals', component: () => import('../views/meals/MyMealsView.vue'), meta: { title: '我的餐食', group: '我的养老', residentOnly: true, icon: 'leaf' } },
  { path: '/my-profile', name: 'my-profile', component: () => import('../views/residents/MyProfileView.vue'), meta: { title: '我的健康档案', group: '我的养老', residentOnly: true, icon: 'heart' } },
  { path: '/residents', name: 'residents', component: () => import('../views/residents/ResidentListView.vue'), meta: { title: '健康档案', staffOnly: true, group: '老人照护', icon: 'clipboard' } },
  { path: '/residents/new', name: 'resident-new', component: () => import('../views/residents/ResidentDetailView.vue'), meta: { title: '新建档案', adminOnly: true } },
  { path: '/residents/:id', name: 'resident-detail', component: () => import('../views/residents/ResidentDetailView.vue'), meta: { title: '档案详情', staffOnly: true } },
  ...agents.map(a => ({ path: `/agent/${a.id}`, name: `agent-${a.id}`, component: () => import('../views/agent/AgentChatView.vue'), props: { id: a.id }, meta: { title: a.name, group: '智能体服务', icon: a.icon, color: a.color, tint: a.tint } })),
  { path: '/kb', name: 'kb', component: () => import('../views/knowledge/DocumentListView.vue'), meta: { title: '知识库管理', group: '知识库与 RAG', adminOnly: true, icon: 'book' } },
  { path: '/chunk', name: 'chunk', component: () => import('../views/knowledge/ChunkView.vue'), meta: { title: '文本切块', group: '知识库与 RAG', adminOnly: true, icon: 'scissors' } },
  { path: '/vector', name: 'vector', component: () => import('../views/knowledge/VectorizeView.vue'), meta: { title: '向量入库', group: '知识库与 RAG', adminOnly: true, icon: 'database' } },
  { path: '/search', name: 'search', component: () => import('../views/retrieval/RetrievalView.vue'), meta: { title: '向量检索', group: '知识库与 RAG', adminOnly: true, icon: 'search' } },
  { path: '/records', name: 'records', component: () => import('../views/retrieval/RetrievalLogsView.vue'), meta: { title: '检索记录', group: '知识库与 RAG', adminOnly: true, icon: 'history' } },
  { path: '/services', name: 'services', component: () => import('../views/ops/ServiceRecordsView.vue'), meta: { title: '服务记录', group: '运营管理', adminOnly: true, icon: 'clipboard' } },
  { path: '/:pathMatch(.*)*', redirect: '/home' }
]
