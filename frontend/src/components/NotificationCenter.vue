<script setup lang="ts">
import { ref } from 'vue'
import { Bell } from '@lucide/vue'
import { useNotificationStore } from '../stores'
const notifications = useNotificationStore(); const show = ref(false)
</script>
<template><div class="notifications"><button class="icon-button" aria-label="Notificaciones" :aria-expanded="show" @click="show = !show"><Bell :size="19" /><span v-if="notifications.items.length" class="notification-dot"></span></button><div v-if="show" class="notification-popover"><h3>Actividad y condiciones</h3><p v-if="!notifications.items.length" class="muted">Sin eventos disponibles.</p><div v-for="n in notifications.items" :key="n.id" :class="['notification-item', n.kind]"><span>{{ n.kind === 'warning' ? '!' : '·' }}</span><p>{{ n.text }}</p></div></div></div></template>
