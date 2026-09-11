// Frontend Interactive Logic for Royalty Sales & Settlement System
let globalConfigs = { platforms: [], teachers: [], courses: [] };
let currentAuditResult = null;
let currentPeriodStr = "115年8月";
let currentPlatformName = "104學習平台";
let gasCodeSnippet = "";
let gasPlatformCode = "";
let gasTeacherCode = "";

document.addEventListener("DOMContentLoaded", () => {
  loadConfigs();
  refreshDetectedFiles();
  loadGoogleSheetsConfig();
  loadHistory();
  loadPrinters();
});

// 切換分頁
function switchTab(tabId) {
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  
  const currentTabElem = Array.from(document.querySelectorAll(".nav-tab")).find(el => el.getAttribute("onclick").includes(tabId));
  if (currentTabElem) currentTabElem.classList.add("active");
  document.getElementById(tabId).classList.add("active");

  if (tabId === "tab-history") {
    loadHistory();
  }
}

// 載入平台與課程設定
async function loadConfigs() {
  try {
    const res = await fetch("/api/configs");
    globalConfigs = await res.json();
    
    // 渲染平台下拉選單
    const selPlat = document.getElementById("selPlatform");
    selPlat.innerHTML = "";
    globalConfigs.platforms.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.id.toUpperCase()})`;
      selPlat.appendChild(opt);
    });

    selPlat.onchange = onPlatformChange;

    renderCoursesTable();
    renderPlatformsTable();
  } catch (err) {
    console.error("載入設定失敗:", err);
  }
}

function onPlatformChange() {
  const platId = document.getElementById("selPlatform").value;
  const ppaCard = document.getElementById("ppaCard");
  if (platId === "ppa") {
    ppaCard.style.display = "block";
    calcPpaLive();
  } else {
    ppaCard.style.display = "none";
  }
}

function calcPpaLive() {
  const gross = parseFloat(document.getElementById("ppaInputGross").value || 0);
  const marketing = parseFloat(document.getElementById("ppaInputMarketing").value || 0);
  const cost = parseFloat(document.getElementById("ppaInputCost").value || 0);

  // 1. 未稅消費總額
  const untaxedGross = gross / 1.05;
  // 2. 金流手續費 (實付金額 2.25%)
  const gatewayFee = gross * 0.0225;
  // 3. 平台計算基準 (未稅消費 - 金流)
  const platformBase = untaxedGross - gatewayFee;
  // 4. 平台服務費 (20%)
  const platformFee = platformBase * 0.20;
  // 5. 行銷費用 (CSF 負擔 80% 未稅)
  const untaxedMarketing = marketing / 1.05;
  const csfMarketing = untaxedMarketing * 0.80;
  // 6. CSF 銷售所得 (未稅)
  const salesIncomeUntaxed = untaxedGross - gatewayFee - platformFee - csfMarketing;
  // 7. 發票請款總額 (含稅 5%)
  const invoiceGross = salesIncomeUntaxed * 1.05;
  // 8. 講師分潤試算 (扣除製作費用後 50%)
  const netProfit = salesIncomeUntaxed - cost;
  const teacherShare = netProfit * 0.50;

  const grid = document.getElementById("ppaResultGrid");
  grid.innerHTML = `
    <div class="metric-card" style="background: white; border-top: 3px solid #64748b;">
      <div class="metric-label">1. 金流手續費 (2.25%)</div>
      <div class="metric-val" style="font-size: 1.15rem; color: #dc2626;">NT$ ${gatewayFee.toFixed(1)}</div>
      <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">${gross} × 2.25%</div>
    </div>
    <div class="metric-card" style="background: white; border-top: 3px solid #f59e0b;">
      <div class="metric-label">2. 平台服務費 (20%)</div>
      <div class="metric-val" style="font-size: 1.15rem; color: #d97706;">NT$ ${platformFee.toFixed(1)}</div>
      <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">(未稅 - 金流) × 20%</div>
    </div>
    <div class="metric-card" style="background: white; border-top: 3px solid #8b5cf6;">
      <div class="metric-label">3. 乙方分攤行銷費</div>
      <div class="metric-val" style="font-size: 1.15rem; color: #7c3aed;">NT$ ${csfMarketing.toFixed(1)}</div>
      <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">未稅行銷費 × 80%</div>
    </div>
    <div class="metric-card" style="background: white; border-top: 3px solid #059669;">
      <div class="metric-label">4. CSF 銷售所得 (未稅)</div>
      <div class="metric-val" style="font-size: 1.15rem; color: #059669;">NT$ ${salesIncomeUntaxed.toFixed(1)}</div>
      <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">未稅消費 - 金流 - 平台 - 行銷</div>
    </div>
    <div class="metric-card" style="background: #eff6ff; border: 2px solid #2563eb; border-top: 4px solid #1d4ed8;">
      <div class="metric-label" style="font-weight: 700; color: #1e40af;">5. 發票請款總額 (含稅)</div>
      <div class="metric-val" style="font-size: 1.25rem; color: #1e40af;">NT$ ${Math.round(invoiceGross).toLocaleString()}</div>
      <div style="font-size: 0.72rem; color: #2563eb; margin-top: 0.2rem;">未稅所得 × 1.05 (整數開立)</div>
    </div>
  `;
}

// 偵測資料夾中的現有檔案
async function refreshDetectedFiles(isReset = false) {
  try {
    const res = await fetch("/api/detect_files");
    const data = await res.json();
    const files = data.files || [];

    const selUser = document.getElementById("selUserFile");
    const selPlat = document.getElementById("selPlatFile");

    selUser.innerHTML = '<option value="">-- 請選擇自填明細檔案 --</option>';
    selPlat.innerHTML = '<option value="">-- 請選擇平台對帳檔案 --</option>';

    files.forEach(f => {
      if (f.ext === ".xlsx" || f.ext === ".xls") {
        const optU = document.createElement("option");
        optU.value = f.path;
        optU.textContent = `${f.name}`;
        
        const optP = document.createElement("option");
        optP.value = f.path;
        optP.textContent = `${f.name}`;

        // 智慧預選 (非重置模式下才預選)
        if (!isReset) {
          if (f.name.includes("平台版稅明細") && !f.name.includes("老師")) {
            optU.selected = true;
          }
          if (f.name.includes("對帳")) {
            optP.selected = true;
          }
        }

        selUser.appendChild(optU);
        selPlat.appendChild(optP);
      }
    });

    // 監聽下拉選單變更以同步更新提示
    selUser.onchange = () => syncFileBadge('user');
    selPlat.onchange = () => syncFileBadge('platform');

    if (!isReset) {
      syncFileBadge('user');
      syncFileBadge('platform');
    }

  } catch (err) {
    console.error("偵測檔案失敗:", err);
  }
}

// ----------------------------------------------------
// 檔案手動自選 (桌面 / 檔案總管) 與上傳
// ----------------------------------------------------
async function chooseFile(type) {
  const isUser = type === 'user';
  const title = isUser 
    ? "請選取【使用者自填明細表】Excel 活頁簿 (桌面或檔案總管)" 
    : "請選取【平台方郵件寄送對帳單】Excel 活頁簿 (桌面或檔案總管)";

  const btn = event ? event.currentTarget : null;
  const originalHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.innerHTML = "⏳ 選取中...";
    btn.disabled = true;
  }

  try {
    const res = await fetch("/api/choose_file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, title })
    });
    const data = await res.json();
    if (data.selected && data.path) {
      applySelectedFile(type, data.path, data.filename);
      alert(`✅ 已成功指定檔案：\n${data.filename}\n\n路徑：${data.path}`);
    } else if (data.error) {
      alert("開啟本機檔案視窗失敗: " + data.error);
    }
  } catch (err) {
    alert("叫起系統檔案選取視窗失敗: " + err.message);
  } finally {
    if (btn) {
      btn.innerHTML = originalHtml;
      btn.disabled = false;
    }
  }
}

// 透過瀏覽器選取檔案或上傳
async function handleFileUpload(type, inputElem) {
  const file = inputElem.files[0];
  if (!file) return;

  const btn = inputElem.nextElementSibling;
  const originalHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.innerHTML = "⏳ 載入中...";
    btn.disabled = true;
  }

  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const base64 = e.target.result.split(",")[1];
      const res = await fetch("/api/upload_file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          content: base64
        })
      });
      const data = await res.json();
      if (data.success) {
        applySelectedFile(type, data.path, data.filename);
        alert(`✅ 檔案載入成功，已帶入選單！\n\n檔名：${data.filename}`);
      } else {
        alert("上傳失敗: " + (data.error || "未知錯誤"));
      }
    } catch (err) {
      alert("檔案處理異常: " + err.message);
    } finally {
      if (btn) {
        btn.innerHTML = originalHtml;
        btn.disabled = false;
      }
      inputElem.value = "";
    }
  };
  reader.readAsDataURL(file);
}

// 套用選取的檔案路徑至下拉選單與提示徽章
function applySelectedFile(type, fullPath, filename) {
  const isUser = type === 'user';
  const sel = document.getElementById(isUser ? "selUserFile" : "selPlatFile");
  const badge = document.getElementById(isUser ? "userSelectedBadge" : "platSelectedBadge");
  const nameSpan = document.getElementById(isUser ? "userSelectedName" : "platSelectedName");
  const pathSpan = document.getElementById(isUser ? "userSelectedPath" : "platSelectedPath");

  if (!sel) return;

  const normFullPath = fullPath.replace(/\\/g, '/');

  // 若下拉選單已存在相同路徑或相同檔名的選項，直接更新該選項
  let opt = Array.from(sel.options).find(o => {
    const oValNorm = (o.value || '').replace(/\\/g, '/');
    return oValNorm === normFullPath || o.text.trim() === filename || o.text.includes(filename);
  });

  if (!opt) {
    opt = document.createElement("option");
    sel.appendChild(opt);
  }

  opt.value = fullPath;
  opt.textContent = `📁 ${filename}`;
  opt.selected = true;

  sel.value = fullPath;
  sel.selectedIndex = Array.from(sel.options).indexOf(opt);

  if (badge && nameSpan && pathSpan) {
    badge.style.display = "flex";
    nameSpan.textContent = `✅ 已指定：${filename}`;
    pathSpan.textContent = ` (${fullPath})`;
  }

  // 觸發變更事件以確保聯動更新
  sel.dispatchEvent(new Event('change'));
}

function syncFileBadge(type) {
  const isUser = type === 'user';
  const sel = document.getElementById(isUser ? "selUserFile" : "selPlatFile");
  const badge = document.getElementById(isUser ? "userSelectedBadge" : "platSelectedBadge");
  const nameSpan = document.getElementById(isUser ? "userSelectedName" : "platSelectedName");
  const pathSpan = document.getElementById(isUser ? "userSelectedPath" : "platSelectedPath");

  if (!sel || !sel.value) {
    if (badge) badge.style.display = "none";
    return;
  }
  const text = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : "";
  if (badge && nameSpan && pathSpan) {
    badge.style.display = "flex";
    nameSpan.textContent = `✅ 已選取：${text}`;
    pathSpan.textContent = ` (${sel.value})`;
  }
}

function clearSelectedFile(type) {
  const isUser = type === 'user';
  const sel = document.getElementById(isUser ? "selUserFile" : "selPlatFile");
  const badge = document.getElementById(isUser ? "userSelectedBadge" : "platSelectedBadge");
  if (sel) sel.value = "";
  if (badge) badge.style.display = "none";
}

// ----------------------------------------------------
// 恢復原狀為從頭開始 (Reset / Start Over)
// ----------------------------------------------------
async function resetToInitialState() {
  // 1. 重設年份、月份、平台為預設值
  document.getElementById("selRocYear").value = "115";
  document.getElementById("selMonth").value = "8";
  document.getElementById("selPlatform").value = "104";
  onPlatformChange();

  // 2. 清空檔案選取與提示標籤
  document.getElementById("selUserFile").value = "";
  document.getElementById("selPlatFile").value = "";
  clearSelectedFile('user');
  clearSelectedFile('platform');

  // 3. 隱藏核對結果與審計看板
  currentAuditResult = null;
  const auditCard = document.getElementById("auditCard");
  if (auditCard) auditCard.style.display = "none";

  // 4. 隱藏產出檔案卡片並清空清單
  const resultFilesCard = document.getElementById("resultFilesCard");
  if (resultFilesCard) resultFilesCard.style.display = "none";
  clearOutputFiles();

  // 5. 重新掃描本機資料夾 (isReset = true: 保持空白讓使用者自主選取)
  await refreshDetectedFiles(true);

  // 6. 完成提示
  alert("🔄 已成功恢復原狀！\n所有選擇與核對結果已重置，您可以重新選取檔案從頭開始。");
}

// 執行核對
async function runReconciliation() {
  const userFile = document.getElementById("selUserFile").value;
  const platFile = document.getElementById("selPlatFile").value;
  const rocYear = document.getElementById("selRocYear").value;
  const month = document.getElementById("selMonth").value;
  const platformId = document.getElementById("selPlatform").value;
  currentPeriodStr = `${rocYear}年${month}月`;

  const pObj = globalConfigs.platforms.find(p => p.id === platformId);
  currentPlatformName = pObj ? pObj.name : "104平台";

  if (!userFile || !platFile) {
    alert("請先選擇自填表單與平台對帳單！");
    return;
  }

  try {
    const res = await fetch("/api/reconcile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_file: userFile, platform_file: platFile, platform_id: platformId })
    });

    const data = await res.json();
    if (data.error) {
      alert("核對發生錯誤: " + data.error);
      return;
    }

    currentAuditResult = data;
    renderAuditResults(data);
  } catch (err) {
    alert("連線失敗: " + err.message);
  }
}

// 渲染核對分析看板
function renderAuditResults(data) {
  const auditCard = document.getElementById("auditCard");
  auditCard.style.display = "block";

  // 狀態徽章
  const badge = document.getElementById("auditStatusBadge");
  badge.className = `status-pill ${data.status.toLowerCase()}`;
  badge.textContent = data.status_text;

  // 指標卡片
  const metricCards = document.getElementById("metricCards");
  metricCards.innerHTML = "";

  data.audit_items.forEach(item => {
    const card = document.createElement("div");
    card.className = "metric-card";
    const isOk = item.matched;
    card.innerHTML = `
      <div class="metric-label">${item.label}</div>
      <div class="metric-val">${item.platform_val}</div>
      <div class="metric-diff ${isOk ? 'metric-matched' : 'metric-mismatched'}">
        <span>${isOk ? '✔ 完全吻合' : '✖ 差異: ' + item.diff}</span>
      </div>
    `;
    metricCards.appendChild(card);
  });

  // 細項表格
  const tbody = document.querySelector("#reconcileItemsTable tbody");
  tbody.innerHTML = "";

  const items = data.user_data.items || [];
  items.forEach(it => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.no}</td>
      <td style="font-weight: 600;">${it.course_name}</td>
      <td class="text-right">NT$ ${it.price.toLocaleString()}</td>
      <td class="text-center">${it.qty}</td>
      <td class="text-right" style="color: var(--primary); font-weight: 700;">NT$ ${Math.round(it.royalty_gross).toLocaleString()}</td>
      <td class="text-right">NT$ ${Math.round(it.net_amount).toLocaleString()}</td>
      <td class="text-center"><span style="color: var(--success); font-weight: 600;">✔ 通過</span></td>
    `;
    tbody.appendChild(tr);
  });

  auditCard.scrollIntoView({ behavior: "smooth" });
}

