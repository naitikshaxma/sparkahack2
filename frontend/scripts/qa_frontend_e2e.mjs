import { chromium } from "playwright";

const BASE_URL = "http://127.0.0.1:5173";

function parseNdjsonTypes(raw) {
  const lines = String(raw || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const types = [];
  for (const line of lines) {
    try {
      const obj = JSON.parse(line);
      if (obj && obj.type) {
        types.push(obj.type);
      }
    } catch {
      // Ignore non-JSON lines.
    }
  }
  return types;
}

function hasMetaAudioDoneOrder(types) {
  const meta = types.indexOf("meta");
  const audio = types.indexOf("audio_chunk");
  const done = types.indexOf("done");
  return meta >= 0 && audio >= 0 && done >= 0 && meta < audio && audio < done;
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleErrors = [];
  const pageErrors = [];
  const apiCalls = [];
  let streamTypes = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });

  page.on("pageerror", (err) => {
    pageErrors.push(String(err));
  });

  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/api/")) {
      return;
    }
    apiCalls.push({ url, status: response.status() });
    if (url.includes("/api/process-text-stream")) {
      try {
        const body = await response.text();
        streamTypes = parseNdjsonTypes(body);
      } catch {
        // Ignore failures on response text extraction.
      }
    }
  });

  const checks = [];
  const pushCheck = (name, ok, details = {}) => checks.push({ name, ok, details });

  try {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 60000 });

    const pageText = await page.locator("body").innerText();
    pushCheck("frontend_not_blank", pageText.trim().length > 20, { length: pageText.trim().length });

    await page.getByText("Choose Your Language", { exact: false }).waitFor({ timeout: 15000 });
    await page.getByRole("button", { name: /English/i }).click();

    await page.getByText("Let us start with your voice", { exact: false }).waitFor({ timeout: 20000 });
    pushCheck("language_selection_flow", true, { selected: "English" });

    const input = page.locator('input[aria-label="Text input"]');
    await input.fill("I need PM Kisan information");
    await page.getByRole("button", { name: "Send" }).click();

    await page.waitForTimeout(8000);

    const assistantReply = await page.locator("text=Assistant Reply").locator("xpath=..")
      .innerText()
      .catch(() => "");

    const streamOrderOk = hasMetaAudioDoneOrder(streamTypes);
    pushCheck("ui_to_backend_streaming", streamOrderOk, { streamTypes });

    const nonPlaceholder = !assistantReply.includes("Your assistant response will appear here.");
    pushCheck("ui_response_rendered", nonPlaceholder, { sample: assistantReply.slice(0, 180) });

    const consoleOk = consoleErrors.length === 0 && pageErrors.length === 0;
    pushCheck("no_console_or_runtime_errors", consoleOk, { consoleErrors, pageErrors });

    await page.route("**/api/process-text-stream", (route) => route.abort());
    await page.route("**/api/process-text", (route) => route.abort());

    await input.fill("Trigger network failure test");
    await page.getByRole("button", { name: "Send" }).click();

    const errorBanner = page.getByText("Network issue, please retry.", { exact: false });
    await errorBanner.waitFor({ timeout: 12000 });
    pushCheck("frontend_network_failure_graceful", true, {});

    await page.unroute("**/api/process-text-stream");
    await page.unroute("**/api/process-text");

    const allPassed = checks.every((item) => item.ok);
    console.log(JSON.stringify({ allPassed, checks, apiCalls: apiCalls.slice(-20) }, null, 2));
    await browser.close();
    process.exit(allPassed ? 0 : 1);
  } catch (err) {
    console.log(JSON.stringify({ allPassed: false, checks, fatal: String(err), consoleErrors, pageErrors }, null, 2));
    await browser.close();
    process.exit(1);
  }
}

run();
