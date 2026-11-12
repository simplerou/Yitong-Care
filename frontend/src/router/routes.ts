import type { RouteRecordRaw } from 'vue-router'
export const routes:RouteRecordRaw[]=[
 {path:'/',redirect:'/login'},
 {path:'/login',name:'login',component:()=>import('../views/auth/AuthView.vue'),meta:{title:'登录',layout:'auth'}},
 {path:'/register',name:'register',component:()=>import('../views/auth/AuthView.vue'),meta:{title:'员工岗位申请',layout:'auth'}},
 {path:'/application-status',name:'application-status',component:()=>import('../views/auth/ApplicationStatusView.vue'),meta:{title:'岗位申请状态',layout:'account'}},
 {path:'/operations',name:'operations',component:()=>import('../views/operations/OperationsView.vue'),meta:{title:'六岗位 Agent 工作台',icon:'shield'}},
 {path:'/account-reviews',name:'account-reviews',component:()=>import('../views/auth/AccountReviewsView.vue'),meta:{title:'注册审核',roles:['admin']}},
 {path:'/caregivers',name:'caregivers',component:()=>import('../views/residents/CaregiversView.vue'),meta:{title:'护工账号与分配',roles:['nursing']}},
 {path:'/residents',name:'residents',component:()=>import('../views/residents/ResidentListView.vue'),meta:{title:'老人档案',roles:['nursing','medical','user']}},
 {path:'/residents/new',name:'resident-new',component:()=>import('../views/residents/ResidentDetailView.vue'),meta:{title:'新建老人档案',roles:['nursing']}},
 {path:'/residents/:id/meals',name:'resident-meals',component:()=>import('../views/meals/MyMealsView.vue'),meta:{title:'每日餐食',roles:['nursing','user']}},
 {path:'/residents/:id',name:'resident-detail',component:()=>import('../views/residents/ResidentDetailView.vue'),meta:{title:'档案详情',roles:['nursing','medical','user']}},
 {path:'/home',redirect:'/operations'},
 {path:'/:pathMatch(.*)*',redirect:'/operations'},
]