// 匯入系統資料庫
// 匯入系統資料庫
async function importToSystem(silent = false) {
  if (!currentAuditResult) {
    if (!silent) alert("請先完成對帳核對！");
    return;
  }
  const platformId = document.getElementById("selPlatform").value;
  try {
    const res = await fetch("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        period: currentPeriodStr,
        platform_id: platformId,
        audit_result: currentAuditResult
      })
    });
    const data = await res.json();
    if (!silent) {
      alert("匯入成功！已歸檔至系統資料庫。");
    }
    loadHistory();
  } catch (err) {
    if (!silent) alert("匯入失敗: " + err.message);
  }
}

// 產出發票申請單 Word
async function generateInvoiceDoc() {
  if (!currentAuditResult) {
    alert("請先完成對帳核對！");
    return;
  }
  const platformId = document.getElementById("selPlatform").value;
  const rocYear = document.getElementById("selRocYear").value;
  const month = document.getElementById("selMonth").value;
  
  const plat = globalConfigs.platforms.find(p => p.id === platformId) || {
    name: "一零四資訊科技股份有限公司",
    tax_id: "84598349"
  };

  const userMeta = (currentAuditResult.user_data && currentAuditResult.user_data.meta) || {};
  const applyDate = userMeta.apply_date || getInvoiceApplyDate(rocYear, month);
  const expectedDeposit = userMeta.expected_deposit_date || getDepositDateFromApplyDate(applyDate, rocYear, month);

  try {
    const res = await fetch("/api/generate_invoice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform_id: platformId,
        title: plat.name,
        tax_id: plat.tax_id,
        amount: currentAuditResult.final_invoice_amount,
        roc_year: rocYear,
        month: month,
        apply_date: applyDate,
        expected_deposit_date: expectedDeposit
      })
    });
    const data = await res.json();
    if (data.success) {
      addOutputFile({
        name: data.filename,
        path: data.file_path,
        icon: "📄",
        type: "發票請款申請單 (Word)"
      });
      // 自動同步歸檔至歷史資料庫
      await importToSystem(true);
      loadHistory();
      alert(`已成功生成發票請款單！\n檔案已存於：\n${data.file_path}`);
    } else {
      alert("生成失敗: " + data.error);
    }
  } catch (err) {
    alert("產生請款單失敗: " + err.message);
  }
}

