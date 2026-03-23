const fs = require("fs");
const path = require("path");

function getChromium() {
  try {
    return require("playwright").chromium;
  } catch {
    const fallbackPlaywrightPath = path.join(__dirname, "..", "..", "frontend", "node_modules", "playwright");
    return require(fallbackPlaywrightPath).chromium;
  }
}

async function autofillForm(sessionData) {
  const chromium = getChromium();
  console.log("Automation started");
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  try {
    await page.goto("http://127.0.0.1:5173/demo-form", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(800);

    const fieldMapPath = path.join(__dirname, "field_map.json");
    const fieldMap = JSON.parse(fs.readFileSync(fieldMapPath, "utf8"));

    async function fillWithRetry(selector, value, retries = 3) {
      for (let attempt = 1; attempt <= retries; attempt += 1) {
        try {
          await page.waitForSelector(selector, { timeout: 2500 });
          await page.fill(selector, String(value));
          return true;
        } catch (error) {
          if (attempt === retries) {
            console.error(`Failed to fill ${selector} after retries`, error);
            return false;
          }
          await page.waitForTimeout(400);
        }
      }
      return false;
    }

    for (const key of Object.keys(fieldMap)) {
      const selector = fieldMap[key];
      const value = sessionData?.user_profile?.[key];

      if (!value) continue;

      const filled = await fillWithRetry(selector, value);
      if (filled) {
        console.log(`Field filled: ${key}`);
      }
      await page.waitForTimeout(300);
    }

    console.log("Automation completed");

    return "done";
  } catch (error) {
    console.error("Autofill failed:", error);
    return "failed";
  }
}

async function main() {
  let payloadFilePath;
  try {
    payloadFilePath = process.argv[2];
    if (!payloadFilePath) {
      throw new Error("Session payload path is required");
    }

    const raw = fs.readFileSync(payloadFilePath, "utf8");
    const sessionData = JSON.parse(raw);
    await autofillForm(sessionData);
  } catch (error) {
    console.error("Autofill service error:", error);
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
