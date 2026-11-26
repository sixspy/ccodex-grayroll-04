import { api } from "../api.js";
const { ref, onMounted } = Vue;
export const CohortsView = {
  setup() {
    const items = ref([]); const members = ref([]); const rejections = ref([]);
    const cohortId = ref(4);
    const memberForm = ref({ subject_key: "s-dual" });
    const cohortForm = ref({ code: "mx_dual_c", title: "互斥人群 C", mutex_group: "mx-dual", note: "" });
    const err = ref(""); const msg = ref("");
    async function reload() {
      items.value = (await api("/api/cohorts")).items || [];
      rejections.value = (await api("/api/cohorts/mutex/rejections")).items || [];
      await loadMembers();
    }
    async function loadMembers() {
      members.value = (await api(`/api/cohorts/${cohortId.value}/members`)).items || [];
    }
    async function addMember() {
      err.value = ""; msg.value = "";
      try {
        const res = await api(`/api/cohorts/${cohortId.value}/members`, { method: "POST", body: JSON.stringify(memberForm.value) });
        msg.value = `已入册（${res.mode}）`;
        await reload();
      } catch (e) { err.value = e.message || String(e); await reload(); }
    }
    async function createCohort() {
      err.value = ""; msg.value = "";
      try {
        await api("/api/cohorts", { method: "POST", body: JSON.stringify(cohortForm.value) });
        msg.value = "人群已创建"; await reload();
      } catch (e) { err.value = e.message || String(e); }
    }
    onMounted(reload);
    return { items, members, rejections, cohortId, memberForm, cohortForm, err, msg, reload, loadMembers, addMember, createCohort };
  },
  template: `
  <div class="grid">
    <div class="panel span-5">
      <h2>人群</h2>
      <p class="hint">互斥组内同一主体只能挂一册：第二挂正式成员册零增、拒写（甲路径）。</p>
      <table><thead><tr><th>码</th><th>标题</th><th>人数</th><th>互斥组</th></tr></thead>
      <tbody><tr v-for="it in items" :key="it.id"><td>{{ it.code }}</td><td>{{ it.title }}</td><td>{{ it.member_count }}</td>
      <td><span class="pill" :class="{'warn': it.mutex_group}">{{ it.mutex_group || '—' }}</span></td></tr></tbody></table>
      <div class="field" style="margin-top:1rem"><label>查看人群 ID</label><input type="number" v-model.number="cohortId" /></div>
      <button class="btn secondary" @click="loadMembers">加载成员</button>
      <h2 style="margin-top:1.2rem">新建人群</h2>
      <div class="field"><label>人群码</label><input v-model="cohortForm.code" /></div>
      <div class="field"><label>标题</label><input v-model="cohortForm.title" /></div>
      <div class="field"><label>互斥组（可空）</label><input v-model="cohortForm.mutex_group" /></div>
      <button class="btn secondary" @click="createCohort">创建人群</button>
    </div>
    <div class="panel span-7">
      <h2>成员</h2>
      <div class="field"><label>主体键</label><input v-model="memberForm.subject_key" /></div>
      <button class="btn" @click="addMember">加入人群</button>
      <p class="muted" v-if="msg">{{ msg }}</p>
      <div class="err" v-if="err">{{ err }}</div>
      <table style="margin-top:0.8rem"><thead><tr><th>ID</th><th>主体键</th></tr></thead>
      <tbody><tr v-for="m in members" :key="m.id"><td>{{ m.id }}</td><td>{{ m.subject_key }}</td></tr></tbody></table>
      <h2 style="margin-top:1.1rem">互斥第二挂拒写痕</h2>
      <table><thead><tr><th>主体</th><th>目标册</th><th>互斥组</th><th>操作者</th></tr></thead>
      <tbody><tr v-for="r in rejections" :key="r.id"><td>{{ r.subject_key }}</td><td>{{ r.cohort_code || r.cohort_id }}</td><td>{{ r.mutex_group }}</td><td>{{ r.attempted_by }}</td></tr></tbody></table>
    </div>
  </div>`
};