// 結算並產出講師分潤 Excel
async function settleTeacherRoyalty() {
  if (!currentAuditResult) {
    alert("請先完成對帳核對！");
    return;
  }
  const platformId = document.getElementById("selPlatform").value;
  const items = currentAuditResult.user_data.items;
  const plat = globalConfigs.platforms.find(p => p.id === platformId);
  const platName = plat ? (plat.name.includes("一零四") ? "104平台" : plat.name) : "104平台";

  try {
    const res = await fetch("/api/settle_teacher", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        period: currentPeriodStr,
        items: items,
        platform_name: platName,
        platform_id: platformId
      })
    });
    const data = await res.json();
    if (data.success) {
      data.teachers.forEach(t => {
        addOutputFile({
          name: t.filename,
          path: t.file_path,
          icon: "📊",
          type: `講師分潤明細 (${t.teacher_name}老師)`
        });
      });
      // 自動同步歸檔至歷史資料庫
      await importToSystem(true);
      loadHistory();
      alert(`已成功結算並產生 ${data.teachers.length} 位講師的版稅明細 Excel！`);
    } else {
      alert("講師結算失敗: " + data.error);
    }
  } catch (err) {
    alert("計算失敗: " + err.message);
  }
}

// 同步數據至 Google Sheet
async function syncCurrentToGoogleSheets() {
  if (!currentAuditResult) {
    alert("請先完成對帳核對！");
    return;
  }
  const platformId = document.getElementById("selPlatform").value;
  const plat = globalConfigs.platforms.find(p => p.id === platformId);
  const platName = plat ? plat.name : "104學習平台";
  const items = currentAuditResult.user_data.items;
  const summary = currentAuditResult.user_data.summary;

  const invoiceInfo = {
    title: plat ? plat.name : "",
    tax_id: plat ? plat.tax_id : "",
    expected_deposit_date: ""
  };

  try {
    const res = await fetch("/api/google_sheets/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        period: currentPeriodStr,
        platform_id: platformId,
        platform_name: platName,
        items: items,
        summary: summary,
        invoice_info: invoiceInfo,
        ppa_details: currentAuditResult.ppa_details || null
      })
    });
    const data = await res.json();
    if (data.success) {
      await importToSystem(true);
      loadHistory();
      alert(`🎉 ${data.message}`);
    } else {
      alert(`提示：${data.message || data.error}\n請點選上方「🌐 Google Sheet 自動串聯」分頁設定 Webhook 網址！`);
      switchTab("tab-googlesheets");
    }
  } catch (err) {
    alert("連線 Google Sheet 失敗: " + err.message);
  }
}

// 一鍵全自動月結
async function runBatchAll() {
  const userFile = document.getElementById("selUserFile").value;
  const platFile = document.getElementById("selPlatFile").value;
  const rocYear = document.getElementById("selRocYear").value;
  const month = document.getElementById("selMonth").value;
  const platformId = document.getElementById("selPlatform").value;

  if (!userFile || !platFile) {
    alert("請先選擇自填表單與平台對帳單！");
    return;
  }

  try {
    const res = await fetch("/api/batch_run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_file: userFile,
        platform_file: platFile,
        roc_year: rocYear,
        month: month,
        platform_id: platformId
      })
    });
    const data = await res.json();
    if (data.success) {
      currentAuditResult = data.audit;
      renderAuditResults(data.audit);
      
      clearOutputFiles();
      addOutputFile({
        name: data.invoice_file.split(/[\\/]/).pop(),
        path: data.invoice_file,
        icon: "📄",
        type: "發票請款申請單 (Word)"
      });
      data.teacher_files.forEach(t => {
        addOutputFile({
          name: t.path.split(/[\\/]/).pop(),
          path: t.path,
          icon: "📊",
          type: `講師分潤明細 (${t.teacher}老師)`
        });
      });

      // 自動嘗試同步至 Google Sheet
      syncCurrentToGoogleSheets();

      alert(`🎉 全自動月結處理完成！\n1. 雙向對帳完全相符\n2. 數據已歸檔系統\n3. 已產出發票請款申請單 Word\n4. 已產出各講師版稅明細 Excel\n\n存檔目錄：${data.output_dir}`);
    } else {
      alert("月結失敗: " + data.error);
    }
  } catch (err) {
    alert("批次執行失敗: " + err.message);
  }
}

// 產出檔案列表管理
function clearOutputFiles() {
  document.getElementById("outputFilesList").innerHTML = "";
}

function addOutputFile(fileObj) {
  const card = document.getElementById("resultFilesCard");
  card.style.display = "block";
  const list = document.getElementById("outputFilesList");

  const safePath = (fileObj.path || "").replace(/\\/g, '/');
  const docType = fileObj.docType || (fileObj.name.endsWith('.docx') ? 'invoice' : 'settlement');
  const item = document.createElement("div");
  item.className = "output-item";
  item.innerHTML = `
    <div class="output-item-info">
      <span class="output-item-icon">${fileObj.icon}</span>
      <div>
        <div class="output-filename">${fileObj.name}</div>
        <div class="output-path">${fileObj.type} &bull; ${fileObj.path}</div>
      </div>
    </div>
    <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
      <button class="btn btn-print btn-sm" onclick="openPrintModal({ filePath: '${safePath}', docType: '${docType}' })" title="預覽並直接送至實體影印機列印">
        🖨️ 列印預覽
      </button>
      <button class="btn btn-secondary btn-sm" onclick="openFilePath('${safePath}')">
        📄 開啟檔案
      </button>
      <button class="btn btn-secondary btn-sm" onclick="openFileFolder('${safePath}')">
        📂 資料夾
      </button>
    </div>
  `;
  list.appendChild(item);
}

// 開啟資料夾
function openCurrentFolder() {
  fetch("/api/open_folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
}

function openPeriodFolder() {
  fetch("/api/open_folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_path: "" })
  });
}

function openFilePath(fullPath) {
  fetch("/api/open_folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_path: fullPath })
  });
}

function openFileFolder(fullPath) {
  const norm = fullPath.replace(/\\/g, '/');
  const dir = norm.substring(0, norm.lastIndexOf("/"));
  fetch("/api/open_folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_path: dir || fullPath })
  });
}

