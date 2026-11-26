import { api } from "../api.js";
const { ref, onMounted } = Vue;
export const CompareView = {
  setup() {
    const flagId = ref(1); const envId = ref(3);
    const detail = ref(null); const matrix = ref(null); const err = ref("");
    async function reload() {
      err.value = "";
      try {
        detail.value = await api(`/api/compare/flag/${flagId.value}/env/${envId.value}`);
        matrix.value = await api("/api/compare/matrix");
      } catch (e) { err.value = e.message || String(e); }
    }
    onMounted(reload);
    return { flagId, envId, detail, matrix, err, reload };
  },
  template: `
  <div class="grid">
    <div class="panel span-5">
      <h2>正式 vs 影子</h2>
      <div class="field"><label>开关ID</label><input type="number" v-model.number="flagId" /></div>
      <div class="field"><label>环境ID</label><input type="number" v-model.number="envId" /></div>
      <button class="btn secondary" @click="reload">对比</button>
      <div class="err" v-if="err">{{ err }}</div>
      <pre v-if="detail" style="margin-top:0.8rem">{{ detail }}</pre>
    </div>
    <div class="panel span-7">
      <h2>环境矩阵</h2>
      <div v-if="matrix">
        <table>
          <thead>
            <tr>
              <th>开关</th>
              <th v-for="e in matrix.envs" :key="e.id">{{ e.code }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in matrix.matrix" :key="row.flag_id">
              <td>{{ row.flag_key }}</td>
              <td v-for="c in row.cells" :key="c.env_id">
                <span v-if="c.has_rule">{{ c.percent }}% v{{ c.version }}<br /><small class="muted">{{ c.cohort_code || '—' }}</small></span>
                <span v-else class="muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
        <h2 style="margin-top:1rem">互斥双挂冲突</h2>
        <p class="hint" v-if="!matrix.mutex_conflicts || !matrix.mutex_conflicts.length">无跨册双挂。</p>
        <table v-if="matrix.mutex_conflicts && matrix.mutex_conflicts.length">
          <thead><tr><th>主体</th><th>互斥组</th><th>挂靠册数</th></tr></thead>
          <tbody><tr v-for="(m,i) in matrix.mutex_conflicts" :key="i"><td>{{ m.subject_key }}</td><td>{{ m.mutex_group }}</td><td>{{ m.books }}</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>`
};
