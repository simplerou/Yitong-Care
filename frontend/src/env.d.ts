/// <reference types="vite/client" />
import type AppIcon from './components/common/AppIcon.vue'
declare module 'vue' { export interface GlobalComponents { AppIcon: typeof AppIcon } }
export {}