// ----------------------------------------------------
// 課程與講師 Modal 與 CRUD
// ----------------------------------------------------
function renderCoursesTable() {
  const tbody = document.querySelector("#coursesTable tbody");
  tbody.innerHTML = "";
  globalConfigs.courses.forEach(c => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="font-weight: 600;">${c.course_name}</td>
      <td>${c.platform_id.toUpperCase()}</td>
      <td style="color: var(--primary); font-weight: 600;">${c.teacher_name}</td>
      <td class="text-right">NT$ ${c.price.toLocaleString()}</td>
      <td class="text-center">${(c.teacher_share_rate * 100).toFixed(0)}%</td>
      <td class="text-right">NT$ ${c.production_cost.toLocaleString()}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${c.note || ''}</td>
      <td class="text-center">
        <button class="btn btn-secondary btn-sm" onclick="openEditCourseModal('${c.id}')">✏️ 編輯</button>
        <button class="btn btn-secondary btn-sm" style="color: var(--danger);" onclick="deleteCourse('${c.id}')">🗑️</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openAddCourseModal() {
  document.getElementById("courseModalTitle").textContent = "新增課程分潤規則";
  document.getElementById("modalCourseId").value = "c_" + Date.now();
  document.getElementById("modalCourseName").value = "";
  document.getElementById("modalCourseTeacher").value = "";
  document.getElementById("modalCoursePrice").value = "1288";
  document.getElementById("modalCourseShareRate").value = "0.5";
  document.getElementById("modalCourseCost").value = "0";
  document.getElementById("modalCourseNote").value = "扣除平台服務費";

  populatePlatformSelectInModal();
  document.getElementById("courseModal").classList.add("active");
}

function openEditCourseModal(id) {
  const c = globalConfigs.courses.find(item => item.id === id);
  if (!c) return;
  document.getElementById("courseModalTitle").textContent = "編輯課程分潤規則";
  document.getElementById("modalCourseId").value = c.id;
  document.getElementById("modalCourseName").value = c.course_name;
  document.getElementById("modalCourseTeacher").value = c.teacher_name;
  document.getElementById("modalCoursePrice").value = c.price;
  document.getElementById("modalCourseShareRate").value = c.teacher_share_rate;
  document.getElementById("modalCourseCost").value = c.production_cost;
  document.getElementById("modalCourseNote").value = c.note || "";

  populatePlatformSelectInModal(c.platform_id);
  document.getElementById("courseModal").classList.add("active");
}

function populatePlatformSelectInModal(selectedId) {
  const sel = document.getElementById("modalCoursePlatform");
  sel.innerHTML = "";
  globalConfigs.platforms.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.id.toUpperCase()})`;
    if (p.id === selectedId) opt.selected = true;
    sel.appendChild(opt);
  });
}

function closeCourseModal() {
  document.getElementById("courseModal").classList.remove("active");
}

async function saveCourseFromModal() {
  const id = document.getElementById("modalCourseId").value;
  const course_name = document.getElementById("modalCourseName").value.trim();
  const platform_id = document.getElementById("modalCoursePlatform").value;
  const teacher_name = document.getElementById("modalCourseTeacher").value.trim();
  const price = parseFloat(document.getElementById("modalCoursePrice").value || 0);
  const teacher_share_rate = parseFloat(document.getElementById("modalCourseShareRate").value || 0.5);
  const production_cost = parseFloat(document.getElementById("modalCourseCost").value || 0);
  const note = document.getElementById("modalCourseNote").value.trim();

  if (!course_name || !teacher_name) {
    alert("請輸入課程名稱與授課講師！");
    return;
  }

  try {
    const res = await fetch("/api/course/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id, course_name, platform_id, teacher_name, price,
        teacher_share_rate, production_cost, note
      })
    });
    const data = await res.json();
    if (data.success) {
      closeCourseModal();
      loadConfigs();
      alert("課程分潤規則儲存成功！");
    }
  } catch (err) {
    alert("儲存失敗: " + err.message);
  }
}

async function deleteCourse(id) {
  if (!confirm("確定要刪除這筆課程設定嗎？")) return;
  try {
    const res = await fetch("/api/course/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    const data = await res.json();
    if (data.success) {
      alert("課程設定已成功刪除！");
      loadConfigs();
    } else {
      alert("刪除失敗: " + (data.error || "未知錯誤"));
    }
  } catch (err) {
    alert("刪除失敗: " + err.message);
  }
}

// ----------------------------------------------------
// 平台 Modal 與 CRUD
// ----------------------------------------------------
function renderPlatformsTable() {
  const tbody = document.querySelector("#platformsTable tbody");
  tbody.innerHTML = "";
  globalConfigs.platforms.forEach(p => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${p.id}</code></td>
      <td style="font-weight: 600;">${p.name}</td>
      <td><code>${p.tax_id}</code></td>
      <td>${p.revenue_type}</td>
      <td>${p.item_name}</td>
      <td class="text-center">${(p.commission_rate * 100).toFixed(0)}%</td>
      <td>次月月底</td>
      <td>${p.note || ''}</td>
      <td class="text-center">
        <button class="btn btn-secondary btn-sm" onclick="openEditPlatformModal('${p.id}')">✏️ 編輯</button>
        <button class="btn btn-secondary btn-sm" style="color: var(--danger);" onclick="deletePlatform('${p.id}')">🗑️</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openAddPlatformModal() {
  document.getElementById("platformModalTitle").textContent = "新增合作平台";
  document.getElementById("modalPlatId").value = "";
  document.getElementById("modalPlatId").readOnly = false;
  document.getElementById("modalPlatName").value = "";
  document.getElementById("modalPlatTaxId").value = "";
  document.getElementById("modalPlatRate").value = "0.8";
  document.getElementById("modalPlatItem").value = "線上課程訂閱";
  document.getElementById("modalPlatRevType").value = "版稅收入";
  document.getElementById("modalPlatNote").value = "";
  document.getElementById("platformModal").classList.add("active");
}

function openEditPlatformModal(id) {
  const p = globalConfigs.platforms.find(item => item.id === id);
  if (!p) return;
  document.getElementById("platformModalTitle").textContent = "編輯合作平台";
  document.getElementById("modalPlatId").value = p.id;
  document.getElementById("modalPlatId").readOnly = true; // 鍵值不可變
  document.getElementById("modalPlatName").value = p.name;
  document.getElementById("modalPlatTaxId").value = p.tax_id;
  document.getElementById("modalPlatRate").value = p.commission_rate;
  document.getElementById("modalPlatItem").value = p.item_name;
  document.getElementById("modalPlatRevType").value = p.revenue_type;
  document.getElementById("modalPlatNote").value = p.note || "";
  document.getElementById("platformModal").classList.add("active");
}

function closePlatformModal() {
  document.getElementById("platformModal").classList.remove("active");
}

async function savePlatformFromModal() {
  const id = document.getElementById("modalPlatId").value.trim().toLowerCase();
  const name = document.getElementById("modalPlatName").value.trim();
  const tax_id = document.getElementById("modalPlatTaxId").value.trim();
  const commission_rate = parseFloat(document.getElementById("modalPlatRate").value || 0.8);
  const item_name = document.getElementById("modalPlatItem").value.trim();
  const revenue_type = document.getElementById("modalPlatRevType").value.trim();
  const note = document.getElementById("modalPlatNote").value.trim();

  if (!id || !name || !tax_id) {
    alert("請填寫平台代碼、抬頭全名與統一編號！");
    return;
  }

  try {
    const res = await fetch("/api/platform/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id, name, tax_id, commission_rate, item_name, revenue_type, note
      })
    });
    const data = await res.json();
    if (data.success) {
      closePlatformModal();
      loadConfigs();
      alert("平台設定儲存成功！");
    }
  } catch (err) {
    alert("儲存失敗: " + err.message);
  }
}

async function deletePlatform(id) {
  if (!confirm(`確定要刪除平台 [${id}] 嗎？`)) return;
  try {
    const res = await fetch("/api/platform/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    const data = await res.json();
    if (data.success) {
      alert(`已成功刪除合作平台 [${id}]！`);
      loadConfigs();
    } else {
      alert("刪除失敗: " + (data.error || "未知錯誤"));
    }
  } catch (err) {
    alert("刪除失敗: " + err.message);
  }
}

// ----------------------------------------------------
// Google Sheets 設定與連線管理
// ----------------------------------------------------
async function loadGoogleSheetsConfig() {
  try {
    const res = await fetch("/api/google_sheets/config");
    const data = await res.json();
    document.getElementById("gsPlatformWebhook").value = data.platform_webhook_url || "";
    document.getElementById("gsTeacherWebhook").value = data.teacher_webhook_url || "";
    gasCodeSnippet = data.gas_code || "";
    gasPlatformCode = data.gas_platform_code || data.gas_code || "";
    gasTeacherCode = data.gas_teacher_code || data.gas_code || "";
  } catch (err) {
    console.error("載入 Google Sheets 設定失敗:", err);
  }
}

async function saveGoogleSheetsConfig() {
  const platform_webhook_url = document.getElementById("gsPlatformWebhook").value.trim();
  const teacher_webhook_url = document.getElementById("gsTeacherWebhook").value.trim();

  try {
    const res = await fetch("/api/google_sheets/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform_webhook_url, teacher_webhook_url })
    });
    const data = await res.json();
    if (data.success) {
      alert("Google Sheets 雙表設定已成功儲存！");
    }
  } catch (err) {
    alert("儲存設定失敗: " + err.message);
  }
}

async function testGoogleSheetsSync() {
  const platform_webhook_url = document.getElementById("gsPlatformWebhook").value.trim();
  const teacher_webhook_url = document.getElementById("gsTeacherWebhook").value.trim();

  if (!platform_webhook_url && !teacher_webhook_url) {
    alert("請至少填入【平台對帳表】或【講師分潤表】其中一個 Google Apps Script Webhook 網址！");
    return;
  }
  await saveGoogleSheetsConfig();

  // 發送測試資料
  try {
    const testItems = [{
      course_name: "測試課程:AI與數據分析實戰",
      price: 1288,
      qty: 1,
      platform_gross: 1030,
      net_amount: 981,
      tax_amount: 49,
      royalty_gross: 1030
    }];
    const testSummary = { total_qty: 1, total_gross: 1030 };

    const res = await fetch("/api/google_sheets/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        period: "115年測試期",
        platform_id: "104",
        platform_name: "104學習平台",
        items: testItems,
        summary: testSummary,
        invoice_info: { title: "測試公司", tax_id: "84598349", expected_deposit_date: "115年10月31日" },
        teacher_settlements: {
          "侯玉彤": [{
            course_name: "測試課程:AI與數據分析實戰",
            platform_net: 1030,
            production_cost: 0,
            net_profit: 1030,
            share_rate_str: "50%",
            payable: 515,
            note: "測試同步"
          }]
        }
      })
    });
    const data = await res.json();
    alert(`執行結果：\n${data.message}`);
  } catch (err) {
    alert("測試異常: " + err.message);
  }
}

function copyPlatformGasCode() {
  const code = gasPlatformCode || gasCodeSnippet;
  if (!code) {
    alert("程式碼載入中，請稍候重試");
    return;
  }
  navigator.clipboard.writeText(code).then(() => {
    alert("📋 已複製【試算表 ① 平台對帳表 (104/PPA)】Apps Script 程式碼！\n\n請前往您的【平台對帳請款表】Google Sheet：\n1. 點擊「擴充功能」>「Apps Script」\n2. 清空並貼上程式碼\n3. 點擊「部署」>「新部署」>「網頁應用程式 (所有人)」\n4. 複製產生的網址貼回系統即可。");
  }).catch(() => {
    alert("複製失敗，請手動複製程式碼。");
  });
}

function copyTeacherGasCode() {
  const code = gasTeacherCode || gasCodeSnippet;
  if (!code) {
    alert("程式碼載入中，請稍候重試");
    return;
  }
  navigator.clipboard.writeText(code).then(() => {
    alert("📋 已複製【試算表 ② 講師分潤表 (侯玉彤/簡志峰)】Apps Script 程式碼！\n\n請前往您的【講師分潤結算表】Google Sheet：\n1. 點擊「擴充功能」>「Apps Script」\n2. 清空並貼上程式碼\n3. 點擊「部署」>「新部署」>「網頁應用程式 (所有人)」\n4. 複製產生的網址貼回系統即可。");
  }).catch(() => {
    alert("複製失敗，請手動複製程式碼。");
  });
}

function copyGasCode() {
  copyPlatformGasCode();
}

// ----------------------------------------------------
// 歷史紀錄
// ----------------------------------------------------
async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();

    // 1. 發票請款單存檔表格
    const invTbody = document.querySelector("#historyInvoiceTable tbody");
    if (invTbody) {
      invTbody.innerHTML = "";
      const invoices = data.invoices || [];
      if (invoices.length === 0) {
        invTbody.innerHTML = '<tr><td colspan="8" class="text-center" style="color: var(--text-muted); padding: 1.25rem;">尚無已開立之《發票收據申請單》存檔紀錄</td></tr>';
      } else {
        invoices.forEach(inv => {
          const tr = document.createElement("tr");
          const fname = inv.file_path ? inv.file_path.split(/[\\\\/]/).pop() : "附件1_發票收據申請單.docx";
          tr.innerHTML = `
            <td style="font-weight: 600;">${inv.period}</td>
            <td>${inv.apply_date}</td>
            <td><strong>${inv.title}</strong></td>
            <td><code>${inv.tax_id}</code></td>
            <td class="text-right" style="color: var(--primary); font-weight: 700;">NT$ ${Number(inv.amount).toLocaleString()}</td>
            <td>${inv.expected_deposit_date}</td>
            <td><span style="font-size: 0.85rem; color: #334155;">📄 ${fname}</span></td>
            <td class="text-center" style="white-space: nowrap;">
              <button class="btn btn-print btn-sm" onclick="openPrintModal({ type: 'invoice', id: ${inv.id}, filePath: '${(inv.file_path || '').replace(/\\/g, '/')}' })">🖨️ 列印預覽</button>
              <button class="btn btn-secondary btn-sm" onclick="openFilePath('${(inv.file_path || '').replace(/\\/g, '/')}')">📄 開啟</button>
              <button class="btn btn-secondary btn-sm" onclick="openFileFolder('${(inv.file_path || '').replace(/\\/g, '/')}')">📂 目錄</button>
              <button class="btn btn-secondary btn-sm" style="color: var(--danger); font-weight: 600;" onclick="deleteHistoryItem('invoice', ${inv.id})" title="刪除此筆發票請款單存檔">🗑️ 刪除</button>
            </td>
          `;
          invTbody.appendChild(tr);
        });
      }
    }

    // 2. 講師分潤結算明細表格
    const setTbody = document.querySelector("#historySettlementTable tbody");
    if (setTbody) {
      setTbody.innerHTML = "";
      const settlements = data.settlements || [];
      if (settlements.length === 0) {
        setTbody.innerHTML = '<tr><td colspan="11" class="text-center" style="color: var(--text-muted); padding: 1.25rem;">尚無講師版稅分潤結算紀錄</td></tr>';
      } else {
        settlements.forEach(s => {
          const tr = document.createElement("tr");
          const fname = s.excel_path ? s.excel_path.split(/[\\/]/).pop() : "講師版稅明細.xlsx";
          tr.innerHTML = `
            <td style="font-weight: 600;">${s.period}</td>
            <td style="color: #065f46; font-weight: 700;">${s.teacher_name}</td>
            <td style="max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${s.course_name}">${s.course_name}</td>
            <td>${(s.platform_id || '').toUpperCase()}</td>
            <td class="text-right">NT$ ${Math.round(s.platform_net).toLocaleString()}</td>
            <td class="text-right">NT$ ${Math.round(s.production_cost).toLocaleString()}</td>
            <td class="text-right">NT$ ${Math.round(s.net_profit).toLocaleString()}</td>
            <td class="text-center">${(s.share_rate * 100).toFixed(0)}%</td>
            <td class="text-right" style="color: #0f766e; font-weight: 700;">NT$ ${Number(s.payable_amount).toLocaleString()}</td>
            <td><span style="font-size: 0.85rem; color: #334155;">📊 ${fname}</span></td>
            <td class="text-center" style="white-space: nowrap;">
              <button class="btn btn-print btn-sm" onclick="openPrintModal({ type: 'settlement', id: ${s.id}, filePath: '${(s.excel_path || '').replace(/\\/g, '/')}' })">🖨️ 列印預覽</button>
              <button class="btn btn-secondary btn-sm" onclick="openFilePath('${(s.excel_path || '').replace(/\\/g, '/')}')">📊 開啟</button>
              <button class="btn btn-secondary btn-sm" onclick="openFileFolder('${(s.excel_path || '').replace(/\\/g, '/')}')">📂 目錄</button>
              <button class="btn btn-secondary btn-sm" style="color: var(--danger); font-weight: 600;" onclick="deleteHistoryItem('settlement', ${s.id})" title="刪除此筆講師結算紀錄">🗑️ 刪除</button>
            </td>
          `;
          setTbody.appendChild(tr);
        });
      }
    }

    // 3. 雙向對帳審核紀錄表格
    const reconTbody = document.querySelector("#historyTable tbody");
    if (reconTbody) {
      reconTbody.innerHTML = "";
      const recons = data.reconciliations || [];
      if (recons.length === 0) {
        reconTbody.innerHTML = '<tr><td colspan="8" class="text-center" style="color: var(--text-muted); padding: 1.25rem;">尚無歷史對帳審核紀錄</td></tr>';
      } else {
        recons.forEach(h => {
          const tr = document.createElement("tr");
          const isMatched = h.status === "MATCHED";
          tr.innerHTML = `
            <td style="font-weight: 600;">${h.period}</td>
            <td>${(h.platform_id || '').toUpperCase()}</td>
            <td class="text-center">${h.total_qty} 件</td>
            <td class="text-right" style="color: var(--primary); font-weight: 600;">NT$ ${Math.round(h.supplier_gross).toLocaleString()}</td>
            <td class="text-right">NT$ ${Math.round(h.supplier_net).toLocaleString()}</td>
            <td class="text-center"><span style="color: ${isMatched ? 'var(--success)' : 'var(--danger)'}; font-weight: 600;">${isMatched ? '✔ 核對相符' : '✖ 差異'}</span></td>
            <td style="color: var(--text-muted); font-size: 0.8rem;">${h.created_at}</td>
            <td class="text-center" style="white-space: nowrap;">
              <button class="btn btn-secondary btn-sm" style="color: var(--danger); font-weight: 600;" onclick="deleteHistoryItem('reconciliation', ${h.id})" title="刪除此筆對帳審核紀錄">🗑️ 刪除</button>
            </td>
          `;
          reconTbody.appendChild(tr);
        });
      }
    }
  } catch (err) {
    console.error("載入歷史失敗:", err);
  }
}

// 刪除單筆歷史紀錄
async function deleteHistoryItem(type, id) {
  const typeMap = {
    invoice: "發票收據申請單存檔",
    settlement: "講師版稅分潤結算",
    reconciliation: "雙向對帳審核紀錄"
  };
  const typeTitle = typeMap[type] || "歷史紀錄";

  if (!confirm(`⚠️ 確定要刪除此筆【${typeTitle}】嗎？\n\n此操作將自系統歷史庫中移除該筆資料。`)) {
    return;
  }

  try {
    const res = await fetch("/api/history/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, id })
    });
    const data = await res.json();
    if (data.success) {
      loadHistory();
    } else {
      alert("刪除失敗: " + (data.error || "未知錯誤"));
    }
  } catch (err) {
    alert("刪除請求異常: " + err.message);
  }
}

// ====================================================
// 🖨️ 實體影印機與文件列印中心模組
// ====================================================

let defaultPrinterName = "";
let availablePrinters = [];
let printState = {
  currentTab: "",
  tabs: [],
  currentOfficeFile: ""
};

// 載入系統已安裝之實體影印機與印表機
async function loadPrinters() {
  try {
    const res = await fetch("/api/printers");
    const data = await res.json();
    defaultPrinterName = data.default_printer || "";
    availablePrinters = data.printers || [];
    updatePrinterBadge();
  } catch (err) {
    console.warn("載入印表機狀態失敗:", err);
  }
}

function updatePrinterBadge() {
  const badge = document.getElementById("printPrinterBadge");
  if (!badge) return;
  if (defaultPrinterName) {
    badge.textContent = `🖨️ 實體影印機：${defaultPrinterName}`;
    badge.className = "status-pill matched";
    badge.title = `已自動連線 Windows 預設影印機: ${defaultPrinterName}\n可用設備: ${availablePrinters.join(', ')}`;
  } else {
    badge.textContent = `🖨️ 使用系統標準影印機/印表機`;
    badge.className = "status-pill matched";
  }
}

// 開啟列印與預覽中心
async function openPrintModal(options = {}) {
  await loadPrinters();
  printState.tabs = [];
  printState.currentOfficeFile = "";

  // 1. 若指定特定檔案或歷史紀錄 ID
  if (options.filePath || options.id) {
    try {
      const res = await fetch("/api/print_doc_data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_path: options.filePath || "",
          doc_type: options.docType || options.type || "",
          id: options.id || null
        })
      });
      const data = await res.json();
      if (!data.success) {
        alert("讀取列印資料失敗: " + (data.error || "未知錯誤"));
        return;
      }

      printState.currentOfficeFile = data.file_path || options.filePath || "";

      if (data.type === "invoice") {
        printState.tabs.push({
          key: "invoice",
          title: "📄 發票請款申請單 (Word)",
          type: "invoice",
          data: data,
          filePath: data.file_path
        });
      } else if (data.type === "settlement") {
        printState.tabs.push({
          key: "settle_0",
          title: `📊 講師明細 (${data.teacher_name}老師)`,
          type: "settlement",
          data: data,
          filePath: data.file_path
        });
      }
    } catch (err) {
      alert("連線取得文件列印資料失敗: " + err.message);
      return;
    }
  }
  // 2. 使用當前對帳結果 (currentAuditResult)
  else if (currentAuditResult) {
    const platformId = document.getElementById("selPlatform").value;
    const rocYear = document.getElementById("selRocYear").value;
    const month = document.getElementById("selMonth").value;
    const periodStr = `${rocYear}年${month}月`;
    const plat = globalConfigs.platforms.find(p => p.id === platformId) || {
      name: "一零四資訊科技股份有限公司",
      tax_id: "84598349",
      item_name: "線上課程訂閱"
    };

    // A. 建立發票請款單預覽資料 (依使用者自填表右上角日期及隔月底計算)
    const userMeta = (currentAuditResult.user_data && currentAuditResult.user_data.meta) || {};
    const applyDate = userMeta.apply_date || getInvoiceApplyDate(rocYear, month);
    const expectedDeposit = userMeta.expected_deposit_date || getDepositDateFromApplyDate(applyDate, rocYear, month);

    const invData = {
      type: "invoice",
      dept: "綜合推廣中心",
      apply_date: applyDate,
      title: plat.name,
      amount: `NT$${Number(currentAuditResult.final_invoice_amount).toLocaleString()}`,
      tax_id: plat.tax_id,
      item_name: plat.item_name || "線上課程訂閱",
      expected_deposit_date: expectedDeposit,
      period: periodStr,
      file_path: ""
    };

    printState.tabs.push({
      key: "invoice",
      title: "📄 發票收據申請單 (Word)",
      type: "invoice",
      data: invData
    });

    // B. 建立各講師版稅明細資料
    const items = currentAuditResult.user_data.items;
    const teacherMap = {};
    items.forEach(it => {
      let cConfig = globalConfigs.courses.find(c => c.course_name === it.course_name || it.course_name.includes(c.course_name) || c.course_name.includes(it.course_name));
      const tName = cConfig ? cConfig.teacher_name : "侯玉彤";
      const shareRate = cConfig ? cConfig.teacher_share_rate : 0.5;
      const cost = cConfig ? cConfig.production_cost : (tName === "侯玉彤" ? 1069 : 0);
      const note = cConfig ? cConfig.note : (tName === "侯玉彤" ? "扣除平台服務費、課程製作相關費用" : "扣除平台服務費");

      if (!teacherMap[tName]) teacherMap[tName] = [];
      const price = it.price;
      const qty = it.qty;
      const rawPlat = it.platform_gross !== undefined ? it.platform_gross : (price * qty * 0.8);
      const platNet = Math.round(rawPlat);
      const netProfit = platNet - cost;
      const payable = Math.round(netProfit * shareRate * 10) / 10;

      teacherMap[tName].push({
        no: teacherMap[tName].length + 1,
        course_name: it.course_name,
        price: price,
        qty: qty,
        platform_net: platNet,
        production_cost: cost,
        net_profit: netProfit,
        share_rate_str: `${Math.round(shareRate * 100)}%`,
        payable: payable,
        note: note
      });
    });

    let tIdx = 0;
    for (const [tName, tItems] of Object.entries(teacherMap)) {
      printState.tabs.push({
        key: `settle_${tIdx}`,
        title: `📊 講師明細 (${tName}老師)`,
        type: "settlement",
        data: {
          teacher_name: tName,
          period: periodStr,
          platform_name: plat.name.includes("一零四") ? "104學習平台" : (plat.name.includes("瑞奧") ? "PressPlay Academy" : plat.name),
          items: tItems
        }
      });
      tIdx++;
    }

    if (printState.tabs.length > 1) {
      printState.tabs.push({
        key: "all",
        title: "📑 全部連續預覽 (請款單 + 講師明細)",
        type: "all"
      });
    }
  }
  // 3. 尚未執行核對
  else {
    try {
      const res = await fetch("/api/history");
      const hist = await res.json();
      if (hist.invoices && hist.invoices.length > 0) {
        const latestInv = hist.invoices[0];
        openPrintModal({ filePath: latestInv.file_path, type: 'invoice', id: latestInv.id });
        return;
      }
    } catch (e) {}

    alert("請先完成「雙向對帳核對」或點選「產出 Word/Excel 表單」，即可在此直接預覽與列印！");
    return;
  }

  printState.currentTab = printState.tabs[0].key;
  renderPrintTabs();
  renderPrintPreview();
  document.getElementById("printModal").classList.add("active");
}

function closePrintModal() {
  document.getElementById("printModal").classList.remove("active");
}

function renderPrintTabs() {
  const container = document.getElementById("printDocTabs");
  container.innerHTML = "";
  printState.tabs.forEach(t => {
    const btn = document.createElement("button");
    btn.className = `print-tab-btn ${t.key === printState.currentTab ? 'active' : ''}`;
    btn.textContent = t.title;
    btn.onclick = () => {
      printState.currentTab = t.key;
      renderPrintTabs();
      renderPrintPreview();
    };
    container.appendChild(btn);
  });
}

function renderPrintPreview() {
  const viewport = document.getElementById("printPreviewViewport");
  viewport.innerHTML = "";

  const currentTabObj = printState.tabs.find(t => t.key === printState.currentTab);
  if (!currentTabObj) return;

  const btnOffice = document.getElementById("btnOpenOfficeCurrent");
  if (currentTabObj.filePath) {
    btnOffice.style.display = "inline-flex";
    printState.currentOfficeFile = currentTabObj.filePath;
  } else {
    btnOffice.style.display = printState.currentOfficeFile ? "inline-flex" : "none";
  }

  if (currentTabObj.type === "invoice") {
    viewport.innerHTML = buildInvoiceDocHtml(currentTabObj.data);
  } else if (currentTabObj.type === "settlement") {
    viewport.innerHTML = buildTeacherSettlementDocHtml(currentTabObj.data);
  } else if (currentTabObj.type === "all") {
    let combinedHtml = "";
    printState.tabs.forEach(t => {
      if (t.type === "invoice") {
        combinedHtml += buildInvoiceDocHtml(t.data);
      } else if (t.type === "settlement") {
        combinedHtml += buildTeacherSettlementDocHtml(t.data);
      }
    });
    viewport.innerHTML = combinedHtml;
  }
}

function openCurrentOfficeDoc() {
  if (printState.currentOfficeFile) {
    openFilePath(printState.currentOfficeFile);
  } else {
    alert("尚未產出實體 Office 檔案，請先點選「產出 Word」或「結算 Excel」即可開啟本機檔案！");
  }
}

// 🖨️ 確認列印：直接連到本機實體影印機，呼叫標準列印對話框
function confirmPrintCurrentDoc() {
  const container = document.getElementById("printPreviewViewport");
  if (!container || !container.innerHTML.trim()) {
    alert("目前無可列印的文件內容！");
    return;
  }

  let printIframe = document.getElementById("hiddenPrintIframe");
  if (!printIframe) {
    printIframe = document.createElement("iframe");
    printIframe.id = "hiddenPrintIframe";
    printIframe.style.position = "fixed";
    printIframe.style.right = "0";
    printIframe.style.bottom = "0";
    printIframe.style.width = "0";
    printIframe.style.height = "0";
    printIframe.style.border = "none";
    document.body.appendChild(printIframe);
  }

  const doc = printIframe.contentWindow.document;
  doc.open();
  doc.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>列印文件 - 線上課程版稅銷售與請款結算系統</title>
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: "標楷體", "Microsoft JhengHei", "新細明體", sans-serif; }
        @page {
          size: A4 portrait;
          margin: 12mm 15mm 12mm 15mm;
        }
        body {
          background: white;
          color: #000;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        .a4-paper-sheet {
          width: 100%;
          min-height: auto;
          page-break-after: always;
          margin-bottom: 25px;
        }
        .a4-paper-sheet:last-child {
          page-break-after: avoid;
          margin-bottom: 0;
        }
        .invoice-doc-title { text-align: center; font-size: 15pt; font-weight: bold; margin-bottom: 2px; }
        .invoice-doc-subtitle { text-align: center; font-size: 18pt; font-weight: bold; letter-spacing: 5px; margin-bottom: 12px; }
        .invoice-doc-table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 9.5pt; }
        .invoice-doc-table th, .invoice-doc-table td { border: 1px solid #000; padding: 5px 8px; vertical-align: middle; }
        .invoice-doc-table th { background-color: #f5f5f5 !important; text-align: center; font-weight: bold; }
        .invoice-checkbox { font-weight: bold; font-size: 11pt; margin-right: 2px; }
        .invoice-notes { font-size: 8.5pt; color: #111; line-height: 1.5; margin-top: 10px; }
        
        .settle-doc-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 8px; }
        .settle-doc-title { font-size: 14pt; font-weight: bold; }
        .settle-doc-period { font-size: 11pt; font-weight: bold; }
        .settle-doc-table { width: 100%; border-collapse: collapse; font-size: 9pt; margin-bottom: 16px; }
        .settle-doc-table th, .settle-doc-table td { border: 1px solid #000; padding: 6px 6px; }
        .settle-doc-table th { background-color: #f5f5f5 !important; text-align: center; font-weight: bold; }
        .settle-signatures { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 24px; }
        .settle-sig-box { border: 1px solid #000; height: 64px; padding: 4px 8px; font-size: 8.5pt; display: flex; flex-direction: column; justify-content: space-between; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
      </style>
    </head>
    <body>
      ${container.innerHTML}
    </body>
    </html>
  `);
  doc.close();

  setTimeout(() => {
    printIframe.contentWindow.focus();
    printIframe.contentWindow.print();
  }, 250);
}

