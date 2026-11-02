<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
import DefaultLayout from './layouts/DefaultLayout.vue'
import ToastHost from './components/common/ToastHost.vue'
import DialogHost from './components/common/DialogHost.vue'
</script>
<template><RouterView v-if="route.meta.layout === 'auth'"/><DefaultLayout v-else/><DialogHost/><ToastHost/></template>
