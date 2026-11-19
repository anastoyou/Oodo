import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import react from "@vitejs/plugin-react";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..");
const ADDONS_DIR = path.join(ROOT, "addons");
const GENERATED_DIR = path.join(__dirname, ".generated");

function parseArgs(argv) {
  let target = null;
  let watch = false;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--target" && argv[i + 1]) {
      target = argv[i + 1];
      i += 1;
    } else if (argv[i] === "--watch") {
      watch = true;
    }
  }
  return { target, watch };
}

function resolveFirstExisting(dir, names) {
  for (const name of names) {
    const candidate = path.join(dir, name);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function discoverReactPdps(targetFilter = null) {
  const entries = [];
  if (!fs.existsSync(ADDONS_DIR)) return entries;

  for (const addonName of fs.readdirSync(ADDONS_DIR)) {
    if (!addonName.startsWith("custom_store")) continue;
    const customPdpRoot = path.join(ADDONS_DIR, addonName, "custom_pdp");
    if (!fs.existsSync(customPdpRoot) || !fs.statSync(customPdpRoot).isDirectory()) continue;

    for (const folderName of fs.readdirSync(customPdpRoot)) {
      const reactDir = path.join(customPdpRoot, folderName, "react");
      const entryComponent = resolveFirstExisting(reactDir, [
        "PdpPage.tsx",
        "PdpPage.jsx",
      ]);
      if (!entryComponent) continue;

      const key = `${addonName}/${folderName}`;
      if (targetFilter && targetFilter !== key && targetFilter !== folderName) {
        continue;
      }

      const fullDataComponent = resolveFirstExisting(reactDir, [
        "pdppage_full_data.tsx",
        "PdpPageFullData.tsx",
      ]);

      entries.push({
        key,
        addonName,
        folderName,
        entryComponent,
        fullDataComponent,
        customCss: fs.existsSync(path.join(reactDir, "pdp.css"))
          ? path.join(reactDir, "pdp.css")
          : null,
        outDir: path.join(ADDONS_DIR, addonName, "static", "dist", `pdp_${folderName}`),
      });
    }
  }
  return entries;
}

function writeWrapperEntry(pdp, componentPath, suffix) {
  fs.mkdirSync(GENERATED_DIR, { recursive: true });
  const safeName = `${pdp.addonName}__${pdp.folderName}__${suffix}`.replace(/[^A-Za-z0-9_.-]/g, "_");
  const entryFile = path.join(GENERATED_DIR, `${safeName}.tsx`);
  const mountImport = path.resolve(__dirname, "src", "mountPdp.tsx").replace(/\\/g, "/");
  const compImport = componentPath.replace(/\\/g, "/");
  const cssLine = pdp.customCss
    ? `import "${pdp.customCss.replace(/\\/g, "/")}";\n`
    : "";

  const content = `${cssLine}import { mountPdp } from "${mountImport}";\nimport Component from "${compImport}";\n\nmountPdp(Component);\n`;
  fs.writeFileSync(entryFile, content, "utf-8");
  return entryFile;
}

async function runViteBundle({ entryFile, outDir, jsName, cssName, emptyOutDir, watch }) {
  await build({
    configFile: false,
    root: __dirname,
    css: {
      postcss: __dirname,
    },
    plugins: [react()],
    resolve: {
      alias: {
        "@odoo-pdp": path.resolve(__dirname, "src"),
      },
    },
    define: {
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
    build: {
      outDir,
      emptyOutDir,
      watch: watch ? {} : null,
      cssCodeSplit: false,
      lib: false,
      rollupOptions: {
        input: entryFile,
        output: {
          format: "es",
          inlineDynamicImports: true,
          entryFileNames: jsName,
          assetFileNames: (assetInfo) => {
            if (assetInfo.name && assetInfo.name.endsWith(".css")) {
              return cssName;
            }
            return "assets/[name]-[hash][extname]";
          },
        },
      },
    },
  });
}

async function buildSinglePdp(pdp, watch = false) {
  console.log(`[build_pdp] Building ${pdp.key} -> ${path.relative(ROOT, pdp.outDir)}`);

  const mainEntry = writeWrapperEntry(pdp, pdp.entryComponent, "main");
  await runViteBundle({
    entryFile: mainEntry,
    outDir: pdp.outDir,
    jsName: "pdp.js",
    cssName: "pdp.css",
    emptyOutDir: true,
    watch,
  });

  if (pdp.fullDataComponent) {
    const fullEntry = writeWrapperEntry(pdp, pdp.fullDataComponent, "full");
    await runViteBundle({
      entryFile: fullEntry,
      outDir: pdp.outDir,
      jsName: "pdp_full_data.js",
      cssName: "pdp_full_data.css",
      emptyOutDir: false,
      watch,
    });
  }
}

async function main() {
  const { target, watch } = parseArgs(process.argv.slice(2));
  const pdps = discoverReactPdps(target);
  if (!pdps.length) {
    if (target) {
      console.error(`[build_pdp] No React PDP found matching target: ${target}`);
      process.exit(1);
    }
    console.log("[build_pdp] No React PDPs found under addons/custom_store*/custom_pdp/*/react/PdpPage.tsx");
    return;
  }

  if (watch && pdps.length > 1) {
    console.log("[build_pdp] Watching multiple PDPs in parallel...");
    await Promise.all(pdps.map((pdp) => buildSinglePdp(pdp, true)));
    return;
  }

  for (const pdp of pdps) {
    await buildSinglePdp(pdp, watch);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
