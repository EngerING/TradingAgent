import type { RouteRecordRaw } from 'vue-router'
export const routes:RouteRecordRaw[]=[
 {path:'/',component:()=>import('../modules/dashboard/HomePage.vue')},
 {path:'/trading',component:()=>import('../modules/trading/TradingPage.vue')},
 {path:'/experimentos',component:()=>import('../modules/experiments/ExperimentsPage.vue')},
 {path:'/aggressive-growth',component:()=>import('../modules/aggressive-growth/AggressiveGrowthPage.vue')},
 {path:'/r20/configuracion',component:()=>import('../modules/r20-configuration/R20ConfigurationPage.vue')},
 {path:'/operaciones',component:()=>import('../modules/trading/OperationsPage.vue')},
 {path:'/mercado',component:()=>import('../modules/market/MarketPage.vue')},
 {path:'/sol',component:()=>import('../modules/sol/SolPage.vue')},
 {path:'/research',component:()=>import('../modules/research/ResearchPage.vue')},
 {path:'/reportes',component:()=>import('../modules/experiments/ReportsPage.vue')},
 {path:'/configuracion',component:()=>import('../modules/system/ConfigurationPage.vue')},
 {path:'/:pathMatch(.*)*',redirect:'/'},
]
