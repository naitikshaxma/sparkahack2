const fs = require("fs");
const path = require("path");

const NAVIGATION_RETRIES = 3;
const FIELD_FILL_RETRIES = 3;
const RETRY_DELAY_MS = 500;
const SELECTOR_TIMEOUT_MS = 2500;
const DEFAULT_FIELD_TIMEOUT_MS = 3000;
const FIELD_VALIDATION_TIMEOUT_MS = 1200;
const ENABLE_RELOAD_RETRY = (process.env.AUTOFILL_ENABLE_RELOAD_RETRY || "true").toLowerCase() !== "false";
const RELOAD_FAIL_RATIO_THRESHOLD = Number(process.env.AUTOFILL_RELOAD_FAIL_RATIO_THRESHOLD || 0.5);
const RELOAD_RETRY_MAX = 1;

function normalizeSchemeName(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return "loan assistance";
  if (raw.includes("pm kisan")) return "pm kisan";
  if (raw.includes("ayushman")) return "ayushman bharat";
  if (raw.includes("pmay") || raw.includes("housing")) return "pmay";
  if (raw.includes("loan")) return "loan assistance";
  return raw;
}

function resolveAutomationConfig(sessionData, mapping) {
  const selectedScheme = normalizeSchemeName(sessionData?.selected_scheme || sessionData?.last_scheme || "");
  const schemeConfig = mapping[selectedScheme] || mapping.default || {};
  return {
    selectedScheme,
    formUrl: schemeConfig.form_url || "/demo-form",
    formSelector: schemeConfig.form_selector || mapping.form_selector || null,
    fieldMap: schemeConfig.field_map || mapping.field_map || {},
  };
}

function getChromium() {
  try {
    return require("playwright").chromium;
  } catch {
    const fallbackPlaywrightPath = path.join(__dirname, "..", "..", "frontend", "node_modules", "playwright");
    return require(fallbackPlaywrightPath).chromium;
  }
}

