import type { RouteRecordRaw } from 'vue-router'
import { agents } from '../config/agents'
export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/home' },
  { path: '/home', name: 'home', component: () => import('../views/home/HomeView.vue'), meta: { title: '首页工作台', group: '工作台', icon: 'home' } },
  ...agents.map(a => ({ path: `/agent/${a.id}`, name: `agent-${a.id}`, component: () => import('../views/agent/AgentChatView.vue'), props: { id: a.id }, meta: { title: a.name, group: '智能体服务', icon: a.icon, color: a.color, tint: a.tint } })),
  { path: '/kb', name: 'kb', component: () => import('../views/knowledge/DocumentListView.vue'), meta: { title: '知识库管理', group: '知识库与 RAG', icon: 'book' } },
  { path: '/chunk', name: 'chunk', component: () => import('../views/knowledge/ChunkView.vue'), meta: { title: '文本切块', group: '知识库与 RAG', icon: 'scissors' } },
  { path: '/vector', name: 'vector', component: () => import('../views/knowledge/VectorizeView.vue'), meta: { title: '向量入库', group: '知识库与 RAG', icon: 'database' } },
  { path: '/search', name: 'search', component: () => import('../views/retrieval/RetrievalView.vue'), meta: { title: '向量检索', group: '知识库与 RAG', icon: 'search' } },
  { path: '/records', name: 'records', component: () => import('../views/retrieval/RetrievalLogsView.vue'), meta: { title: '检索记录', group: '知识库与 RAG', icon: 'history' } },
  { path: '/services', name: 'services', component: () => import('../views/ops/ServiceRecordsView.vue'), meta: { title: '服务记录', group: '运营管理', icon: 'clipboard' } },
  { path: '/:pathMatch(.*)*', redirect: '/home' }
]
