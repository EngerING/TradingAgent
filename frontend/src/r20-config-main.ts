import { createApp } from 'vue'
import { createPinia } from 'pinia'
import R20ConfigurationLab from './R20ConfigurationLab.vue'
document.documentElement.style.background='#0b1922'
document.body.style.margin='0'
createApp(R20ConfigurationLab).use(createPinia()).mount('#app')