function toHumanLabel(key) {
  return String(key || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeRegex(text) {
  return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeLabel(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function labelSimilarity(a, b) {
  const left = normalizeLabel(a);
  const right = normalizeLabel(b);
  if (!left || !right) return 0;
  if (left === right) return 1;
  if (left.includes(right) || right.includes(left)) return 0.85;
  const leftTokens = new Set(left.split(" "));
  const rightTokens = new Set(right.split(" "));
  let overlap = 0;
  for (const token of leftTokens) {
    if (rightTokens.has(token)) overlap += 1;
  }
  return overlap / Math.max(leftTokens.size, rightTokens.size, 1);
}

function buildSelectorCandidates(fieldConfig, fieldKey) {
  const fallback = [
    `#${fieldKey}`,
    `[name="${fieldKey}"]`,
    `[id="${fieldKey}"]`,
    `[aria-label*="${toHumanLabel(fieldKey)}" i]`,
  ];

  if (typeof fieldConfig === "string") {
    return [fieldConfig, ...fallback];
  }

  if (Array.isArray(fieldConfig)) {
    return [...fieldConfig, ...fallback];
  }

  if (fieldConfig && typeof fieldConfig === "object") {
    const selectors = Array.isArray(fieldConfig.selectors)
      ? fieldConfig.selectors
      : typeof fieldConfig.selector === "string"
        ? [fieldConfig.selector]
        : [];
    return [...selectors, ...fallback];
  }

  return fallback;
}

function buildLabelCandidates(fieldConfig, fieldKey) {
  const labels = [toHumanLabel(fieldKey)];

  if (fieldConfig && typeof fieldConfig === "object") {
    if (typeof fieldConfig.label === "string" && fieldConfig.label.trim()) {
      labels.push(fieldConfig.label.trim());
    }
    if (Array.isArray(fieldConfig.labels)) {
      for (const label of fieldConfig.labels) {
        if (typeof label === "string" && label.trim()) {
          labels.push(label.trim());
        }
      }
    }
  }

  return Array.from(new Set(labels.filter(Boolean)));
}

function nowStamp() {
  const iso = new Date().toISOString();
  return iso.replace(/[:.]/g, "-");
}

function asNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function getFieldTimeoutMs(fieldConfig) {
  if (fieldConfig && typeof fieldConfig === "object") {
    if (fieldConfig.timeout_ms !== undefined) {
      return asNumber(fieldConfig.timeout_ms, DEFAULT_FIELD_TIMEOUT_MS);
    }
    if (fieldConfig.timeout !== undefined) {
      return asNumber(fieldConfig.timeout, DEFAULT_FIELD_TIMEOUT_MS);
    }
  }
  return DEFAULT_FIELD_TIMEOUT_MS;
}

function logStep(step, details = {}) {
  const payload = {
    ts: new Date().toISOString(),
    step,
    ...details,
  };
  console.log(`AUTOFILL_STEP:${JSON.stringify(payload)}`);
}

async function getElementValue(locator) {
  return locator.evaluate((el) => {
    if (!el) return "";
    if (el.tagName === "SELECT") {
      const select = el;
      return String(select.value || "");
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      return String(el.value || "");
    }
    return String(el.textContent || "");
  });
}

async function validateFilledValue(locator, expectedValue) {
  try {
    await locator.waitFor({ state: "attached", timeout: FIELD_VALIDATION_TIMEOUT_MS });
    const actual = await getElementValue(locator);
    const expected = String(expectedValue || "").trim();
    if (!expected) {
      return { ok: true, actual };
    }

    const normalizedActual = String(actual || "").trim();
    const compactExpected = expected.replace(/\s+/g, "");
    const compactActual = normalizedActual.replace(/\s+/g, "");
    const ok = normalizedActual === expected || compactActual === compactExpected;
    return { ok, actual: normalizedActual };
  } catch (error) {
    return { ok: false, actual: "", error: String(error?.message || error || "validate_error") };
  }
}

async function safeDelay(page, ms) {
  await page.waitForTimeout(ms);
}

async function saveFailureScreenshot(page, reason) {
  try {
    const dir = path.join(__dirname, "..", "..", "automation_errors");
    await fs.promises.mkdir(dir, { recursive: true });
    const filePath = path.join(dir, `${nowStamp()}.png`);
    await page.screenshot({ path: filePath, fullPage: true });
    console.error(`Saved failure screenshot (${reason}): ${filePath}`);
    return filePath;
  } catch (error) {
    console.error("Failed to save failure screenshot:", error);
    return null;
  }
}

async function gotoWithRetry(page, targetUrl) {
  let lastError = null;
  for (let attempt = 1; attempt <= NAVIGATION_RETRIES; attempt += 1) {
    try {
      logStep("navigation_attempt", { attempt, target_url: targetUrl });
      await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
      logStep("navigation_success", { attempt, target_url: targetUrl });
      return { ok: true, attempts: attempt };
    } catch (error) {
      lastError = error;
      logStep("navigation_retry", {
        attempt,
        target_url: targetUrl,
        error: String(error?.message || error || "navigation_error"),
      });
      if (attempt < NAVIGATION_RETRIES) {
        await safeDelay(page, RETRY_DELAY_MS * attempt);
      }
    }
  }
  return { ok: false, attempts: NAVIGATION_RETRIES, error: lastError };
}

async function ensurePageReady(page, formSelector) {
  logStep("page_readiness_start", { form_selector: formSelector || null });
  await page.waitForLoadState("domcontentloaded");
  if (formSelector && String(formSelector).trim()) {
    await page.waitForSelector(String(formSelector), { timeout: 8000 });
  } else {
    await page.waitForSelector("form, input, textarea, select", { timeout: 8000 });
  }
  logStep("page_readiness_ready", { form_selector: formSelector || null });
}

async function fillSelectorWithRetry(page, selector, value, fieldKey, timeoutMs, retries = FIELD_FILL_RETRIES) {
  let lastError = null;
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      logStep("field_selector_attempt", { field: fieldKey, selector, attempt, timeout_ms: timeoutMs });
      await page.waitForSelector(selector, { timeout: timeoutMs || SELECTOR_TIMEOUT_MS });
      const locator = page.locator(selector).first();
      await locator.fill(String(value));
      const validation = await validateFilledValue(locator, value);
      if (!validation.ok) {
        throw new Error(`post_fill_validation_failed actual=${validation.actual || ""}`);
      }
      logStep("field_selector_success", { field: fieldKey, selector, attempt });
      return { ok: true, method: `selector:${selector}`, attempts: attempt };
    } catch (error) {
      lastError = error;
      logStep("field_selector_retry", {
        field: fieldKey,
        selector,
        attempt,
        error: String(error?.message || error || "selector_fill_error"),
      });
      if (attempt < retries) {
        await safeDelay(page, RETRY_DELAY_MS * attempt);
      }
    }
  }
  return { ok: false, method: `selector:${selector}`, attempts: retries, error: lastError };
}

async function fillByLabelFallback(page, labelText, value, fieldKey, timeoutMs) {
  try {
    logStep("field_label_attempt", { field: fieldKey, label: labelText, timeout_ms: timeoutMs });
    let label = page.locator("label", { hasText: new RegExp(escapeRegex(labelText), "i") }).first();
    if ((await label.count()) < 1) {
      // Fuzzy label fallback for slight copy or spacing changes.
      const allLabels = page.locator("label");
      const count = await allLabels.count();
      let bestIndex = -1;
      let bestScore = 0;
      for (let idx = 0; idx < count; idx += 1) {
        const text = await allLabels.nth(idx).innerText();
        const score = labelSimilarity(text, labelText);
        if (score > bestScore) {
          bestScore = score;
          bestIndex = idx;
        }
      }
      if (bestIndex >= 0 && bestScore >= 0.55) {
        label = allLabels.nth(bestIndex);
      }
    }
    if ((await label.count()) < 1) {
      return { ok: false, method: `label:${labelText}` };
    }

    const forAttr = await label.getAttribute("for");
    if (forAttr) {
      const byFor = await fillSelectorWithRetry(page, `#${forAttr}`, value, fieldKey, timeoutMs, 1);
      if (byFor.ok) {
        logStep("field_label_success", { field: fieldKey, label: labelText, method: "label-for" });
        return { ok: true, method: `label-for:${labelText}` };
      }
    }

    const siblingInput = label
      .locator("xpath=following::input[1] | following::textarea[1] | following::select[1]")
      .first();
    if ((await siblingInput.count()) > 0) {
      await siblingInput.fill(String(value));
      const validation = await validateFilledValue(siblingInput, value);
      if (!validation.ok) {
        return { ok: false, method: `label-near:${labelText}` };
      }
      logStep("field_label_success", { field: fieldKey, label: labelText, method: "label-near" });
      return { ok: true, method: `label-near:${labelText}` };
    }

    logStep("field_label_miss", { field: fieldKey, label: labelText });
    return { ok: false, method: `label:${labelText}` };
  } catch {
    logStep("field_label_error", { field: fieldKey, label: labelText });
    return { ok: false, method: `label:${labelText}` };
  }
}

async function fillFieldWithFallback(page, fieldKey, fieldConfig, value) {
  const timeoutMs = getFieldTimeoutMs(fieldConfig);
  logStep("field_fill_start", { field: fieldKey, timeout_ms: timeoutMs });
  const selectors = buildSelectorCandidates(fieldConfig, fieldKey);
  for (const selector of selectors) {
    const attempt = await fillSelectorWithRetry(page, selector, value, fieldKey, timeoutMs, FIELD_FILL_RETRIES);
    if (attempt.ok) return attempt;
  }

  const labels = buildLabelCandidates(fieldConfig, fieldKey);
  for (const label of labels) {
    const attempt = await fillByLabelFallback(page, label, value, fieldKey, timeoutMs);
    if (attempt.ok) return attempt;
  }

  logStep("field_fill_failed", { field: fieldKey, timeout_ms: timeoutMs });
  return { ok: false, method: "none" };
}

function shouldReloadRetry(totalAttempted, failedCount) {
  if (!ENABLE_RELOAD_RETRY) return false;
  if (totalAttempted <= 0) return false;
  const ratio = failedCount / totalAttempted;
  return ratio >= Math.max(0.1, Math.min(1.0, RELOAD_FAIL_RATIO_THRESHOLD));
}

async function fillFromFieldKeys(page, config, profile, keys, filledFields, failedFields, skippedFields) {
  const pendingKeys = Array.isArray(keys) ? keys : [];
  for (const key of pendingKeys) {
    const fieldConfig = config.fieldMap[key];
    const value = profile?.[key];

    if (value === undefined || value === null || String(value).trim() === "") {
      skippedFields.push({ field: key, reason: "missing_value" });
      logStep("field_skipped", { field: key, reason: "missing_value" });
      continue;
    }

    const result = await fillFieldWithFallback(page, key, fieldConfig, value);
    if (result.ok) {
      logStep("field_filled", { field: key, method: result.method });
      filledFields.push({ field: key, method: result.method });
    } else {
      logStep("field_failed", { field: key, reason: "selector-and-label-fallback-failed" });
      failedFields.push({ field: key, value: String(value), reason: "selector-and-label-fallback-failed" });
    }
    await safeDelay(page, 280);
  }
}

async function autofillForm(sessionData) {
  const chromium = getChromium();
  console.log("Automation started");
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    logStep("autofill_start", { session_id: sessionData?.session_id || null });
    const frontendBaseUrl = process.env.AUTOFILL_FRONTEND_URL || "http://127.0.0.1:5173";
    const fieldMapPath = path.join(__dirname, "field_map.json");
    const mappingRaw = await fs.promises.readFile(fieldMapPath, "utf8");
    const mapping = JSON.parse(mappingRaw);
    const config = resolveAutomationConfig(sessionData, mapping);
    const targetUrl = `${frontendBaseUrl.replace(/\/$/, "")}${config.formUrl}`;

    const navigation = await gotoWithRetry(page, targetUrl);
    if (!navigation.ok) {
      const screenshot = await saveFailureScreenshot(page, "navigation_failed");
      return {
        status: "failed",
        error: `Navigation failed after ${navigation.attempts} attempts`,
        failed_fields: [],
        skipped_fields: [],
        filled_fields: [],
        screenshot,
      };
    }

    await ensurePageReady(page, config.formSelector);

    const filledFields = [];
    const failedFields = [];
    const skippedFields = [];

    const allFieldKeys = Object.keys(config.fieldMap || {});
    await fillFromFieldKeys(
      page,
      config,
      sessionData?.user_profile || {},
      allFieldKeys,
      filledFields,
      failedFields,
      skippedFields,
    );

    let reloadAttempted = false;
    for (let retry = 1; retry <= RELOAD_RETRY_MAX; retry += 1) {
      const attemptedCount = allFieldKeys.length - skippedFields.length;
      if (!shouldReloadRetry(attemptedCount, failedFields.length)) {
        break;
      }
      const retryCandidates = failedFields.map((item) => item.field).filter(Boolean);
      if (retryCandidates.length === 0) {
        break;
      }

      reloadAttempted = true;
      logStep("reload_retry_start", {
        attempt: retry,
        failed_count: failedFields.length,
        attempted_count: attemptedCount,
        retry_fields: retryCandidates,
      });

      await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
      await ensurePageReady(page, config.formSelector);

      const recoveredFilled = [];
      const retriedFailed = [];
      const retriedSkipped = [];
      await fillFromFieldKeys(
        page,
        config,
        sessionData?.user_profile || {},
        retryCandidates,
        recoveredFilled,
        retriedFailed,
        retriedSkipped,
      );

      if (recoveredFilled.length > 0) {
        const recoveredSet = new Set(recoveredFilled.map((item) => item.field));
        const stillFailed = failedFields.filter((item) => !recoveredSet.has(item.field));
        failedFields.length = 0;
        failedFields.push(...stillFailed);
        filledFields.push(...recoveredFilled);
      }

      if (retriedFailed.length > 0) {
        const existing = new Set(failedFields.map((item) => item.field));
        for (const item of retriedFailed) {
          if (!existing.has(item.field)) {
            failedFields.push(item);
          }
        }
      }

      logStep("reload_retry_result", {
        attempt: retry,
        recovered_count: recoveredFilled.length,
        remaining_failed_count: failedFields.length,
      });
    }

    if (filledFields.length === 0 && failedFields.length > 0) {
      logStep("autofill_failed", { reason: "all_fields_failed", reload_attempted: reloadAttempted });
      const screenshot = await saveFailureScreenshot(page, "all_fields_failed");
      return {
        status: "failed",
        error: "Failed to fill any target field",
        filled_fields: [],
        failed_fields: failedFields,
        skipped_fields: skippedFields,
        screenshot,
      };
    }

    if (failedFields.length > 0) {
      logStep("autofill_partial", {
        filled_count: filledFields.length,
        failed_count: failedFields.length,
        skipped_count: skippedFields.length,
        reload_attempted: reloadAttempted,
      });
      console.warn("Autofill failed fields:", JSON.stringify(failedFields));
      const screenshot = await saveFailureScreenshot(page, "partial_field_failure");
      return {
        status: "partial",
        filled_fields: filledFields,
        failed_fields: failedFields,
        skipped_fields: skippedFields,
        screenshot,
      };
    }

    console.log("Automation completed");
    logStep("autofill_success", {
      filled_count: filledFields.length,
      skipped_count: skippedFields.length,
      reload_attempted: reloadAttempted,
    });
    return {
      status: "success",
      filled_fields: filledFields,
      skipped_fields: skippedFields,
      failed_fields: [],
    };
  } catch (error) {
    logStep("autofill_exception", { error: String(error?.message || error || "unknown_error") });
    console.error("Autofill failed:", error);
    const screenshot = await saveFailureScreenshot(page, "unexpected_error");
    return {
      status: "failed",
      error: String(error?.message || error || "Unknown error"),
      failed_fields: [],
      skipped_fields: [],
      filled_fields: [],
      screenshot,
    };
  } finally {
    try {
      await browser.close();
    } catch {
      // Ignore browser shutdown failures.
    }
  }
}

async function main() {
  let payloadFilePath;
  try {
    payloadFilePath = process.argv[2];
    if (!payloadFilePath) {
      throw new Error("Session payload path is required");
    }

    const raw = await fs.promises.readFile(payloadFilePath, "utf8");
    const sessionData = JSON.parse(raw);
    const result = await autofillForm(sessionData);

    console.log(`AUTOFILL_STRUCTURED:${JSON.stringify(result)}`);
    const success = result && result.status === "success";
    if (success) {
      console.log("AUTOFILL_RESULT:done");
    } else {
      console.log("AUTOFILL_RESULT:failed");
    }

    if (!success) {
      process.exitCode = 1;
    }
  } catch (error) {
    console.error("Autofill service error:", error);
    process.exitCode = 1;
  } finally {
    if (payloadFilePath) {
      try {
        fs.unlinkSync(payloadFilePath);
      } catch {
        // Ignore cleanup failure.
      }
    }
  }
}

if (require.main === module) {
  void main();
}

module.exports = { autofillForm };
