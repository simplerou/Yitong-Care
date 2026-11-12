<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import AppSelect from '../../components/common/AppSelect.vue'
import { authApi } from '../../api/auth'
import { useRouter } from 'vue-router'
import { useRoute } from 'vue-router'
const route = useRoute(), router = useRouter(), busy = ref(false)
const registering = computed(() => route.name === 'register')
const form = reactive({ name: '', phone: '', password: '', confirm: '', requested_role:'user',application_note:'' })
const errors = reactive<Record<string, string>>({})
const visible = ref(false), confirmVisible = ref(false), notice = ref(route.query.reason==='review_changed'?'审核状态可能有更新或登录已过期，请重新登录。':'')
const services = [
  { icon: 'home', name: '院长工作台', text: '统筹运营，核对与审批' },
  { icon: 'pill', name: '医务室', text: '查证用药，守住安全关' },
  { icon: 'leaf', name: '食堂', text: '按需配餐，确认备餐' },
  { icon: 'shield', name: '护理部', text: '安排班次，审核照护' },
  { icon: 'doc', name: '财务部', text: '核对工时，清晰核薪' },
  { icon: 'heart', name: '护工', text: '完成任务，及时上报异常' },
]

watch(registering, () => {
  form.password = ''; form.confirm = ''; visible.value = false; confirmVisible.value = false; notice.value = ''
  Object.keys(errors).forEach(key => delete errors[key])
})
async function submit() {
  if (busy.value) return
  Object.keys(errors).forEach(key => delete errors[key]); notice.value = ''
  if (registering.value && !form.name.trim()) errors.name = '请填写姓名'
  if (!/^1[3-9]\d{9}$/.test(form.phone.trim())) errors.phone = '请输入正确的 11 位手机号码'
  if (!form.password) errors.password = '请输入密码'
  else if (registering.value && (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/\d/.test(form.password))) errors.password = '请使用至少 8 位的字母和数字组合'
  if (registering.value && form.confirm !== form.password) errors.confirm = '两次输入的密码不一致'
  if (Object.keys(errors).length) {
    await nextTick(); document.getElementById('auth-' + Object.keys(errors)[0])?.focus(); return
  }
  busy.value = true
  try {
    if (registering.value) {
      await authApi.register({ name: form.name.trim(), phone: form.phone.trim(), password: form.password,requested_role:form.requested_role,application_note:form.application_note.trim() })
      await authApi.login(form.phone.trim(),form.password)
      form.password='';form.confirm=''
      await router.replace('/application-status')
    } else {
      const account = await authApi.login(form.phone.trim(), form.password)
      if(account.role==='resident'){await authApi.logout();throw new Error('老人账号端已停用，请使用护工账号管理老人资料。')}
      form.password = ''
      window.location.hash = account.status&&account.status!=='active'?'/application-status':'/operations'
      window.location.reload()
    }
  } catch (error) { notice.value = error instanceof Error ? error.message : '请求失败，请稍后重试' }
  finally { busy.value = false }

}
</script>
<template>
  <div class="auth-page">
    <header class="auth-header">
      <RouterLink to="/login" class="auth-brand" aria-label="禾龄通登录"><span class="auth-logo"><AppIcon name="heart" :size="27" /></span><span><b>禾龄通</b><small>HELING CARE</small></span></RouterLink>
      <span class="auth-back">养老院智能照护协作平台</span>
    </header>
    <main class="auth-main">
      <section class="auth-story" aria-labelledby="care-heading">
        <div class="auth-eyebrow"><span></span> 多岗协作 · 照护相连</div>
        <h1 id="care-heading">让协作，更有序。<br><span>让照护，更安心。</span></h1>
        <p class="auth-intro">面向养老院的多岗位协作，<br>串联医护、配餐与执行，让每一份照护有据可循。</p>
        <div class="auth-services"><div v-for="service in services" :key="service.name" class="auth-service"><span><AppIcon :name="service.icon" :size="22" /></span><div><b>{{ service.name }}</b><p>{{ service.text }}</p></div></div></div>
        <div class="auth-story-note"><AppIcon name="heart" :size="18" /> 专业建议有依据，照护执行有记录。</div>
      </section>
      <section class="auth-form-card" :aria-labelledby="registering ? 'register-heading' : 'login-heading'">
        <div class="auth-card-top"><span class="auth-card-symbol"><AppIcon :name="registering ? 'smile' : 'home'" :size="25" /></span><span>养老院照护服务，从这里开始</span></div>
        <h2 :id="registering ? 'register-heading' : 'login-heading'">{{ registering ? '员工岗位申请' : '欢迎回来' }}</h2>
        <p class="auth-subtitle">{{ registering ? '选择申请岗位，由院长核实后开通业务权限。' : '登录岗位工作台，协同处理院内照护事务。' }}</p>
        <div class="auth-tabs" role="group" aria-label="当前账号页面"><span :aria-current="!registering ? 'page' : undefined">账号登录</span><span :aria-current="registering ? 'page' : undefined">注册账号</span></div>
        <form novalidate :aria-busy="busy" @submit.prevent="submit"><fieldset :disabled="busy" class="auth-fieldset">
          <div v-if="registering" class="auth-field"><label for="auth-name">姓名</label><input id="auth-name" v-model="form.name" autocomplete="nickname" maxlength="30" placeholder="请输入姓名" :aria-invalid="!!errors.name" :aria-describedby="errors.name ? 'error-name' : undefined"><p v-if="errors.name" id="error-name" class="auth-error">{{ errors.name }}</p></div>
          <div class="auth-field"><label for="auth-phone">手机号码</label><input id="auth-phone" v-model="form.phone" type="tel" inputmode="tel" autocomplete="username" maxlength="11" placeholder="请输入手机号码" :aria-invalid="!!errors.phone" :aria-describedby="errors.phone ? 'error-phone' : undefined"><p v-if="errors.phone" id="error-phone" class="auth-error">{{ errors.phone }}</p></div>
          <div class="auth-field"><label for="auth-password">{{ registering ? '设置密码' : '登录密码' }}</label><div class="auth-password"><input id="auth-password" v-model="form.password" :type="visible ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" :placeholder="registering ? '至少 8 位，包含字母和数字' : '请输入密码'" :aria-invalid="!!errors.password" :aria-describedby="errors.password ? 'error-password' : undefined"><button type="button" :aria-pressed="visible" aria-controls="auth-password" :aria-label="visible ? '隐藏密码' : '显示密码'" :title="visible ? '隐藏密码' : '显示密码'" @click="visible = !visible"><AppIcon :name="visible ? 'eye-off' : 'eye'" :size="20" /></button></div><p v-if="errors.password" id="error-password" class="auth-error">{{ errors.password }}</p></div>
          <div v-if="registering" class="auth-field"><label for="auth-confirm">确认密码</label><div class="auth-password"><input id="auth-confirm" v-model="form.confirm" :type="confirmVisible ? 'text' : 'password'" autocomplete="new-password" placeholder="请再次输入密码" :aria-invalid="!!errors.confirm" :aria-describedby="errors.confirm ? 'error-confirm' : undefined"><button type="button" :aria-pressed="confirmVisible" aria-controls="auth-confirm" :aria-label="confirmVisible ? '隐藏确认密码' : '显示确认密码'" :title="confirmVisible ? '隐藏确认密码' : '显示确认密码'" @click="confirmVisible = !confirmVisible"><AppIcon :name="confirmVisible ? 'eye-off' : 'eye'" :size="20" /></button></div><p v-if="errors.confirm" id="error-confirm" class="auth-error">{{ errors.confirm }}</p></div>
          <div v-if="registering" class="auth-field"><label for="auth-role">申请岗位</label><AppSelect id="auth-role" v-model="form.requested_role" class="select" :disabled="busy"><option value="user">护工</option><option value="medical">医务室</option><option value="kitchen">食堂</option><option value="nursing">护理部</option><option value="finance">财务部</option></AppSelect><p class="auth-role-note">院长核实后开通权限；医务室、护理部需额外核实资质。</p></div>
          <div v-if="registering" class="auth-field"><label for="auth-application-note">申请说明（选填）</label><textarea id="auth-application-note" v-model="form.application_note" rows="2" maxlength="500" placeholder="例如：入职部门、岗位安排，方便院长核对。"></textarea></div>
          <button class="auth-submit" type="submit">{{ busy ? '正在提交…' : registering ? '提交岗位申请' : '登录' }}<AppIcon name="arrow" :size="19" /></button>
          <p v-if="notice" class="auth-notice" role="status">{{ notice }}</p>
        </fieldset></form>
        <p class="auth-switch">{{ registering ? '已经有账号？' : '还没有账号？' }}<RouterLink :to="registering ? '/login' : '/register'">{{ registering ? '立即登录' : '立即注册' }}</RouterLink></p>
        <div class="auth-preview"><AppIcon name="info" :size="16" /><span>请妥善保管账号，切勿向他人透露密码。</span></div>
      </section>
    </main>
    <footer class="auth-footer"><span>禾龄通 · 养老院智能照护协作平台</span><span>各司其职，让照护紧密相连</span></footer>
  </div>
