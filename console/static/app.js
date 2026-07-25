/* 卡卡西控制台 · classic script（禁 type=module） */
(() => {
  const $ = (id) => document.getElementById(id);

  let sessionId = null;
  let state = null;
  let personas = [];
  let uiStep = null;
  let pollTimer = null;
  let jobTimer = null;

  const KIND_LABEL = {
    human: "人手",
    script: "脚本",
    agent: "写/评",
  };

  async function api(path, opts = {}) {
    const r = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    const text = await r.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text || r.statusText };
    }
    if (!r.ok) {
      const err = new Error(data.error || r.statusText || "request failed");
      err.data = data;
      throw err;
    }
    return data;
  }

  function statusLabel(st) {
    return (
      {
        idle: "待办",
        running: "跑着",
        await_gate: "等人",
        done: "完成",
        failed: "失败",
        blocked: "阻塞",
      }[st] || st || "待办"
    );
  }

  function setDot(kind) {
    const d = $("statusDot");
    d.className = "dot " + (kind || "");
  }

  function toast(show, title, sub, pct) {
    const el = $("runToast");
    if (!show) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    $("runToastTitle").textContent = title || "运行中…";
    $("runToastSub").textContent = sub || "";
    const p = Math.max(0, Math.min(100, pct || 0));
    $("runToastPct").textContent = p + "%";
    $("runToastFill").style.width = p + "%";
  }

  async function loadPersonas(preferId) {
    const res = await api("/api/personas");
    personas = res.personas || [];
    const sel = $("personaSel");
    if (!sel) return;
    const want =
      preferId ||
      (state && state.persona_id) ||
      sel.value ||
      "";
    sel.innerHTML = "";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent =
      state && state.mode === "install" && !installDone(state)
        ? "新建中…"
        : "选人格包";
    sel.appendChild(opt0);
    personas.forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id;
      const runs = p.run_count ? " · " + p.run_count + "次" : "";
      o.textContent = (p.display_name || p.id) + runs;
      if (p.latest_brief_preview)
        o.title = p.latest_brief_preview;
      sel.appendChild(o);
    });
    if (want && personas.some((p) => p.id === want)) {
      sel.value = want;
    } else if (state && state.persona_id && personas.some((p) => p.id === state.persona_id)) {
      sel.value = state.persona_id;
    }
  }

  async function selectPersona(pid, opts) {
    opts = opts || {};
    if (!sessionId) await newSession("write");
    const patch = {
      persona_id: pid,
      mode: "write",
    };
    if (opts.fresh) patch.fresh = true;
    if (opts.run_id) patch.run_id = opts.run_id;
    state = await api("/api/session/" + encodeURIComponent(sessionId) + "/settings", {
      method: "POST",
      body: JSON.stringify(patch),
    });
    if (state.current_step) uiStep = state.current_step;
    await loadPersonas(pid);
    if ($("personaSel")) $("personaSel").value = pid;
    await renderAll();
    const hist = (state.run_history || []).length;
    $("serialMsg").textContent = opts.fresh
      ? "已选 " + pid + " · 全新写"
      : "已选 " + pid + (state.run_id ? " · 恢复 " + state.run_id : "") +
        (hist ? " · 历史" + hist + "条" : "");
  }

  async function resumeRun(runId) {
    if (!sessionId) return;
    state = await api(
      "/api/session/" + encodeURIComponent(sessionId) + "/resume",
      {
        method: "POST",
        body: JSON.stringify({
          persona_id: state.persona_id,
          run_id: runId,
        }),
      }
    );
    if (state.current_step) uiStep = state.current_step;
    await renderAll();
    $("serialMsg").textContent = "已打开 " + runId + " → " + (state.current_step || "");
  }

  async function resetProgress(scope, fromStep) {
    if (!sessionId) return;
    const body =
      scope === "all"
        ? { scope: "all" }
        : { scope: "from", from_step: fromStep || uiStep || state.current_step };
    const msg =
      scope === "all"
        ? "清空当前人格下本会话的全部写稿进度（磁盘上旧 run 还在，可再选历史恢复）。确定？"
        : "从本步起重做后续？更早的步骤保留。";
    if (!confirm(msg)) return;
    state = await api(
      "/api/session/" + encodeURIComponent(sessionId) + "/reset",
      { method: "POST", body: JSON.stringify(body) }
    );
    if (state.current_step) uiStep = state.current_step;
    await renderAll();
    $("serialMsg").textContent =
      scope === "all" ? "已全部清空，可重新写要求" : "已从 " + (fromStep || "") + " 起重置";
  }

  function historyBarHtml(st) {
    if (!st || st.mode !== "write") return "";
    const hist = st.run_history || [];
    const cur = st.run_id || "";
    let h =
      '<div class="hist-bar">' +
      '<div class="hist-row">' +
      '<span class="hist-label">历史</span>';
    if (!hist.length) {
      h += '<span class="hist-empty">此人格还没有写稿记录</span>';
    } else {
      h += '<select id="selRunHist" title="切换历史 run">';
      hist.forEach((r) => {
        h +=
          '<option value="' +
          esc(r.id) +
          '"' +
          (r.id === cur ? " selected" : "") +
          ">" +
          esc(r.id) +
          " · " +
          esc(r.status_label || "") +
          (r.brief_preview ? " · " + esc(r.brief_preview.slice(0, 28)) : "") +
          (r.draft_han ? " · " + r.draft_han + "字" : "") +
          "</option>";
      });
      h += "</select>";
      h +=
        '<button type="button" class="ghost" id="btnLoadRun">打开</button>';
    }
    h +=
      '<button type="button" class="ghost" id="btnFreshWrite" title="不加载历史，空白写">全新写</button>' +
      '<button type="button" class="ghost" id="btnResetFrom" title="从当前步起重做">从本步清</button>' +
      '<button type="button" class="ghost danger-text" id="btnResetAll" title="清空本会话进度">全部清</button>' +
      "</div></div>";
    return h;
  }

  function wireHistoryBar() {
    const sel = $("selRunHist");
    const btnLoad = $("btnLoadRun");
    if (btnLoad && sel) {
      btnLoad.onclick = () => resumeRun(sel.value).catch((e) => alert(e.message || e));
      sel.onchange = () => {
        /* 需点打开，避免误触 */
      };
    }
    const btnFresh = $("btnFreshWrite");
    if (btnFresh) {
      btnFresh.onclick = async () => {
        if (!state || !state.persona_id) return;
        if (!confirm("用当前人格开一份全新写稿（不加载历史）？")) return;
        await selectPersona(state.persona_id, { fresh: true });
      };
    }
    const btnFrom = $("btnResetFrom");
    if (btnFrom)
      btnFrom.onclick = () =>
        resetProgress("from", uiStep || (state && state.current_step)).catch((e) =>
          alert(e.message || e)
        );
    const btnAll = $("btnResetAll");
    if (btnAll)
      btnAll.onclick = () => resetProgress("all").catch((e) => alert(e.message || e));
  }

  function installDone(st) {
    if (!st || !st.steps) return false;
    const i5 = st.steps.I5;
    return !!(i5 && i5.status === "done" && st.paths && st.paths.persona);
  }

  async function newSession(mode) {
    const m = mode || (state && state.mode) || "write";
    const body = {
      mode: m,
      gates_only: $("chkGatesOnly") ? $("chkGatesOnly").checked : false,
    };
    // 写稿可带当前人格并恢复历史；创建人格默认全新槽
    if (m === "write" && $("personaSel").value) {
      body.persona_id = $("personaSel").value;
      // 不 fresh → 服务端 hydrate 最新 run
    }
    state = await api("/api/session", { method: "POST", body: JSON.stringify(body) });
    sessionId = state.session_id;
    uiStep = state.current_step;
    try {
      localStorage.setItem("kakashi_session", sessionId);
    } catch (_) {}
    if (m === "install") {
      $("personaSel").value = "";
    } else if (state.persona_id && $("personaSel")) {
      $("personaSel").value = state.persona_id;
    }
    await renderAll();
    $("serialMsg").textContent =
      "新会话 " +
      sessionId +
      (m === "install"
        ? " · 创建人格·新槽"
        : state.run_id
          ? " · 已恢复 " + state.run_id
          : "");
  }

  async function loadSession(sid) {
    state = await api("/api/session/" + encodeURIComponent(sid));
    sessionId = state.session_id;
    if (!uiStep) uiStep = state.current_step;
    if ($("chkGatesOnly")) $("chkGatesOnly").checked = !!state.gates_only;
    // 创建完成或写稿：下拉对准 persona
    if (state.persona_id) {
      await loadPersonas(state.persona_id);
      if ($("personaSel")) $("personaSel").value = state.persona_id;
    }
    syncModeUI();
    await renderAll();
  }

  function syncModeUI() {
    const mode = (state && state.mode) || "write";
    document.querySelectorAll("#modeSeg button").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    const wrap = $("personaWrap");
    if (wrap) {
      wrap.classList.toggle("install-mode", mode === "install" && !installDone(state));
      wrap.title =
        mode === "install" && !installDone(state)
          ? "创建中：名字在正文上方填；完成后会自动选中新人设"
          : "写稿时选择人格包";
    }
    // 硬闸勾选：写稿时底栏可见；创建人格隐藏
    const g = $("gatesOnlyWrap");
    if (g) g.style.display = mode === "write" ? "" : "none";
  }

  function pipeline() {
    return (state && state.pipeline) || [];
  }

  function renderPipeline() {
    const track = $("pipeTrack");
    if (!track) return;
    track.innerHTML = "";
    const mode = (state && state.mode) || "write";
    const meta = [];
    if (mode === "install") {
      if (installDone(state)) {
        meta.push(
          "已创建 " +
            (state.new_persona_display || state.persona_id || "") +
            (state.persona_id ? " · " + state.persona_id : "")
        );
      } else if (state.new_persona_display || state.new_persona_id) {
        meta.push("新建 " + (state.new_persona_display || state.new_persona_id));
      } else {
        meta.push("新建人格 · 先起名再贴范文");
      }
    } else if (state && state.persona_id) {
      const p = personas.find((x) => x.id === state.persona_id);
      meta.push((p && p.display_name) || state.persona_id);
    }
    if (state && state.gates_only) meta.push("只跑机器硬闸");
    if ($("pipeMeta")) $("pipeMeta").textContent = meta.join(" · ");

    pipeline().forEach((s) => {
      const node = document.createElement("div");
      const st = s.status || "idle";
      node.className = "pipe-node " + st;
      if (s.is_current) node.classList.add("is-current");
      if (uiStep === s.id) node.classList.add("ui-active");
      let mark = s.id;
      if (st === "done") mark = "✓";
      else if (st === "running") mark = "…";
      else if (st === "failed") mark = "!";
      else if (st === "await_gate") mark = "→";
      // 短名：去掉「I1 ·」前缀噪音，只留步骤名
      const shortName = String(s.name || s.id).replace(/^I\d\s*[·.]\s*/, "").replace(/^W\d\s*[·.]\s*/, "");
      node.innerHTML =
        '<div class="bubble" title="' +
        esc(s.id + " " + s.name) +
        '">' +
        mark +
        '</div><div class="conn"></div><div class="label">' +
        esc(shortName) +
        "</div>";
      node.onclick = () => {
        uiStep = s.id;
        renderAll();
      };
      track.appendChild(node);
    });
  }

  function primaryActionLabel(stepId) {
    const info = stepInfo(stepId);
    if (stepId === "I1") return "范文没问题，下一步";
    if (stepId === "W1") return "要求没问题，下一步";
    if (stepId === "W2") return "组装提示";
    if (stepId === "W3") {
      const hasDraft =
        state &&
        state.file_stats &&
        state.file_stats.draft &&
        (state.file_stats.draft.han || 0) > 50;
      const llmDone = state && state.writer_llm && (state.writer_llm.han || 0) > 50;
      if (hasDraft || llmDone) return "正文没问题，下一步";
      return "一键写正文（Grok）";
    }
    if (stepId === "W4") return "跑机器硬闸";
    if (stepId === "W5" && !(state && state.gates_only)) {
      const jv = state && state.judge_view;
      if (jv && jv.pass === false) return "先这样，去出回执 →";
      if (jv && jv.pass === true) return "过了，去出回执 →";
      return "去出回执 →";
    }
    if (stepId === "W6") {
      const rv = state && state.receipt_view;
      if (rv && rv.deliver_ok) {
        if (rv.desktop_path) return "已交稿 · 在桌面";
        return "已交稿 · 再放到桌面";
      }
      if (rv && rv.deliver_ok === false) return "再出一次回执";
      return "一键出回执";
    }
    if (info.kind === "script") {
      if (stepId === "W2") return "跑组装提示";
      if (stepId === "W4") return "跑机器硬闸";
      if (stepId === "W6") return "一键出回执";
      if (stepId === "I2" || stepId === "I3" || stepId === "I4" || stepId === "I5")
        return "跑创建人格";
      return "跑本步";
    }
    return "跑本步";
  }

  function updateChromeActions() {
    const step = uiStep || (state && state.current_step) || "W1";
    const label = primaryActionLabel(step);
    const info = stepInfo(step);
    if ($("btnRunStep")) $("btnRunStep").textContent = label;
    if ($("btnRunStep2")) $("btnRunStep2").textContent = label;
    // 人手步：底栏「确认过闸」与主按钮同义，高亮主按钮即可
    if ($("btnApprove")) {
      const humanGate =
        info.kind === "human" ||
        step === "I1" ||
        step === "W1" ||
        step === "W3" ||
        (step === "W5" && !(state && state.gates_only));
      $("btnApprove").style.display = humanGate ? "" : "none";
      $("btnApprove").textContent = humanGate ? label : "确认过闸 →";
    }
  }

  function renderNav() {
    const nav = $("stepNav");
    nav.innerHTML = "";
    pipeline().forEach((s) => {
      const st = s.status || "idle";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "step-btn " + st;
      if (uiStep === s.id) btn.classList.add("active");
      btn.innerHTML =
        '<span class="step-num">' +
        s.id +
        '</span><span><div class="step-name">' +
        s.name +
        '</div><div class="step-sub">' +
        statusLabel(st) +
        " · " +
        (KIND_LABEL[s.kind] || "") +
        "</div></span>";
      btn.onclick = () => {
        uiStep = s.id;
        renderAll();
      };
      nav.appendChild(btn);
    });
  }

  function stepInfo(id) {
    return pipeline().find((s) => s.id === id) || { id: id, name: id, status: "idle", kind: "human" };
  }

  async function fetchFile(key) {
    if (!sessionId) return null;
    try {
      return await api(
        "/api/session/" + encodeURIComponent(sessionId) + "/file?key=" + encodeURIComponent(key)
      );
    } catch {
      return null;
    }
  }

  async function saveFile(key, text, extra) {
    const opts = extra || {};
    const skipRender = !!opts.skipRender;
    const payload = Object.assign({ key: key, text: text }, opts);
    delete payload.skipRender;
    // 前端也挡：空 brief/draft/raw 不发起覆盖请求（避免重绘后二次空写）
    if (
      (key === "brief" || key === "draft" || key === "raw") &&
      !(String(text || "").trim())
    ) {
      throw new Error(
        key === "brief"
          ? "要求是空的，没保存。请先在框里写内容。"
          : key === "draft"
            ? "正文是空的，没保存。"
            : "范文是空的，没保存。"
      );
    }
    state = await api("/api/session/" + encodeURIComponent(sessionId) + "/file", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!skipRender) {
      // 重绘后立刻回填，避免框被清空；磁盘 hydrate 再校正
      window.__kakashiRestoreEditor = { key: key, text: text };
      await renderAll();
      restoreEditorIfAny();
    }
    return state;
  }

  function restoreEditorIfAny() {
    const r = window.__kakashiRestoreEditor;
    if (!r || !r.text) return;
    if (r.key === "raw" && $("edRaw")) $("edRaw").value = r.text;
    if ((r.key === "brief" || r.key === "draft" || r.key === "judge") && $("edMain"))
      $("edMain").value = r.text;
  }

  async function runWriterLlm() {
    if (!sessionId) await newSession("write");
    if (!(state && state.paths && state.paths.write_prompt)) {
      alert("请先在 W2 点「组装提示」");
      return;
    }
    const cur = ($("edMain") && $("edMain").value) || "";
    if (cur.trim().length > 80) {
      const ok = confirm("一键写正文会覆盖当前 draft 框。继续？");
      if (!ok) return;
    }
    setDot("run");
    $("statusText").textContent = "writer llm";
    try {
      toast(true, "Grok 写正文", "已提交，常要 1–3 分钟…", 8);
      const res = await api(
        "/api/session/" + encodeURIComponent(sessionId) + "/writer-run",
        { method: "POST", body: "{}" }
      );
      const jid = res.job_id;
      state = res.state || state;
      const job = await pollJob(jid);
      state = await api("/api/session/" + encodeURIComponent(sessionId));
      uiStep = "W3";
      const text =
        (job && job.result && job.result.text) ||
        (state.writer_llm && state.writer_llm.text) ||
        "";
      window.__kakashiRestoreEditor = {
        key: "draft",
        text: text || undefined,
      };
      await renderAll();
      // 磁盘回填
      const f = await fetchFile("draft");
      if ($("edMain") && f && f.text) $("edMain").value = f.text;
      else if ($("edMain") && text) $("edMain").value = text;
      toast(false);
      setDot("ok");
      $("statusText").textContent = "idle";
      const han =
        (job && job.result && job.result.han) ||
        (state.writer_llm && state.writer_llm.han) ||
        "?";
      $("serialMsg").textContent =
        "Grok 写完 han=" + han + " · 可改后点「正文没问题，下一步」";
    } catch (e) {
      toast(false);
      setDot("bad");
      $("statusText").textContent = "error";
      $("serialMsg").textContent = e.message || String(e);
      alert(e.message || String(e));
      try {
        state = await api("/api/session/" + encodeURIComponent(sessionId));
        await renderAll();
      } catch (_) {}
    }
  }

  function looksLikeJudgeJson(text) {
    const t = String(text || "").trim();
    if (!t) return false;
    if (t[0] !== "{" && !t.startsWith("```")) return false;
    try {
      const bare = t.startsWith("```")
        ? t.replace(/^```[a-zA-Z0-9_-]*\s*/, "").replace(/```\s*$/, "")
        : t;
      const o = JSON.parse(bare);
      return o && typeof o === "object" && !Array.isArray(o);
    } catch (_) {
      // 宽松：含 pass / axis 关键字也算「像」
      return /"pass"\s*:/.test(t) && /axis_/.test(t);
    }
  }

  async function runJudgeLlm() {
    if (!sessionId) await newSession("write");
    if (state && state.gates_only) {
      alert("已勾「只跑机器硬闸」，无需评分。去「回执交付」点跑 finalize。");
      return;
    }
    if (!(state && (state.paths || {}).judge_prompt) && !(state && state.run_id)) {
      alert("请先跑「机器硬闸」（W4）生成评分合同");
      return;
    }
    const cur = ($("edMain") && $("edMain").value) || "";
    if (looksLikeJudgeJson(cur)) {
      const ok = confirm("一键评分会覆盖当前 Judge 框。继续？");
      if (!ok) return;
    }
    setDot("run");
    $("statusText").textContent = "judge llm";
    try {
      toast(true, "Grok 评分", "已提交，常要 1–2 分钟…", 8);
      const res = await api(
        "/api/session/" + encodeURIComponent(sessionId) + "/judge-run",
        { method: "POST", body: "{}" }
      );
      const jid = res.job_id;
      state = res.state || state;
      const job = await pollJob(jid);
      state = await api("/api/session/" + encodeURIComponent(sessionId));
      uiStep = "W5";
      const text =
        (job && job.result && job.result.text) ||
        "";
      window.__kakashiRestoreEditor = {
        key: "judge",
        text: text || undefined,
      };
      await renderAll();
      const f = await fetchFile("judge");
      if ($("edMain") && f && f.text) $("edMain").value = f.text;
      else if ($("edMain") && text) $("edMain").value = text;
      toast(false);
      setDot("ok");
      $("statusText").textContent = "idle";
      const jv = (state && state.judge_view) || {};
      const jl = (state && state.judge_llm) || {};
      $("serialMsg").textContent =
        (jv.verdict || (jl.pass ? "过了" : "没过")) +
        " · " +
        (jv.headline || jl.one_line || "评分完成") +
        " · " +
        (jv.next_hint || "可去出回执");
    } catch (e) {
      toast(false);
      setDot("bad");
      $("statusText").textContent = "error";
      $("serialMsg").textContent = e.message || String(e);
      alert(e.message || String(e));
      try {
        state = await api("/api/session/" + encodeURIComponent(sessionId));
        await renderAll();
      } catch (_) {}
    }
  }

  async function runStep(stepId) {
    if (!sessionId) await newSession();
    const step = stepId || uiStep;
    const info = stepInfo(step);
    // W3：尚无正文 → 一键 Grok；已有正文 → 过闸
    if (step === "W3") {
      const ta = $("edMain");
      const box = (ta && ta.value) || "";
      let diskHan = 0;
      try {
        const f = await fetchFile("draft");
        diskHan = f && f.text ? (f.text.match(/[一-鿿]/g) || []).length : 0;
        if ((!box || !box.trim()) && f && f.text && ta) ta.value = f.text;
      } catch (_) {}
      const boxHan = (box.match(/[一-鿿]/g) || []).length;
      const llmHan = (state && state.writer_llm && state.writer_llm.han) || 0;
      if (Math.max(boxHan, diskHan, llmHan) >= 50) {
        await approve("W3");
        return;
      }
      await runWriterLlm();
      return;
    }
    // W5：尚无评分 JSON → 一键 Grok；已有 → 过闸（不把空框当 JSON 硬存）
    if (step === "W5" && !(state && state.gates_only)) {
      const ta = $("edMain");
      const box = (ta && ta.value) || "";
      let diskOk = false;
      try {
        const f = await fetchFile("judge");
        if (f && f.text && looksLikeJudgeJson(f.text)) {
          diskOk = true;
          if ((!box || !box.trim()) && ta) ta.value = f.text;
        }
      } catch (_) {}
      const boxOk = looksLikeJudgeJson(box);
      const llmOk = !!(state && state.judge_llm && state.judge_llm.pass != null);
      if (boxOk || diskOk || llmOk) {
        await approve("W5");
        return;
      }
      await runJudgeLlm();
      return;
    }
    // I1/W1：只走 approve（内部保存一次），禁止 save+approve 双写把空框盖回去
    if (step === "I1" || step === "W1") {
      await approve(step);
      return;
    }
    // W6：已有成功回执 → 再放到桌面；否则真跑 finalize（成功会自动拷桌面）
    if (step === "W6") {
      const rv = state && state.receipt_view;
      if (rv && rv.deliver_ok) {
        if (rv.desktop_path) {
          $("serialMsg").textContent =
            "已在桌面： " + (rv.desktop_name || rv.desktop_path);
          return;
        }
        await copyToDesktop();
        return;
      }
      await runFinalize();
      return;
    }
    // 脚本步：若有编辑框先保存（skipRender，跑完再画）
    const ta =
      document.querySelector("#edRaw") ||
      document.querySelector("#edMain") ||
      document.querySelector("textarea.editor[data-key]");
    if (ta && ta.dataset.key) {
      const keep = ta.value;
      if (String(keep || "").trim()) {
        const extra =
          ta.dataset.key === "raw"
            ? { raw_source: window.__kakashiI1Tab === "search" ? "search" : "paste", skipRender: true }
            : { skipRender: true };
        try {
          await saveFile(ta.dataset.key, keep, extra);
        } catch (e) {
          // 脚本步可无编辑内容
        }
      }
    }
    if (info.kind === "agent") {
      $("serialMsg").textContent = "本步是粘贴/外置写：保存正文或 Judge JSON 后过闸";
      setDot("ok");
      return;
    }
    toast(true, "跑 " + step, info.name, 8);
    setDot("run");
    $("statusText").textContent = "running " + step;
    try {
      const res = await api(
        "/api/session/" +
          encodeURIComponent(sessionId) +
          "/steps/" +
          encodeURIComponent(step) +
          "/run",
        {
          method: "POST",
          body: JSON.stringify({
            calibrate: step === "I3",
          }),
        }
      );
      const jid = res.job_id;
      state = res.state || state;
      await pollJob(jid);
      state = await api("/api/session/" + encodeURIComponent(sessionId));
      // auto advance ui
      if (state.current_step) uiStep = state.current_step;
      // 创建人格跑完：刷新库并自动选中新人设，收起强制编辑
      if (
        state.mode === "install" &&
        installDone(state) &&
        (step === "I2" || step === "I3" || step === "I4" || step === "I5" || step === "install_all")
      ) {
        window.__kakashiForceSlotEdit = false;
        await afterInstallSelectPersona();
      }
      renderAll();
      toast(false);
      setDot(state.receipt_summary && state.receipt_summary.deliver_ok === false ? "bad" : "ok");
      $("statusText").textContent = "idle";
      if (!(state.mode === "install" && installDone(state))) {
        $("serialMsg").textContent = step + " 完成";
      }
    } catch (e) {
      toast(false);
      setDot("bad");
      $("statusText").textContent = "error";
      $("serialMsg").textContent = e.message || String(e);
      alert(e.message || String(e));
      try {
        state = await api("/api/session/" + encodeURIComponent(sessionId));
        renderAll();
      } catch (_) {}
    }
  }

  async function runFinalize() {
    if (!sessionId) return;
    toast(true, "出回执", "正在汇总成绩与草稿…", 12);
    setDot("run");
    $("statusText").textContent = "finalize";
    try {
      const res = await api(
        "/api/session/" + encodeURIComponent(sessionId) + "/steps/W6/run",
        { method: "POST", body: "{}" }
      );
      const jid = res.job_id;
      state = res.state || state;
      await pollJob(jid);
      state = await api("/api/session/" + encodeURIComponent(sessionId));
      uiStep = "W6";
      await renderAll();
      toast(false);
      const rv = (state && state.receipt_view) || {};
      const ok = !!(rv.deliver_ok || (state.receipt_summary && state.receipt_summary.deliver_ok));
      setDot(ok ? "ok" : "bad");
      $("statusText").textContent = "idle";
      if (ok && rv.desktop_path) {
        $("serialMsg").textContent =
          (rv.verdict || "可以交了") +
          " · 已放到桌面 " +
          (rv.desktop_name || rv.desktop_path);
      } else {
        $("serialMsg").textContent = ok
          ? (rv.verdict || "可以交了") + " · " + (rv.headline || "回执已出")
          : (rv.verdict || "回执失败") + " · " + (rv.headline || "看看原因");
      }
    } catch (e) {
      toast(false);
      setDot("bad");
      $("statusText").textContent = "error";
      $("serialMsg").textContent = e.message || String(e);
      alert(e.message || String(e));
      try {
        state = await api("/api/session/" + encodeURIComponent(sessionId));
        await renderAll();
      } catch (_) {}
    }
  }

  function pollJob(jid) {
    return new Promise((resolve, reject) => {
      if (jobTimer) clearInterval(jobTimer);
      jobTimer = setInterval(async () => {
        try {
          const job = await api("/api/jobs/" + jid);
          const lastLog = (job.log && job.log[job.log.length - 1]) || "";
          const sub =
            job.hint ||
            lastLog ||
            (job.elapsed_sec != null ? "已等待 " + job.elapsed_sec + "s" : "");
          const kindLabel =
            {
              sample_search_llm: "Grok 搜集范文",
              writer_llm: "Grok 写正文",
              judge_llm: "Grok 评分",
            }[job.kind] ||
            job.kind ||
            "任务";
          const title =
            kindLabel + (job.elapsed_sec != null ? " · " + job.elapsed_sec + "s" : "");
          toast(true, title, sub, job.pct != null ? job.pct : 10);
          if (job.status === "done") {
            clearInterval(jobTimer);
            jobTimer = null;
            resolve(job);
          } else if (job.status === "failed") {
            clearInterval(jobTimer);
            jobTimer = null;
            reject(new Error(job.error || "job failed"));
          }
        } catch (e) {
          clearInterval(jobTimer);
          jobTimer = null;
          reject(e);
        }
      }, 800);
    });
  }

  async function approve(stepOverride) {
    if (!sessionId) return;
    const step = stepOverride || uiStep;
    if (!step) return;
    // I1：过闸前必须有名字（新人设包名）
    if (step === "I1" && state && state.mode === "install") {
      try {
        await saveSlotSettings({ requireName: true, skipRender: true });
      } catch (e) {
        alert(e.message || String(e));
        const card = $("slotCard") || $("edNewPname");
        if (card && card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "center" });
        if ($("edNewPname")) $("edNewPname").focus();
        return;
      }
    }
    // 先抓当前框正文；保存时 skipRender，过闸后再画一次，杜绝「空框二次保存」
    const ta =
      document.querySelector("#edRaw") ||
      document.querySelector("#edMain") ||
      document.querySelector("textarea.editor[data-key]");
    if (ta && ta.dataset.key) {
      const keep = ta.value;
      const key = ta.dataset.key;
      // W5：空框 / 不像 JSON 时，磁盘有货就直接过闸，绝不把空串存成 Judge
      if (key === "judge" && step === "W5") {
        if (!String(keep || "").trim() || !looksLikeJudgeJson(keep)) {
          try {
            const f = await fetchFile("judge");
            const disk = (f && f.text) || "";
            if (looksLikeJudgeJson(disk)) {
              ta.value = disk;
              // 不 saveFile：磁盘已是合法评分
            } else if (state && state.judge_llm && state.judge_llm.pass != null) {
              // 刚一键评过分，磁盘应有；再读一次
              const f2 = await fetchFile("judge");
              if (f2 && f2.text) ta.value = f2.text;
            } else {
              alert("还没有评分。请先点「一键评分（Grok）」，或粘贴合法 JSON。");
              return;
            }
          } catch (_) {
            alert("还没有评分。请先点「一键评分（Grok）」。");
            return;
          }
        } else {
          try {
            window.__kakashiRestoreEditor = { key: "judge", text: keep };
            await saveFile("judge", keep, { skipRender: true });
          } catch (e) {
            // 非法 JSON：若磁盘已有合法则继续过闸
            try {
              const f = await fetchFile("judge");
              if (!(f && looksLikeJudgeJson(f.text))) {
                alert(e.message || String(e));
                return;
              }
              ta.value = f.text;
            } catch (_) {
              alert(e.message || String(e));
              return;
            }
          }
        }
      } else if (!String(keep || "").trim()) {
        // 框空：若磁盘已有内容则只过闸；否则拦住
        try {
          const f = await fetchFile(key);
          const disk = (f && f.text) || "";
          if (!String(disk).trim()) {
            alert(
              step === "W1"
                ? "请先写要求再点下一步"
                : step === "I1"
                  ? "请先贴范文"
                  : "内容是空的，先写再过闸"
            );
            return;
          }
          ta.value = disk;
        } catch (_) {
          alert("请先填写并保存内容");
          return;
        }
      } else {
        try {
          const extra =
            key === "raw"
              ? {
                  raw_source: window.__kakashiI1Tab === "search" ? "search" : "paste",
                  skipRender: true,
                }
              : { skipRender: true };
          window.__kakashiRestoreEditor = { key: key, text: keep };
          await saveFile(key, keep, extra);
        } catch (e) {
          alert(e.message || String(e));
          return;
        }
      }
    }
    try {
      state = await api(
        "/api/session/" +
          encodeURIComponent(sessionId) +
          "/steps/" +
          encodeURIComponent(step) +
          "/approve",
        { method: "POST", body: "{}" }
      );
      if (state.current_step) uiStep = state.current_step;
      await renderAll();
      restoreEditorIfAny();
      $("serialMsg").textContent =
        step + " 已完成 → 现在到 " + (state.current_step || step);
      setDot("ok");
      // 评分过闸后自动出回执，避免「点了去出回执却没然后」
      if (step === "W5" && state && state.current_step === "W6") {
        const hasReceipt =
          state.receipt_view && state.receipt_view.deliver_ok != null;
        if (!hasReceipt) {
          $("serialMsg").textContent = "评分过了，正在出回执…";
          await runFinalize();
        }
      }
    } catch (e) {
      setDot("bad");
      $("serialMsg").textContent = e.message || String(e);
      alert(e.message || String(e));
    }
  }

  async function copyToDesktop() {
    if (!sessionId) {
      alert("还没有会话");
      return;
    }
    setDot("run");
    $("statusText").textContent = "desktop-copy";
    try {
      const res = await api(
        "/api/session/" + encodeURIComponent(sessionId) + "/desktop-copy",
        { method: "POST", body: "{}" }
      );
      if (res && res.state) state = res.state;
      else state = await api("/api/session/" + encodeURIComponent(sessionId));
      uiStep = "W6";
      await renderAll();
      const name =
        (res && res.desktop_name) ||
        (state.receipt_view && state.receipt_view.desktop_name) ||
        (res && res.desktop_path) ||
        "";
      $("serialMsg").textContent = name
        ? "已放到桌面： " + name
        : "已放到桌面";
      setDot("ok");
      $("statusText").textContent = "idle";
    } catch (e) {
      setDot("bad");
      $("statusText").textContent = "error";
      $("serialMsg").textContent = e.message || String(e);
      alert(e.message || String(e));
    }
  }

  async function reveal(preferKey) {
    if (!sessionId) {
      alert("还没有会话");
      return;
    }
    // 拿走正文：优先 draft；否则回执/run 目录
    const paths = (state && state.paths) || {};
    const order = preferKey
      ? [preferKey, "draft", "receipt", "run_dir", "persona", "brief"]
      : ["draft", "receipt", "run_dir", "persona", "brief"];
    let p = "";
    for (const k of order) {
      if (paths[k]) {
        p = paths[k];
        break;
      }
    }
    if (!p && state && state.receipt_view && state.receipt_view.draft_path) {
      p = state.receipt_view.draft_path;
    }
    try {
      const res = await api(
        "/api/session/" + encodeURIComponent(sessionId) + "/reveal",
        {
          method: "POST",
          body: JSON.stringify({ path: p || undefined }),
        }
      );
      const opened = (res && (res.opened || res.path)) || p || "";
      $("serialMsg").textContent = opened
        ? "已打开文件夹： " + opened
        : "已请求打开文件夹";
      // 剪贴板备份路径，资源管理器被挡时用户仍能粘贴
      if (opened && navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(opened);
          $("serialMsg").textContent =
            "已打开文件夹，路径也复制了： " + opened;
        } catch (_) {}
      }
      setDot("ok");
    } catch (e) {
      setDot("bad");
      const msg = e.message || String(e);
      $("serialMsg").textContent = msg;
      // 失败时仍尽量把路径亮出来
      const fallback =
        p ||
        (state && state.receipt_view && state.receipt_view.draft_path) ||
        "";
      alert(
        msg +
          (fallback
            ? "\n\n正文路径（可手动复制到资源管理器）：\n" + fallback
            : "")
      );
    }
  }

  async function applySettings(patch) {
    if (!sessionId) return;
    state = await api("/api/session/" + encodeURIComponent(sessionId) + "/settings", {
      method: "POST",
      body: JSON.stringify(patch),
    });
    await renderAll();
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /** 显示名 → 可用 id（中文可留；空格变 -） */
  function suggestIdFromDisplay(name) {
    let s = String(name || "").trim().toLowerCase();
    s = s.replace(/\s+/g, "-");
    s = s.replace(/[^\w一-鿿\-]+/gi, "-");
    s = s.replace(/-+/g, "-").replace(/^-|-$/g, "");
    return s;
  }

  function slotCardHtml(st, opts) {
    opts = opts || {};
    // 创建完成后默认收起起名框；需要改名再点「改名」
    if (installDone(st) && !opts.forceEdit && !window.__kakashiForceSlotEdit) {
      const label = st.new_persona_display || st.persona_id || "已创建";
      return (
        '<div class="slot-card done" id="slotCard">' +
        "<h3>人格包已写入：<b>" +
        esc(label) +
        "</b>" +
        (st.persona_id ? " <code>" + esc(st.persona_id) + "</code>" : "") +
        "</h3>" +
        '<p class="slot-hint">顶栏下拉已选中此包；可切「写稿」继续。需要改名/覆盖再点下面。</p>' +
        '<div class="actions">' +
        '<button type="button" id="btnEditSlot">改名 / 覆盖设置</button>' +
        '<button type="button" class="primary" id="btnGoWrite">用它写稿</button>' +
        "</div></div>"
      );
    }
    const named =
      (st && (st.new_persona_display || st.new_persona_id)) ||
      (st && st.install_overwrite && st.persona_id);
    const head = named
      ? "这份人格叫：<b>" +
        esc(st.new_persona_display || st.new_persona_id || st.persona_id) +
        "</b>"
      : "先给这份新人设起个名字";
    return (
      '<div class="slot-card" id="slotCard">' +
      "<h3>" +
      head +
      "</h3>" +
      '<p class="slot-hint">显示名给人看；id 可空（按显示名生成）。默认新建，不动已有包。</p>' +
      '<div class="field-row">' +
      '<label class="field"><span>显示名（必填）</span>' +
      '<input type="text" id="edNewPname" placeholder="例如：藤野先生笔迹" value="' +
      esc((st && st.new_persona_display) || "") +
      '" autocomplete="off" /></label>' +
      '<label class="field"><span>人格 id（可空）</span>' +
      '<input type="text" id="edNewPid" placeholder="例如 tengye" value="' +
      esc((st && st.new_persona_id) || "") +
      '" autocomplete="off" /></label>' +
      "</div>" +
      '<label class="chk slot-overwrite">' +
      '<input type="checkbox" id="chkOverwrite" ' +
      (st && st.install_overwrite ? "checked" : "") +
      " />" +
      '<span class="chk-text"><span class="chk-main">覆盖已有人格</span>' +
      '<span class="chk-sub">危险：默认别勾</span></span></label>' +
      '<div class="field-row" id="overwriteRow" style="' +
      (st && st.install_overwrite ? "" : "display:none") +
      '">' +
      '<label class="field"><span>要覆盖的人格</span>' +
      '<select id="selOverwritePid"></select></label></div>' +
      '<div class="actions"><button type="button" id="btnSaveSlot">保存名字</button></div>' +
      "</div>"
    );
  }

  async function saveSlotSettings(opts) {
    opts = opts || {};
    if (!sessionId) await newSession("install");
    let pid = (($("edNewPid") && $("edNewPid").value) || "").trim();
    let pname = (($("edNewPname") && $("edNewPname").value) || "").trim();
    const overwrite = !!($("chkOverwrite") && $("chkOverwrite").checked);
    if (!overwrite) {
      if (!pname && !pid) {
        if (opts.requireName) {
          throw new Error("请先填写「显示名」（这份人格叫什么）");
        }
      }
      if (!pid && pname) {
        pid = suggestIdFromDisplay(pname);
        if ($("edNewPid")) $("edNewPid").value = pid;
      }
      if (opts.requireName && !pid) {
        throw new Error("请填显示名或人格 id，否则无法创建新人设包");
      }
    } else {
      const ov =
        ($("selOverwritePid") && $("selOverwritePid").value) ||
        $("personaSel").value ||
        "";
      if (opts.requireName && !ov) {
        throw new Error("勾了覆盖，请选择要覆盖的已有人格");
      }
    }
    const patch = {
      new_persona_id: pid || null,
      new_persona_display: pname || null,
      install_overwrite: overwrite,
    };
    if (overwrite) {
      const ov =
        ($("selOverwritePid") && $("selOverwritePid").value) ||
        $("personaSel").value;
      if (ov) {
        patch.persona_id = ov;
        $("personaSel").value = ov;
      }
    } else {
      patch.persona_id = "";
    }
    // applySettings 会 renderAll 清掉输入焦点；这里用 silent 路径
    state = await api("/api/session/" + encodeURIComponent(sessionId) + "/settings", {
      method: "POST",
      body: JSON.stringify(patch),
    });
    if (!opts.skipRender) await renderAll();
    $("serialMsg").textContent = overwrite
      ? "槽位：将覆盖 " + (patch.persona_id || "?")
      : "新人设：" + (pname || pid || "（未命名）") + (pid ? " · id=" + pid : "");
    return state;
  }

  function wireSlotCard() {
    const btnSaveSlot = $("btnSaveSlot");
    if (btnSaveSlot)
      btnSaveSlot.onclick = () =>
        saveSlotSettings({ requireName: true })
          .then(() => {
            window.__kakashiForceSlotEdit = false;
          })
          .catch((e) => alert(e.message || e));
    const btnEditSlot = $("btnEditSlot");
    if (btnEditSlot) {
      btnEditSlot.onclick = () => {
        window.__kakashiForceSlotEdit = true;
        renderAll();
      };
    }
    const btnGoWrite = $("btnGoWrite");
    if (btnGoWrite) {
      btnGoWrite.onclick = async () => {
        const pid = (state && state.persona_id) || "";
        await newSession("write");
        if (pid) {
          await loadPersonas(pid);
          $("personaSel").value = pid;
          await applySettings({ persona_id: pid });
        }
        $("serialMsg").textContent = "已切到写稿 · " + (pid || "");
      };
    }
    const chkOverwrite = $("chkOverwrite");
    const overwriteRow = $("overwriteRow");
    const selOverwrite = $("selOverwritePid");
    if (selOverwrite) {
      selOverwrite.innerHTML = "";
      const o0 = document.createElement("option");
      o0.value = "";
      o0.textContent = "— 选要覆盖的包 —";
      selOverwrite.appendChild(o0);
      personas.forEach((p) => {
        if (String(p.id).startsWith("demo:")) return;
        const o = document.createElement("option");
        o.value = p.id;
        o.textContent = (p.display_name || p.id) + " (" + p.id + ")";
        selOverwrite.appendChild(o);
      });
      if (state && state.persona_id) selOverwrite.value = state.persona_id;
    }
    if (chkOverwrite && overwriteRow) {
      chkOverwrite.onchange = () => {
        overwriteRow.style.display = chkOverwrite.checked ? "" : "none";
      };
    }
    const edName = $("edNewPname");
    const edPid = $("edNewPid");
    if (edName && edPid) {
      edName.addEventListener("blur", () => {
        if (!edPid.value.trim() && edName.value.trim()) {
          edPid.value = suggestIdFromDisplay(edName.value);
        }
      });
    }
  }

  async function afterInstallSelectPersona() {
    const pid = state && state.persona_id;
    if (!pid) return;
    await loadPersonas(pid);
    if ($("personaSel")) $("personaSel").value = pid;
    $("serialMsg").textContent =
      "已创建「" +
      (state.new_persona_display || pid) +
      "」并选中 · 可切写稿";
  }

  async function renderContent() {
    const el = $("content");
    if (!state) {
      el.innerHTML = '<div class="panel"><h2>还没有会话</h2><p>点「新会话」开始。顶上流水线图会跟着走。</p></div>';
      return;
    }
    const step = uiStep || state.current_step;
    const info = stepInfo(step);
    const st = info.status || "idle";

    let body = "";
    body +=
      '<div class="panel"><h2>' +
      esc(info.id) +
      " · " +
      esc(info.name) +
      ' <span class="badge ' +
      (st === "done" ? "ok" : st === "failed" ? "bad" : st === "await_gate" ? "warn" : "") +
      '">' +
      statusLabel(st) +
      "</span></h2>";
    body +=
      '<p>类型：' +
      esc(KIND_LABEL[info.kind] || info.kind) +
      " · 当前产线位置：" +
      esc(state.current_step) +
      " · 你正在看：" +
      esc(step) +
      "</p>";

    if (info.error) body += '<div class="alert bad">' + esc(info.error) + "</div>";

    // 写稿：历史 run 条（所有 W 步可见）
    if (state.mode === "write") {
      body += historyBarHtml(state);
    }

    // mode-specific panels
    if (step === "I1") {
      // 单一范文 SSOT：只有一份 raw。来源切换只改「怎么填入」，不造第二框。
      // 以服务端 raw_source 为准；仅当用户本页刚点过 tab 才用 window 覆盖
      let src = state.raw_source === "search" ? "search" : "paste";
      if (window.__kakashiI1TabUserSet) {
        src = window.__kakashiI1Tab === "search" ? "search" : "paste";
      }
      window.__kakashiI1Tab = src;
      const rawHan =
        (state.file_stats && state.file_stats.raw && state.file_stats.raw.han) ||
        (state.sample_search_llm && state.sample_search_llm.han) ||
        0;
      const srcLabel = src === "search" ? "Grok 网搜" : "自己贴文";
      // 起名：仅创建未完成时显示编辑框；完成后收成摘要
      body += slotCardHtml(state);
      if (!installDone(state)) {
        body +=
          '<div class="alert ok">顺序：<b>① 起名</b> → ② 贴/搜范文 → ③「范文没问题，下一步」。一份范文；另做新人设请「新会话」。</div>';
      }
      body +=
        '<div class="meta-grid" style="margin-bottom:10px">' +
        '<div class="meta-card"><div class="k">当前来源</div><div class="v">' +
        esc(srcLabel) +
        '</div></div><div class="meta-card"><div class="k">汉字</div><div class="v">' +
        esc(String(rawHan || "0")) +
        (state.sample_search_llm && state.sample_search_llm.model
          ? '</div></div><div class="meta-card"><div class="k">模型</div><div class="v">' +
            esc(state.sample_search_llm.model)
          : "") +
        "</div></div></div>";
      body +=
        '<div class="i1-tabs" role="tablist" aria-label="范文来源">' +
        '<button type="button" data-i1tab="paste" class="' +
        (src === "paste" ? "active" : "") +
        '">自己贴文</button>' +
        '<button type="button" data-i1tab="search" class="' +
        (src === "search" ? "active" : "") +
        '">Grok 网搜</button>' +
        "</div>";
      if (src === "search") {
        body +=
          '<div class="alert">写清要谁的作品 → 一键网搜会用 cliproxy·Grok 4.5 <b>覆盖</b>下方范文框（无实时浏览器；公版名著较稳）。</div>' +
          '<label for="edSearchQ">要搜谁的什么作品？</label>' +
          '<textarea class="editor" id="edSearchQ" placeholder="例如：鲁迅《藤野先生》公开正文"></textarea>' +
          '<div class="actions">' +
          '<button type="button" class="primary" id="btnRunSearchLlm">一键网搜并填入（会覆盖当前范文）</button>' +
          "</div>";
      } else {
        body +=
          '<p class="hint">从别处复制正文粘进下面大框。建议 ≥500 汉字，≤3000。保存会覆盖会话里唯一的 raw.md。</p>';
      }
      body +=
        '<h3>范文正文（本人格唯一）</h3>' +
        '<textarea class="editor tall" data-key="raw" id="edRaw" placeholder="在这里贴正文，或用 Grok 网搜填入…"></textarea>' +
        '<div class="actions">' +
        '<button type="button" class="primary" id="btnSave">保存范文</button>' +
        '<button type="button" id="btnCleanRaw">清洗排版</button>' +
        '<button type="button" id="btnReloadRaw">从磁盘重新载入</button>' +
        "</div>";
      if (src === "search") {
        body +=
          '<details class="adv-box" style="margin:12px 0">' +
          "<summary>高级：只要注入词、外置分身</summary>" +
          '<div class="actions">' +
          '<button type="button" id="btnPrepSearch">只生成注入词</button>' +
          '<button type="button" id="btnCopySpawn">复制注入词</button>' +
          "</div>" +
          (state.handoff && state.handoff.role === "sample_search"
            ? '<pre class="preview" id="pvSpawn" style="max-height:180px">加载中…</pre>'
            : "") +
          "</details>";
      }
      if (state.raw_clean_notes && state.raw_clean_notes.length) {
        body +=
          '<div class="alert warn">' +
          esc(state.raw_clean_notes.join("；")) +
          "</div>";
      }
      body +=
        '<div class="actions" style="margin-top:14px">' +
        '<button type="button" class="primary" id="btnApproveI1">范文没问题，下一步 →</button>' +
        "</div>";
    } else if (step === "I2" || step === "I3" || step === "I4" || step === "I5") {
      if (installDone(state)) {
        body +=
          '<div class="alert ok">创建完成。起名框已收起；顶栏应已选中新人设。下面是 rules 预览。</div>';
        body += slotCardHtml(state);
      } else {
        body +=
          '<div class="alert">一键跑「创建人格」：抽笔迹 → 校准 → 体检 → 写入。名字不对可在此改。</div>';
        body += slotCardHtml(state);
        if (step === "I3")
          body += '<div class="alert warn">本步会带校准（布局极端时改 rules 注）。</div>';
        body +=
          '<div class="actions"><button type="button" class="primary" id="btnDoRun">跑创建人格</button></div>';
      }
      if (state.paths && state.paths.rules) {
        body += "<h3>rules.md</h3><pre class=\"preview\" id=\"pvRules\">加载中…</pre>";
      }
    } else if (step === "W1") {
      body +=
        '<div class="alert">brief 是事实/结构/字数 SSOT。风格跟人格包；禁止把样本叙事身份写进 brief 除非你明确允许角色扮演。</div>';
      body +=
        '<textarea class="editor tall" data-key="brief" id="edMain" placeholder="例如：约1000字，写当代东京通勤，禁止角色仿写…"></textarea>';
      body +=
        '<div class="actions"><button type="button" class="primary" id="btnSave">保存 brief</button></div>';
    } else if (step === "W2") {
      body +=
        '<div class="alert">组装写作合同：run_write prepare → WRITE_PROMPT（下一键写正文会吃这份）。</div>';
      body +=
        '<div class="actions"><button type="button" class="primary" id="btnDoRun">组装提示</button></div>';
      if (state.paths && state.paths.write_prompt)
        body +=
          '<div class="alert ok">已组装。去 <b>写正文</b> 点「一键写正文（Grok）」即可，不用复制提示词。</div>' +
          "<h3>WRITE_PROMPT（合同预览）</h3><pre class=\"preview\" id=\"pvWP\">加载中…</pre>";
      body +=
        '<details class="adv-box" style="margin:12px 0"><summary>高级：外置分身注入词</summary>' +
        '<div class="actions"><button type="button" id="btnCopySpawn">复制 SPAWN_PROMPT</button></div>' +
        (state.paths && state.paths.spawn_prompt
          ? '<pre class="preview" id="pvSpawn" style="max-height:180px">加载中…</pre>'
          : "") +
        "</details>";
    } else if (step === "W3") {
      const h = state.handoff || {};
      const llm = state.writer_llm || {};
      body +=
        '<div class="alert ok"><b>默认：页内一键写</b> — 与 I1 网搜相同，走 cliproxy · Grok 4.5，按 WRITE_PROMPT 直接写 draft。你不用复制给分身。</div>';
      if (h.spawn_instruction && h.auto_ran)
        body += '<div class="alert">' + esc(h.spawn_instruction) + "</div>";
      body +=
        '<div class="meta-grid" style="margin-bottom:10px">' +
        (h.write_target
          ? '<div class="meta-card"><div class="k">draft 路径</div><div class="v">' +
            esc(h.write_target) +
            "</div></div>"
          : "") +
        (llm.model
          ? '<div class="meta-card"><div class="k">模型</div><div class="v">' +
            esc(llm.model) +
            "</div></div>"
          : "") +
        (llm.han != null
          ? '<div class="meta-card"><div class="k">汉字</div><div class="v">' +
            esc(String(llm.han)) +
            "</div></div>"
          : "") +
        "</div>";
      body +=
        '<div class="actions">' +
        '<button type="button" class="primary" id="btnRunWriterLlm">一键写正文（Grok 4.5）</button>' +
        '<button type="button" id="btnApproveW3">正文没问题，下一步 →</button>' +
        "</div>";
      body +=
        '<h3>正文 draft（可改）</h3><textarea class="editor tall" data-key="draft" id="edMain" placeholder="点上面一键生成，或自己贴正文…"></textarea>';
      body +=
        '<div class="actions"><button type="button" id="btnSave">保存 draft</button></div>';
      body +=
        '<details class="adv-box" style="margin:12px 0"><summary>高级：外置 Writer / 只看合同</summary>' +
        '<div class="actions"><button type="button" id="btnCopySpawn">复制 SPAWN_PROMPT</button></div>' +
        '<pre class="preview" id="pvSpawn" style="max-height:160px">加载中…</pre>' +
        (state.paths && state.paths.write_prompt
          ? "<h3>WRITE_PROMPT</h3><pre class=\"preview\" id=\"pvWP\">加载中…</pre>"
          : "") +
        "</details>";
    } else if (step === "W4") {
      body +=
        '<div class="alert">机器硬闸（与 skill 同脚本）：查身份污染 + brief 是否对得上。失败则 deliver_ok 不能过；默认仍会生成评分分身注入包。</div>';
      body +=
        '<div class="actions"><button type="button" class="primary" id="btnDoRun">跑机器硬闸</button></div>';
      if (state.gates_data) {
        body +=
          "<h3>GATES</h3><pre class=\"preview\">" +
          esc(JSON.stringify(state.gates_data, null, 2)) +
          "</pre>";
      } else if (state.paths && state.paths.gates) {
        body += "<h3>GATES</h3><pre class=\"preview\" id=\"pvGates\">加载中…</pre>";
      }
    } else if (step === "W5") {
      if (state.gates_only) {
        body +=
          '<div class="alert warn"><b>本步会跳过</b>：你勾了「只跑机器硬闸」。系统自动合成一份降级成绩，然后去出回执。要认真评就取消勾选再评一次。</div>';
      } else {
        const jv = state.judge_view || null;
        const jl = state.judge_llm || {};
        body +=
          '<div class="alert">这一步是<strong>给稿子打分</strong>：像不像这支笔、有没有按你的要求写。' +
          "分数单是给机器出回执用的；你只看下面的人话结论就行。</div>";
        if (!jv) {
          body +=
            '<div class="alert ok">还没评。点「一键评分」，等一两分钟看人话成绩单。</div>';
          body +=
            '<div class="actions">' +
            '<button type="button" class="primary" id="btnRunJudgeLlm">一键评分</button>' +
            "</div>";
        } else {
          const ok = !!jv.pass;
          body +=
            '<div class="judge-card ' +
            (ok ? "ok" : "bad") +
            '">' +
            '<div class="judge-verdict">' +
            (ok ? "过了" : "没过") +
            "</div>" +
            '<div class="judge-head">' +
            esc(jv.headline || jl.one_line || "") +
            "</div>" +
            '<div class="judge-grid">' +
            '<div class="judge-item"><div class="k">' +
            esc(jv.style_label || "像不像这支笔") +
            '</div><div class="v">' +
            esc(String(jv.style_score != null ? jv.style_score : "—")) +
            " / 10</div></div>" +
            '<div class="judge-item"><div class="k">' +
            esc(jv.brief_label || "有没有按你的要求写") +
            '</div><div class="v">' +
            esc(String(jv.brief_score != null ? jv.brief_score : "—")) +
            " / 10</div></div>" +
            '<div class="judge-item"><div class="k">身份</div><div class="v">' +
            esc(jv.identity_text || "") +
            "</div></div>" +
            "</div>";
          if (jv.fail_reasons && jv.fail_reasons.length) {
            body += "<div class=\"judge-sec\"><b>没过的点</b><ul>";
            jv.fail_reasons.forEach((x) => {
              body += "<li>" + esc(x) + "</li>";
            });
            body += "</ul></div>";
          }
          if (jv.rewrite_directives && jv.rewrite_directives.length) {
            body += "<div class=\"judge-sec\"><b>建议怎么改</b><ul>";
            jv.rewrite_directives.forEach((x) => {
              body += "<li>" + esc(x) + "</li>";
            });
            body += "</ul></div>";
          }
          if (jv.next_hint) {
            body +=
              '<div class="judge-next">' + esc(jv.next_hint) + "</div>";
          }
          body += "</div>";
          body +=
            '<div class="actions">' +
            '<button type="button" class="primary" id="btnApproveW5">' +
            (ok ? "过了，去出回执 →" : "先这样，去出回执 →") +
            "</button>" +
            '<button type="button" id="btnRunJudgeLlm">再评一次</button>' +
            "</div>";
        }
        body +=
          '<details class="adv-box" style="margin:12px 0">' +
          "<summary>机器原始成绩单（一般不用看）</summary>" +
          '<p class="hint">这是给回执程序读的 JSON，不是给你读的说明文。改坏了可能出不了回执。</p>' +
          '<textarea class="editor" data-key="judge" id="edMain" placeholder="一般不用手改"></textarea>' +
          '<div class="actions"><button type="button" id="btnSave">保存成绩单</button></div>' +
          "</details>";
        body +=
          '<details class="adv-box" style="margin:12px 0"><summary>高级：外置评分 / 合同原文</summary>' +
          '<div class="actions"><button type="button" id="btnCopySpawn">复制注入词</button></div>' +
          '<pre class="preview" id="pvSpawn" style="max-height:160px">加载中…</pre>' +
          (state.paths && state.paths.judge_prompt
            ? "<h3>评分合同</h3><pre class=\"preview\" id=\"pvJP\">加载中…</pre>"
            : "") +
          "</details>";
      }
    } else if (step === "W6") {
      const rv = state.receipt_view || null;
      body +=
        '<div class="alert">这一步是<strong>交稿收尾</strong>：出回执的同时，正文会<strong>自动放一份到桌面</strong>。' +
        "不用再找文件夹。</div>";
      if (!rv) {
        body +=
          '<div class="alert ok">还没出回执。点下面按钮，几秒就好；成功后桌面会出现一份正文。</div>';
        body +=
          '<div class="actions"><button type="button" class="primary" id="btnFinalize">一键出回执（并放到桌面）</button></div>';
      } else {
        const ok = !!rv.deliver_ok;
        body +=
          '<div class="judge-card ' +
          (ok ? "ok" : "bad") +
          '">' +
          '<div class="judge-verdict">' +
          esc(rv.verdict || (ok ? "可以交了" : "还不行")) +
          "</div>" +
          '<div class="judge-head">' +
          esc(rv.headline || "") +
          "</div>" +
          '<div class="judge-grid">' +
          '<div class="judge-item"><div class="k">正文大约</div><div class="v">' +
          esc(String(rv.han != null ? rv.han : "—")) +
          " 字</div></div>" +
          '<div class="judge-item"><div class="k">硬闸</div><div class="v">' +
          esc(rv.gates_text || "") +
          "</div></div>" +
          '<div class="judge-item"><div class="k">评分</div><div class="v">' +
          esc(rv.judge_text || "") +
          "</div></div>" +
          '<div class="judge-item"><div class="k">身份</div><div class="v">' +
          esc(rv.identity_text || "") +
          "</div></div>" +
          (rv.style_score && rv.style_score !== "—"
            ? '<div class="judge-item"><div class="k">像不像这支笔</div><div class="v">' +
              esc(String(rv.style_score)) +
              " / 10</div></div>"
            : "") +
          (rv.brief_score && rv.brief_score !== "—"
            ? '<div class="judge-item"><div class="k">按你的要求</div><div class="v">' +
              esc(String(rv.brief_score)) +
              " / 10</div></div>"
            : "") +
          "</div>" +
          (rv.next_hint
            ? '<div class="judge-next">' + esc(rv.next_hint) + "</div>"
            : "") +
          "</div>";
        if (ok && rv.desktop_path) {
          body +=
            '<div class="meta-card" style="margin-bottom:10px"><div class="k">桌面上的正文</div><div class="v" id="desktopPathText">' +
            esc(rv.desktop_path) +
            "</div></div>";
        } else if (ok) {
          const draftPath =
            (state.paths && state.paths.draft) || (rv && rv.draft_path) || "";
          if (draftPath) {
            body +=
              '<div class="meta-card" style="margin-bottom:10px"><div class="k">库内正文</div><div class="v">' +
              esc(draftPath) +
              "</div></div>";
          }
        }
        body +=
          '<div class="actions">' +
          (ok
            ? rv.desktop_path
              ? '<button type="button" class="primary" id="btnCopyDesktopPath">复制桌面路径</button>' +
                '<button type="button" id="btnDesktopCopy">再放一份到桌面</button>'
              : '<button type="button" class="primary" id="btnDesktopCopy">放到桌面</button>'
            : '<button type="button" class="primary" id="btnFinalize">再出一次回执</button>') +
          (ok
            ? '<button type="button" id="btnFinalize">刷新回执</button>'
            : "") +
          "</div>";
        if (state.paths && state.paths.draft) {
          body +=
            "<h3>正文预览</h3><pre class=\"preview\" id=\"pvDraft\">加载中…</pre>";
        }
        body +=
          '<details class="adv-box" style="margin:12px 0"><summary>高级：库内路径 / 机器回执</summary>' +
          (state.paths && state.paths.draft
            ? '<p class="hint">库内：' +
              esc(state.paths.draft) +
              "</p>"
            : "") +
          '<div class="actions"><button type="button" id="btnRevealReceipt">打开库内文件夹</button></div>' +
          (state.receipt_text || (state.paths && state.paths.receipt)
            ? '<pre class="preview" id="pvReceipt">加载中…</pre>'
            : "") +
          (state.receipt_data
            ? "<pre class=\"preview\">" +
              esc(JSON.stringify(state.receipt_data, null, 2)) +
              "</pre>"
            : "") +
          "</details>";
      }
    } else {
      body += "<p>未知步骤</p>";
    }

    // meta
    body += '<div class="meta-grid">';
    const stats = state.file_stats || {};
    Object.keys(stats).forEach((k) => {
      body +=
        '<div class="meta-card"><div class="k">' +
        esc(k) +
        '</div><div class="v">' +
        stats[k].han +
        " 字 · " +
        stats[k].bytes +
        " B</div></div>";
    });
    body += "</div>";

    if (state.log && state.log.length) {
      body += '<h3>会话日志</h3><div class="log-list">';
      state.log
        .slice(-20)
        .reverse()
        .forEach((L) => {
          body += "<div>" + esc(L.t) + " · " + esc(L.msg) + "</div>";
        });
      body += "</div>";
    }
    body += "</div>";

    el.innerHTML = body;

    // wire buttons
    wireSlotCard();
    wireHistoryBar();
    const btnApproveI1 = $("btnApproveI1");
    if (btnApproveI1) btnApproveI1.onclick = () => approve("I1");
    const btnSave = $("btnSave");
    if (btnSave) {
      btnSave.onclick = async () => {
        const ta = $("edRaw") || $("edMain");
        if (!ta) return;
        const keep = ta.value;
        if (!String(keep || "").trim()) {
          alert(ta.dataset.key === "brief" ? "要求是空的，写点内容再保存" : "内容是空的");
          return;
        }
        const key = ta.dataset.key || "raw";
        const extra =
          key === "raw"
            ? { raw_source: window.__kakashiI1Tab === "search" ? "search" : "paste" }
            : {};
        // 有名字框时一并落盘（不强制）
        if (key === "raw" && ($("edNewPname") || $("edNewPid"))) {
          try {
            await saveSlotSettings({ skipRender: true });
          } catch (_) {
            /* 保存范文时名字可后补 */
          }
        }
        try {
          window.__kakashiRestoreEditor = { key: key, text: keep };
          await saveFile(key, keep, extra);
          restoreEditorIfAny();
          $("serialMsg").textContent =
            key === "brief"
              ? "要求已保存（" + keep.trim().length + " 字）。可点「要求没问题，下一步」"
              : key === "draft"
                ? "draft 已保存"
                : "已保存。确认后点下一步";
        } catch (e) {
          alert(e.message || String(e));
        }
      };
    }
    const btnDoRun = $("btnDoRun");
    if (btnDoRun) {
      btnDoRun.onclick = async () => {
        // 跑创建前先落盘槽位，避免默认踩旧人格
        if ($("edNewPid") || $("edNewPname") || $("chkOverwrite")) {
          try {
            await saveSlotSettings({ requireName: true, skipRender: true });
          } catch (e) {
            alert(e.message || String(e));
            if ($("edNewPname")) $("edNewPname").focus();
            return;
          }
        }
        runStep(step);
      };
    }
    const btnRunWriterLlm = $("btnRunWriterLlm");
    if (btnRunWriterLlm) btnRunWriterLlm.onclick = () => runWriterLlm();
    const btnApproveW3 = $("btnApproveW3");
    if (btnApproveW3) btnApproveW3.onclick = () => approve("W3");
    const btnRunJudgeLlm = $("btnRunJudgeLlm");
    if (btnRunJudgeLlm) btnRunJudgeLlm.onclick = () => runJudgeLlm();
    const btnApproveW5 = $("btnApproveW5");
    if (btnApproveW5) btnApproveW5.onclick = () => approve("W5");
    const btnFinalize = $("btnFinalize");
    if (btnFinalize) btnFinalize.onclick = () => runFinalize();
    const btnRevealReceipt = $("btnRevealReceipt");
    if (btnRevealReceipt) btnRevealReceipt.onclick = () => reveal("draft");
    const btnDesktopCopy = $("btnDesktopCopy");
    if (btnDesktopCopy) btnDesktopCopy.onclick = () => copyToDesktop();
    const btnCopyDesktopPath = $("btnCopyDesktopPath");
    if (btnCopyDesktopPath) {
      btnCopyDesktopPath.onclick = async () => {
        const p =
          (state && state.receipt_view && state.receipt_view.desktop_path) ||
          (state && state.paths && state.paths.desktop_draft) ||
          "";
        if (!p) {
          alert("还没有桌面文件，先出回执或点「放到桌面」");
          return;
        }
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(p);
          } else {
            prompt("复制桌面路径：", p);
          }
          $("serialMsg").textContent = "桌面路径已复制";
        } catch (_) {
          prompt("复制桌面路径：", p);
        }
      };
    }
    async function copySpawnText() {
      let text = state.spawn_prompt_text || "";
      if (!text) {
        const f = await fetchFile("spawn_prompt");
        text = (f && f.text) || "";
      }
      if (!text) {
        alert("尚无 SPAWN_PROMPT：先跑 prepare / post，或在 I1 高级里生成注入词");
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        $("serialMsg").textContent = "已复制 SPAWN_PROMPT（" + text.length + " 字）";
      } catch (e) {
        const pre = $("pvSpawn");
        if (pre) {
          const r = document.createRange();
          r.selectNodeContents(pre);
          const sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(r);
        }
        alert("剪贴板不可用，已选中文本请 Ctrl+C");
      }
    }
    const btnCopySpawn = $("btnCopySpawn");
    if (btnCopySpawn) btnCopySpawn.onclick = () => copySpawnText();

    async function cleanRawIntoEditors() {
      if (!sessionId) await newSession("install");
      try {
        const res = await api(
          "/api/session/" + encodeURIComponent(sessionId) + "/clean-raw",
          { method: "POST", body: "{}" }
        );
        state = res.state || state;
        const text = (res.clean && res.clean.text) || "";
        renderAll();
        if ($("edRaw") && text) $("edRaw").value = text;
        $("serialMsg").textContent =
          "已清洗 han=" + ((res.clean && res.clean.han_after) || "?");
      } catch (e) {
        alert(e.message || String(e));
      }
    }
    const btnCleanRaw = $("btnCleanRaw");
    if (btnCleanRaw) btnCleanRaw.onclick = () => cleanRawIntoEditors();

    const btnPrepSearch = $("btnPrepSearch");
    if (btnPrepSearch) {
      btnPrepSearch.onclick = async () => {
        if (!sessionId) await newSession("install");
        const q = ($("edSearchQ") && $("edSearchQ").value) || "";
        try {
          const res = await api(
            "/api/session/" + encodeURIComponent(sessionId) + "/sample-search",
            { method: "POST", body: JSON.stringify({ query: q }) }
          );
          state = res.state || state;
          window.__kakashiI1Tab = "search";
          renderAll();
          $("serialMsg").textContent = "注入词已生成（高级路径）";
        } catch (e) {
          alert(e.message || String(e));
        }
      };
    }
    const btnRunSearchLlm = $("btnRunSearchLlm");
    if (btnRunSearchLlm) {
      btnRunSearchLlm.onclick = async () => {
        if (!sessionId) await newSession("install");
        const q = ($("edSearchQ") && $("edSearchQ").value) || "";
        if (!q.trim() || q.trim().length < 4) {
          alert("先写清要搜谁的什么作品");
          return;
        }
        const cur = ($("edRaw") && $("edRaw").value) || "";
        if (cur.trim().length > 80) {
          const ok = confirm(
            "一键网搜会覆盖当前唯一范文。继续？\n（另做一篇请先「新会话」）"
          );
          if (!ok) return;
        }
        setDot("run");
        $("statusText").textContent = "sample-search llm";
        try {
          toast(true, "Grok 搜集范文", "已提交，Grok 常要 1–3 分钟，进度会慢慢走…", 8);
          const res = await api(
            "/api/session/" + encodeURIComponent(sessionId) + "/sample-search-run",
            { method: "POST", body: JSON.stringify({ query: q }) }
          );
          const jid = res.job_id;
          state = res.state || state;
          const job = await pollJob(jid);
          state = await api("/api/session/" + encodeURIComponent(sessionId));
          window.__kakashiI1Tab = "search";
          let text =
            (job && job.result && job.result.text) ||
            (state.sample_search_llm && state.sample_search_llm.text) ||
            "";
          if (!text) {
            const f = await fetchFile("raw");
            text = (f && f.text) || "";
          }
          renderAll();
          if ($("edRaw")) $("edRaw").value = text;
          toast(false);
          setDot("ok");
          $("statusText").textContent = "idle";
          const han =
            (job && job.result && job.result.han) ||
            (state.sample_search_llm && state.sample_search_llm.han) ||
            "?";
          $("serialMsg").textContent = "已覆盖填入范文 han=" + han;
          if (!text || String(text).trim().length < 20) {
            alert("任务结束但范文几乎是空的，请再点一次或改用自己贴文。");
          }
        } catch (e) {
          toast(false);
          setDot("bad");
          $("statusText").textContent = "error";
          $("serialMsg").textContent = e.message || String(e);
          alert(e.message || String(e));
          try {
            state = await api("/api/session/" + encodeURIComponent(sessionId));
            renderAll();
          } catch (_) {}
        }
      };
    }
    const btnReloadRaw = $("btnReloadRaw");
    if (btnReloadRaw) {
      btnReloadRaw.onclick = async () => {
        const f = await fetchFile("raw");
        const text = (f && f.text) || "";
        if ($("edRaw")) $("edRaw").value = text;
        $("serialMsg").textContent = text
          ? "已从磁盘载入唯一范文（" + ((f && f.han) || 0) + " 字）"
          : "磁盘尚无 raw.md";
      };
    }
    document.querySelectorAll("[data-i1tab]").forEach((b) => {
      b.onclick = async () => {
        const next = b.getAttribute("data-i1tab") || "paste";
        // 先把框里未保存字抠住，切 tab 重绘后写回——切换来源不丢正文
        const keep = ($("edRaw") && $("edRaw").value) || "";
        window.__kakashiI1Tab = next;
        window.__kakashiI1TabUserSet = true;
        if (sessionId) {
          try {
            await applySettings({ raw_source: next });
          } catch (_) {
            renderAll();
          }
        } else {
          renderAll();
        }
        if ($("edRaw") && keep) $("edRaw").value = keep;
      };
    });

    // hydrate：唯一范文框从磁盘回填（重绘后新节点）
    if (step === "I1") {
      const f = await fetchFile("raw");
      const text = (f && f.text) || "";
      if ($("edRaw")) {
        // 若用户刚在框里打了还没保存的字，且磁盘为空，勿清空
        const cur = $("edRaw").value || "";
        if (text) $("edRaw").value = text;
        else if (!cur) $("edRaw").value = "";
      }
      const qf = await fetchFile("sample_query");
      if ($("edSearchQ")) {
        if (qf && qf.text) $("edSearchQ").value = qf.text;
        else if (state.sample_search_query) $("edSearchQ").value = state.sample_search_query;
      }
    }
    if (step === "W1") {
      const f = await fetchFile("brief");
      const disk = (f && f.text) || "";
      const restore =
        (window.__kakashiRestoreEditor &&
          window.__kakashiRestoreEditor.key === "brief" &&
          window.__kakashiRestoreEditor.text) ||
        "";
      if ($("edMain")) {
        // 磁盘优先；恢复缓冲次之；绝不在有货时留空
        if (disk.trim()) $("edMain").value = disk;
        else if (restore.trim()) $("edMain").value = restore;
      }
    }
    if (step === "W3") {
      const f = await fetchFile("draft");
      const disk = (f && f.text) || "";
      const restore =
        (window.__kakashiRestoreEditor &&
          window.__kakashiRestoreEditor.key === "draft" &&
          window.__kakashiRestoreEditor.text) ||
        "";
      if ($("edMain")) {
        if (disk.trim()) $("edMain").value = disk;
        else if (restore.trim()) $("edMain").value = restore;
      }
    }
    if (step === "W5" && !state.gates_only) {
      const f = await fetchFile("judge");
      if (f && $("edMain") && !($("edMain").value || "").trim()) $("edMain").value = f.text || "";
    }
    async function fillPre(id, key) {
      const node = document.getElementById(id);
      if (!node) return;
      const f = await fetchFile(key);
      node.textContent = f ? f.text : "(无文件)";
    }
    await fillPre("pvWP", "write_prompt");
    await fillPre("pvRules", "rules");
    await fillPre("pvGates", "gates");
    await fillPre("pvJP", "judge_prompt");
    await fillPre("pvReceipt", "receipt");
    await fillPre("pvDraft", "draft");
    // spawn: prefer server-enriched full text
    const pvSpawn = document.getElementById("pvSpawn");
    if (pvSpawn) {
      if (state.spawn_prompt_text) {
        pvSpawn.textContent = state.spawn_prompt_text + (state.spawn_prompt_truncated ? "\n…(truncated)" : "");
      } else {
        await fillPre("pvSpawn", "spawn_prompt");
      }
    }

    $("footerHint").textContent =
      "会话 " +
      state.session_id +
      (state.persona_path ? " · " + state.persona_path : "") +
      (state.run_id ? " · " + state.run_id : "");
  }

  async function renderAll() {
    syncModeUI();
    renderPipeline();
    renderNav();
    // renderContent 内有 await hydrate；必须等完再 restore，否则框仍空
    await renderContent();
    restoreEditorIfAny();
    updateChromeActions();
    if (state && state.receipt_summary && state.receipt_summary.deliver_ok) setDot("ok");
    else if (state && state.steps) {
      const anyFail = Object.values(state.steps).some((s) => s && s.status === "failed");
      const anyRun = Object.values(state.steps).some((s) => s && s.status === "running");
      setDot(anyFail ? "bad" : anyRun ? "run" : "ok");
    }
  }

  function wire() {
    $("btnNewSession").onclick = () => newSession();
    $("btnRefresh").onclick = async () => {
      if (sessionId) await loadSession(sessionId);
      else await loadPersonas();
    };
    $("btnRefreshPersonas").onclick = () => loadPersonas();
    $("btnRunStep").onclick = () => runStep(uiStep);
    $("btnRunStep2").onclick = () => runStep(uiStep);
    $("btnApprove").onclick = () => approve();
    $("btnReveal").onclick = () => reveal();
    $("chkGatesOnly").onchange = async () => {
      if (sessionId) await applySettings({ gates_only: $("chkGatesOnly").checked });
    };
    $("personaSel").onchange = async () => {
      if (!$("personaSel").value) return;
      if (state && state.mode === "install" && !(state.install_overwrite)) {
        $("serialMsg").textContent =
          "创建人格默认新槽；顶栏选择不会覆盖。要覆盖请在 I2 勾「覆盖已有」。";
        return;
      }
      try {
        // 写稿：自动恢复该人格最新历史（磁盘 runs 还在）
        if (!state || state.mode !== "write") {
          await newSession("write");
        }
        await selectPersona($("personaSel").value, { fresh: false });
      } catch (e) {
        alert(e.message || String(e));
      }
    };
    document.querySelectorAll("#modeSeg button").forEach((b) => {
      b.onclick = async () => {
        const mode = b.getAttribute("data-mode");
        const pid = $("personaSel") && $("personaSel").value;
        await newSession(mode);
        // 切回写稿且已选人格：自动带历史
        if (mode === "write" && pid) {
          try {
            await selectPersona(pid, { fresh: false });
          } catch (e) {
            $("serialMsg").textContent = e.message || String(e);
          }
        }
      };
    });
  }

  async function boot() {
    wire();
    await loadPersonas();
    let sid = null;
    try {
      sid = localStorage.getItem("kakashi_session");
    } catch (_) {}
    if (sid) {
      try {
        await loadSession(sid);
        // 旧会话若卡在 install 且 persona 是 soseki，UI 提示但不自动覆盖
        if (state && state.mode === "install" && !state.new_persona_id) {
          $("serialMsg").textContent =
            "创建人格：默认新槽。在 I2 填 id；不会静默写进 " +
            (state.persona_id || "已有包");
        }
        return;
      } catch (_) {
        /* fallthrough */
      }
    }
    await newSession("write");
    // 写稿可默认挑一个包方便试；创建人格绝不默认写进 soseki
    const prefer = personas.find(
      (p) => p.id === "soseki" || (p.id && String(p.id).includes("soseki"))
    );
    if (prefer && state && state.mode === "write") {
      $("personaSel").value = prefer.id;
      await applySettings({ persona_id: prefer.id });
    }
    setDot("ok");
    $("statusText").textContent = "ready";
  }

  boot().catch((e) => {
    console.error(e);
    $("serialMsg").textContent = e.message || String(e);
    setDot("bad");
  });
})();
