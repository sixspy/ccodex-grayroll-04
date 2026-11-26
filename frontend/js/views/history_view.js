import { api } from "../api.js";
const { ref, onMounted } = Vue;
export const HistoryView = {
  setup() {
    const items = ref([]); const timeline = ref(null); const err = ref("");
    async function reload() {
      try {
        items.value = (await api("/api/history")).items || [];
        timeline.value = await api("/api/history/mutex-timeline");
      }
      catch (e) { err.value = e.message || String(e); }
    }
    onMounted(reload);
    return { items, timeline, err, reload };
  },
  template: `
  <div class="grid">
    <div class="panel span-12">
      <h2>变更历史</h2>
      <p class="hint">互斥第二挂两段式：先「拒写核销」，再「命运取舍」；与此页同源展示。</p>
      <div class="err" v-if="err">{{ err }}</div>
      <table>
        <thead><tr><th>时间动作</th><th>开关</th><th>环境</th><th>详情</th><th>操作者</th></tr></thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td>{{ it.action }}</td><td>{{ it.flag_key || '-' }}</td><td>{{ it.env_code || '-' }}</td>
            <td>{{ it.detail }}</td><td>{{ it.actor }}</td>
          </tr>
        </tbody>
      </table>
      <button class="btn secondary" style="margin-top:0.7rem" @click="reload">刷新</button>
    </div>
    <div class="panel span-6" v-if="timeline && timeline.phase_one">
      <h2>第一段 · 争用核销</h2>
      <p class="hint">第二挂拒写与人群锁争用：败方只留痕，正式成员册零改。</p>
      <table><thead><tr><th>主体</th><th>目标册</th><th>互斥组</th><th>操作者</th></tr></thead>
      <tbody><tr v-for="r in timeline.phase_one.rejects" :key="'r'+r.id"><td>{{ r.subject_key }}</td><td>{{ r.cohort_code || r.cohort_id }}</td><td>{{ r.mutex_group }}</td><td>{{ r.actor }}</td></tr></tbody></table>
      <table style="margin-top:0.6rem"><thead><tr><th>锁</th><th>败方</th><th>胜方</th></tr></thead>
      <tbody><tr v-for="c in timeline.phase_one.contention" :key="'c'+c.id"><td><code>{{ c.lock_key }}</code></td><td>{{ c.loser }}</td><td>{{ c.winner }}</td></tr></tbody></table>
    </div>
    <div class="panel span-6" v-if="timeline && timeline.phase_two">
      <h2>第二段 · 命运取舍</h2>
      <p class="hint">偏离甲路径（乙/折中）一律偏航拒写，取向已定。</p>
      <table><thead><tr><th>域</th><th>请求路径</th><th>操作者</th><th>详情</th></tr></thead>
      <tbody><tr v-for="d in timeline.phase_two.divergences" :key="'d'+d.id"><td>{{ d.scope }}</td><td>{{ d.requested_path }}</td><td>{{ d.actor }}</td><td>{{ d.detail }}</td></tr></tbody></table>
    </div>
  </div>`
};