// 日期推算輔助函式
function getInvoiceApplyDate(rocYear, month) {
  let y = parseInt(rocYear);
  let m = parseInt(month) + 1;
  if (m > 12) { m -= 12; y += 1; }
  return `${y}年${String(m).padStart(2, '0')}月03日`;
}

function getInvoiceDepositDate(rocYear, month) {
  let adYear = parseInt(rocYear) + 1911;
  let targetMonth = parseInt(month) + 2;
  let targetYear = adYear;
  if (targetMonth > 12) {
    targetMonth -= 12;
    targetYear += 1;
  }
  let lastDay = new Date(targetYear, targetMonth, 0).getDate();
  let targetRoc = targetYear - 1911;
  return `${targetRoc}年${String(targetMonth).padStart(2, '0')}月${String(lastDay).padStart(2, '0')}日`;
}

// 依據「申請日期」計算「申請日期的隔月底」
function getDepositDateFromApplyDate(applyDateStr, fallbackRocYear = 115, fallbackMonth = 8) {
  if (!applyDateStr) return getInvoiceDepositDate(fallbackRocYear, fallbackMonth);

  let rocYear = null;
  let month = null;

  const m1 = applyDateStr.match(/(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if (m1) {
    rocYear = parseInt(m1[1]) - 1911;
    month = parseInt(m1[2]);
  } else {
    const m2 = applyDateStr.match(/(\d{2,3})[年/-](\d{1,2})[月/-](\d{1,2})/);
    if (m2) {
      rocYear = parseInt(m2[1]);
      month = parseInt(m2[2]);
    }
  }

  if (!rocYear || !month) {
    rocYear = parseInt(fallbackRocYear);
    month = parseInt(fallbackMonth) + 1;
  }

  // 隔月 = month + 1
  let adYear = rocYear + 1911;
  let targetMonth = month + 1;
  let targetYear = adYear;
  if (targetMonth > 12) {
    targetMonth -= 12;
    targetYear += 1;
  }
  let lastDay = new Date(targetYear, targetMonth, 0).getDate();
  let targetRoc = targetYear - 1911;
  return `${targetRoc}年${String(targetMonth).padStart(2, '0')}月${String(lastDay).padStart(2, '0')}日`;
}

// 產生《附件1_發票收據申請單》標準 A4 仿真 HTML
function buildInvoiceDocHtml(inv) {
  const amountStr = typeof inv.amount === 'number' 
    ? `NT$${Number(inv.amount).toLocaleString()}` 
    : String(inv.amount).startsWith('NT$') ? inv.amount : `NT$${inv.amount}`;
  const depStr = inv.expected_deposit_date 
    ? (inv.expected_deposit_date.startsWith('(') ? inv.expected_deposit_date : `(預計) ${inv.expected_deposit_date}`) 
    : '(預計) 下個月底';

  return `
  <div class="a4-paper-sheet" id="printSheetInvoice">
    <div class="invoice-doc-title">財團法人中華民國電腦技能基金會</div>
    <div class="invoice-doc-subtitle">發票收據申請單</div>
    
    <table class="invoice-doc-table">
      <colgroup>
        <col style="width: 14%;">
        <col style="width: 36%;">
        <col style="width: 18%;">
        <col style="width: 32%;">
      </colgroup>
      <tr>
        <th>部門</th>
        <td>${inv.dept || '綜合推廣中心'}</td>
        <th>申請日期</th>
        <td style="font-weight: bold;">${inv.apply_date}</td>
      </tr>
      <tr>
        <th>專案名稱 /<br>考場名稱</th>
        <td>${inv.project_name || '&nbsp;'}</td>
        <th>專案編號 /<br>試務編號</th>
        <td>${inv.project_code || '&nbsp;'}</td>
      </tr>
      <tr>
        <th>檢附相關文件</th>
        <td colspan="3">
          契約　報價單　<span class="invoice-checkbox">☑</span><strong>其他：分潤明細</strong>
        </td>
      </tr>
    </table>

    <div style="font-weight: bold; margin-bottom: 4px; font-size: 10pt; color: #111;">2. 開立資料及種類</div>
    <table class="invoice-doc-table">
      <colgroup>
        <col style="width: 10%;">
        <col style="width: 15%;">
        <col style="width: 12%;">
        <col style="width: 15%;">
        <col style="width: 12%;">
        <col style="width: 12%;">
        <col style="width: 12%;">
        <col style="width: 12%;">
      </colgroup>
      <tr>
        <th>抬頭</th>
        <td colspan="4" style="font-weight: bold; font-size: 10.5pt;">${inv.title}</td>
        <th>金額</th>
        <td colspan="2" style="font-weight: bold; font-size: 11pt; color: #0f172a; text-align: right;">${amountStr}</td>
      </tr>
      <tr>
        <th rowspan="2">種類</th>
        <td colspan="5">
          <span class="invoice-checkbox">☑</span>發票：
          <span class="invoice-checkbox">☑</span><strong>有統編，請填統編：${inv.tax_id}</strong>
        </td>
        <td colspan="2">
          <span class="invoice-checkbox">☐</span>無統編
        </td>
      </tr>
      <tr>
        <td colspan="7">
          <span class="invoice-checkbox">☐</span>收據 (限測驗、換證、成績複查)
        </td>
      </tr>
      <tr>
        <th rowspan="3">收入</th>
        <td><span class="invoice-checkbox">☑</span><strong>版稅收入</strong></td>
        <td><span class="invoice-checkbox">☐</span>授權收入</td>
        <td><span class="invoice-checkbox">☐</span>會員收入</td>
        <td><span class="invoice-checkbox">☐</span>專案收入</td>
        <td colspan="3"><span class="invoice-checkbox">☐</span>書籍收入</td>
      </tr>
      <tr>
        <td><span class="invoice-checkbox">☐</span>選務計票</td>
        <td><span class="invoice-checkbox">☐</span>租金收入</td>
        <td><span class="invoice-checkbox">☐</span>排版收入</td>
        <td><span class="invoice-checkbox">☐</span>展覽收入</td>
        <td colspan="3"><span class="invoice-checkbox">☐</span>研習收入</td>
      </tr>
      <tr>
        <td><span class="invoice-checkbox">☐</span>測驗收入</td>
        <td><span class="invoice-checkbox">☐</span>換證收入</td>
        <td><span class="invoice-checkbox">☐</span>成績複查</td>
        <td><span class="invoice-checkbox">☐</span>其他收入</td>
        <td colspan="3"></td>
      </tr>
      <tr>
        <th>品名</th>
        <td colspan="7">
          (請詳填品名) <strong>${inv.item_name || '線上課程訂閱'}</strong>
        </td>
      </tr>
    </table>

    <div style="font-weight: bold; margin-bottom: 4px; font-size: 10pt; color: #111;">3. 入帳資料</div>
    <table class="invoice-doc-table">
      <colgroup>
        <col style="width: 14%;">
        <col style="width: 36%;">
        <col style="width: 14%;">
        <col style="width: 36%;">
      </colgroup>
      <tr>
        <th>已入帳</th>
        <td>　　年　　月　　日</td>
        <th>入帳方式</th>
        <td>1. 匯款 (合庫北 / 一銀 / 國泰世華)</td>
      </tr>
      <tr>
        <th>未入帳</th>
        <td colspan="3" style="font-weight: bold; color: #1e3a8a; font-size: 10pt;">
          ${depStr}
        </td>
      </tr>
    </table>

    <div style="font-weight: bold; margin-bottom: 4px; font-size: 10pt; color: #111;">4. 簽核</div>
    <table class="invoice-doc-table">
      <colgroup>
        <col style="width: 50%;">
        <col style="width: 50%;">
      </colgroup>
      <tr>
        <th style="height: 24px;">主管 ②</th>
        <th>申請人 ①</th>
      </tr>
      <tr>
        <td style="height: 60px; vertical-align: bottom; color: #64748b; font-size: 8.5pt;">(簽章)</td>
        <td style="height: 60px; vertical-align: bottom; color: #64748b; font-size: 8.5pt;">(簽名/蓋章)</td>
      </tr>
    </table>

    <div style="font-weight: bold; margin-bottom: 4px; font-size: 10pt; color: #111;">5. 開立</div>
    <table class="invoice-doc-table">
      <colgroup>
        <col style="width: 18%;">
        <col style="width: 22%;">
        <col style="width: 18%;">
        <col style="width: 22%;">
        <col style="width: 20%;">
      </colgroup>
      <tr>
        <th>發票收據號碼</th>
        <td>&nbsp;</td>
        <th>收款確認</th>
        <td>&nbsp;</td>
        <th style="text-align: center;">會計 / 出納</th>
      </tr>
    </table>

    <div class="invoice-notes">
      <strong>注意事項：</strong><br>
      1. 說明：專案編號「ICT業管系統專案編號；其他近似管理編號」；試務編號「ICT業管系統申領表試務編號；CWT業管系統申領表梯次編號」。<br>
      2. 品名填寫規則，詳見《附件2_發票收據品名對照表》。<br>
      3. 申請流程：經辦 ➔ 主管簽核 ➔ 會計/出納 (開立發票/收據)。原申請單由會計行政部門留存，經辦請自留影本備查。<br>
      4. 如需作廢，請務必於開立後次月5號前提出申請。
    </div>
  </div>
  `;
}

// 產生《各講師版稅明細表》標準 A4 仿真 HTML
function buildTeacherSettlementDocHtml(settle) {
  let totalPrice = 0;
  let totalQty = 0;
  let totalPlatNet = 0;
  let totalCost = 0;
  let totalNetProfit = 0;
  let totalPayable = 0;

  const rows = (settle.items || []).map((it, idx) => {
    const price = Number(it.price || 0);
    const qty = Number(it.qty || 0);
    const platNet = Number(it.platform_net || 0);
    const cost = Number(it.production_cost || it.cost || 0);
    const netProfit = Number(it.net_profit !== undefined ? it.net_profit : (platNet - cost));
    const payable = Number(it.payable || 0);

    totalPrice += price;
    totalQty += qty;
    totalPlatNet += platNet;
    totalCost += cost;
    totalNetProfit += netProfit;
    totalPayable += payable;

    const netProfitColor = netProfit < 0 ? 'color: #dc2626;' : '';
    const payableColor = payable < 0 ? 'color: #dc2626; font-weight: bold;' : 'color: #047857; font-weight: bold;';

    return `
      <tr>
        <td class="text-center">${it.no || idx + 1}</td>
        <td style="font-weight: 600;">${it.course_name}</td>
        <td class="text-right">NT$ ${price.toLocaleString()}</td>
        <td class="text-center">${qty}</td>
        <td class="text-right">NT$ ${Math.round(platNet).toLocaleString()}</td>
        <td class="text-right">NT$ ${Math.round(cost).toLocaleString()}</td>
        <td class="text-right" style="${netProfitColor}">NT$ ${Math.round(netProfit).toLocaleString()}</td>
        <td class="text-center">${it.share_rate_str || '50%'}</td>
        <td class="text-right" style="${payableColor}">NT$ ${payable.toLocaleString()}</td>
        <td style="font-size: 8pt; color: #475569;">${it.note || ''}</td>
      </tr>
    `;
  }).join("");

  return `
  <div class="a4-paper-sheet" id="printSheetSettlement_${settle.teacher_name}">
    <div class="settle-doc-header">
      <div class="settle-doc-title">講師 ：${settle.teacher_name}老師</div>
      <div style="text-align: center;">
        <div style="font-size: 15pt; font-weight: bold; letter-spacing: 2px;">線上課程講師版稅分潤結算表</div>
        <div style="font-size: 10pt; color: #475569;">${settle.platform_name || '104學習平台'}</div>
      </div>
      <div class="settle-doc-period">${settle.period}</div>
    </div>

    <table class="settle-doc-table">
      <thead>
        <tr>
          <th style="width: 4%;">NO.</th>
          <th style="width: 32%;">課程名稱</th>
          <th style="width: 9%;" class="text-right">定價</th>
          <th style="width: 6%;" class="text-center">數量</th>
          <th style="width: 11%;" class="text-right">平台淨額(80%)</th>
          <th style="width: 10%;" class="text-right">課程製作費用</th>
          <th style="width: 9%;" class="text-right">結餘淨利</th>
          <th style="width: 7%;" class="text-center">講師分潤</th>
          <th style="width: 9%;" class="text-right">本期應付</th>
          <th style="width: 13%;">備註</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
      <tfoot>
        <tr style="background-color: #f8fafc; font-weight: bold;">
          <td colspan="2" class="text-center">合計 (Total)</td>
          <td class="text-right">NT$ ${totalPrice.toLocaleString()}</td>
          <td class="text-center">${totalQty}</td>
          <td class="text-right">NT$ ${Math.round(totalPlatNet).toLocaleString()}</td>
          <td class="text-right">NT$ ${Math.round(totalCost).toLocaleString()}</td>
          <td class="text-right" style="color: ${totalNetProfit < 0 ? '#dc2626' : '#0f172a'};">
            NT$ ${Math.round(totalNetProfit).toLocaleString()}
          </td>
          <td class="text-center">-</td>
          <td class="text-right" style="color: ${totalPayable < 0 ? '#dc2626' : '#047857'}; font-size: 10.5pt;">
            NT$ ${totalPayable.toLocaleString()}
          </td>
          <td></td>
        </tr>
      </tfoot>
    </table>

    <div style="font-size: 8.5pt; color: #475569; margin-top: 4px; line-height: 1.4;">
      會計計算說明：平台扣除服務費淨額 = 定價 × 數量 × 80%；結餘淨利 = 平台淨額 - 課程製作相關費用；本期應付 = 結餘淨利 × 講師分潤比例。
    </div>

    <div class="settle-signatures">
      <div class="settle-sig-box">
        <div>授課講師簽章：</div>
        <div style="text-align: right; color: #94a3b8;">年　月　日</div>
      </div>
      <div class="settle-sig-box">
        <div>經辦人員：</div>
        <div style="text-align: right; color: #94a3b8;">年　月　日</div>
      </div>
      <div class="settle-sig-box">
        <div>單位主管覆核：</div>
        <div style="text-align: right; color: #94a3b8;">年　月　日</div>
      </div>
      <div class="settle-sig-box">
        <div>會計部門覆核：</div>
        <div style="text-align: right; color: #94a3b8;">年　月　日</div>
      </div>
    </div>
  </div>
  `;
}
