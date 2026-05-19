const fs = require('fs');
const path = require('path');

function parseCheckpointMap() {
  const configured = new Map();

  for (const raw of [
    process.env.OPENCODE_DEMO_SCREENSHOT_CHECKPOINTS,
    process.env.OPENCODE_VISUAL_VALIDATION_FULL_PAGE_CHECKPOINTS,
    process.env.OPENCODE_EVIDENCE_SCREENSHOT_CHECKPOINTS,
    process.env.OPENCODE_EVIDENCE_SCREENSHOT_CHECKPOINT_PATHS,
  ]) {
    if (!raw) {
      continue;
    }

    try {
      const payload = JSON.parse(raw);
      const entries = Array.isArray(payload)
        ? payload
        : Object.entries(payload).map(([name, path]) => ({ name, path }));

      for (const item of entries) {
        if (!item) {
          continue;
        }

        const name = item.name || item.checkpoint || item.checkpoint_name || item.checkpointName;
        const checkpointPath = item.path || item.file || item.filePath || item.file_path;

        if (typeof name !== 'string' || typeof checkpointPath !== 'string') {
          continue;
        }
        configured.set(name.trim(), checkpointPath.trim());
      }
    } catch {
      continue;
    }
  }

  return configured;
}

const configuredCheckpointPaths = parseCheckpointMap();

function sanitizeFilename(value) {
  return value.replace(/[^a-zA-Z0-9._-]/g, '-');
}

function resolveCheckpointPath(testInfo, checkpointName) {
  const configuredPath = configuredCheckpointPaths.get(checkpointName);
  if (configuredPath) {
    return configuredPath;
  }

  for (const artifactDir of [
    process.env.OPENCODE_EVIDENCE_SCREENSHOT_CHECKPOINTS_DIR,
    process.env.OPENCODE_EVIDENCE_SCREENSHOTS_DIR,
    process.env.OPENCODE_EVIDENCE_ARTIFACTS_DIR,
    process.env.OPENCODE_ARTIFACTS_DIR,
  ]) {
    if (artifactDir) {
      return path.join(artifactDir, `${sanitizeFilename(checkpointName)}.png`);
    }
  }

  return testInfo.outputPath(`${checkpointName}.png`);
}

async function captureCheckpointScreenshot(target, testInfo, checkpointName, options = {}) {
  const screenshotPath = resolveCheckpointPath(testInfo, checkpointName);
  fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });

  await target.screenshot({ path: screenshotPath, ...options });
  await testInfo.attach(checkpointName, {
    path: screenshotPath,
    contentType: 'image/png',
  });
}

module.exports = {
  captureCheckpointScreenshot,
};
