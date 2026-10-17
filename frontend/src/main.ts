import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { routes } from './app/routes'
import './style.css'
import './app/trading-app.css'
import './app/workspace-tokens.css'
const router = createRouter({ history: createWebHistory(), routes })
createApp(App).use(createPinia()).use(router).mount('#app')