</template>
<style scoped>
.auth-page { --auth-muted: #53647e; --auth-error: #b4232b; min-height: 100dvh; background: radial-gradient(ellipse at 8% 46%, var(--brand-100) 0, transparent 53%), var(--bg); font-size: 16px; }
.auth-header { max-width: 1320px; margin: auto; padding: 28px 48px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.auth-brand { display: flex; align-items: center; gap: 12px; }.auth-logo { display: grid; place-items: center; width: 48px; height: 48px; background: var(--brand); color: var(--card); border-radius: 15px; box-shadow: var(--shadow-sm); }
.auth-brand b { display: block; font-size: 24px; letter-spacing: 3px; line-height: 1.2; }.auth-brand small { font-size: 10px; letter-spacing: 2px; color: var(--auth-muted); }.auth-back { display: flex; align-items: center; gap: 10px; min-height: 44px; color: var(--auth-muted); font-size: 14px; }
.auth-main { max-width: 1180px; margin: 28px auto 48px; padding: 0 32px; display: grid; grid-template-columns: 1fr 460px; gap: 80px; align-items: center; }
.auth-story { padding: 20px 0; }.auth-eyebrow { display: flex; align-items: center; gap: 10px; color: var(--brand-ink); font-size: 14px; font-weight: 600; letter-spacing: 2px; }.auth-eyebrow span { width: 7px; height: 7px; border-radius: 50%; background: var(--brand); }
.auth-story h1 { font-size: clamp(32px, 3.5vw, 46px); line-height: 1.45; letter-spacing: -1px; margin: 22px 0; }.auth-story h1 span { color: var(--brand); }.auth-intro { color: var(--auth-muted); line-height: 1.9; margin-bottom: 32px; }
.auth-services { display: grid; grid-template-columns: repeat(2, 1fr); gap: 25px 18px; }.auth-service { display: flex; align-items: center; gap: 12px; }.auth-service > span { width: 44px; height: 44px; display: grid; place-items: center; background: var(--card); color: var(--brand-deep); border-radius: 12px; border: 1px solid var(--line); }.auth-service b { font-size: 15px; }.auth-service p { font-size: 12px; color: var(--auth-muted); margin: 3px 0 0; }.auth-story-note { margin-top: 40px; border-top: 1px solid var(--line-2); padding-top: 23px; display: flex; gap: 10px; align-items: center; font-size: 14px; color: var(--auth-muted); }
.auth-form-card { padding: 32px 36px 24px; background: var(--card); border: 1px solid var(--line); border-radius: 24px; box-shadow: var(--shadow); }.auth-card-top { display: flex; align-items: center; gap: 12px; color: var(--auth-muted); font-size: 12px; }.auth-card-symbol { display: grid; place-items: center; width: 46px; height: 46px; background: var(--brand-50); color: var(--brand); border-radius: 14px; }.auth-form-card h2 { margin: 22px 0 6px; font-size: 29px; }.auth-subtitle { color: var(--auth-muted); font-size: 14px; margin: 0 0 24px; }.auth-tabs { display: grid; grid-template-columns: 1fr 1fr; background: var(--bg); border-radius: 10px; padding: 4px; margin-bottom: 24px; }.auth-tabs span { display: grid; place-items: center; min-height: 44px; border-radius: 8px; font-size: 15px; color: var(--auth-muted); }.auth-tabs span[aria-current] { color: var(--brand-deep); background: var(--card); box-shadow: var(--shadow-xs); font-weight: 600; }
.auth-fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }.auth-fieldset:disabled { opacity: .7; }
.auth-field { margin-bottom: 17px; }.auth-field label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 7px; }.auth-field input { width: 100%; min-width: 0; height: 49px; padding: 0 14px; border: 1px solid var(--line-2); border-radius: 9px; background: var(--card); font-size: 16px; }.auth-field input::placeholder { color: var(--auth-muted); font-size: 14px; }.auth-password { position: relative; }.auth-password input { padding-right: 54px; }.auth-password button { position: absolute; right: 4px; top: 2px; min-height: 44px; min-width: 44px; display: grid; place-items: center; border: none; background: transparent; color: var(--brand-deep); font-size: 13px; }.auth-field input[aria-invalid=true] { border-color: var(--auth-error); }.auth-error { margin: 5px 0 0; font-size: 13px; color: var(--auth-error); }
.auth-submit { width: 100%; min-height: 50px; border: none; border-radius: 10px; color: var(--card); background: var(--brand); display: flex; justify-content: center; align-items: center; gap: 12px; font-size: 16px; font-weight: 600; margin-top: 24px; transition: background 180ms; }.auth-submit:hover { background: var(--brand-deep); }.auth-switch { text-align: center; font-size: 14px; color: var(--auth-muted); margin: 22px 0; }.auth-switch a { display: inline-flex; align-items: center; min-height: 44px; color: var(--brand-deep); font-weight: 600; margin-left: 8px; }.auth-preview { border-top: 1px solid var(--line); padding-top: 16px; display: flex; gap: 8px; align-items: center; color: var(--auth-muted); font-size: 12px; }.auth-notice { background: var(--brand-50); color: var(--brand-ink); padding: 12px; border-radius: 8px; font-size: 14px; }.auth-footer { max-width: 1220px; padding: 0 24px 24px; margin: auto; display: flex; justify-content: space-between; gap: 12px; color: var(--auth-muted); font-size: 12px; }
.auth-page :is(a, button, input):focus-visible { outline: 3px solid var(--brand); outline-offset: 3px; }
@media (max-width: 1024px) { .auth-main { gap: 36px; grid-template-columns: 1fr 420px; }.auth-services { grid-template-columns: 1fr; gap: 16px; }.auth-service p { display: none; } }
@media (max-width: 760px) { .auth-header { padding: 20px; }.auth-main { display: block; padding: 0 20px; margin: 8px auto 32px; max-width: 500px; }.auth-story { padding: 8px 4px 24px; }.auth-story h1 { font-size: 30px; margin: 12px 0; }.auth-intro, .auth-services, .auth-story-note { display: none; }.auth-form-card { padding: 26px 24px 22px; border-radius: 20px; }.auth-footer { flex-direction: column; align-items: center; gap: 4px; }.auth-card-top { font-size: 12px; } }
@media (prefers-reduced-motion: reduce) { .auth-submit { transition: none; } }
</style>

<style scoped>.auth-role-note{font-size:12px;line-height:1.7;color:var(--auth-muted);margin-top:8px}.auth-field textarea{width:100%;box-sizing:border-box;border:1px solid var(--line);border-radius:10px;padding:12px;font:inherit;resize:vertical;min-height:72px;background:var(--card)}</style>
