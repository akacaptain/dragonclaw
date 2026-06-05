#!/usr/bin/env node
/**
 * Export live provider model catalog via OpenClaw picker path (runProviderCatalog).
 * Provider-agnostic; used by DragonClaw catalog_for_provider().
 */
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const DISCOVERY_ORDERS = ["simple", "profile", "paired", "late"];

function parseArgs(argv) {
  let provider = "";
  for (let i = 2; i < argv.length; i += 1) {
    if (argv[i] === "--provider" && argv[i + 1]) {
      provider = argv[i + 1].trim().toLowerCase();
      i += 1;
    }
  }
  if (!provider) {
    throw new Error("usage: oc_picker_catalog.mjs --provider <id>");
  }
  return { provider };
}

function listDistFiles(distDir, prefix) {
  return readdirSync(distDir)
    .filter((name) => name.startsWith(prefix) && name.endsWith(".js"))
    .sort();
}

async function importDist(distDir, prefix, { exportName = "", aliases = [] } = {}) {
  const matches = listDistFiles(distDir, prefix);
  if (matches.length === 0) {
    throw new Error(`OpenClaw dist module not found: ${prefix}* in ${distDir}`);
  }
  if (exportName || aliases.length > 0) {
    for (const name of matches) {
      const mod = await import(pathToFileURL(join(distDir, name)).href);
      if (exportName && typeof mod[exportName] === "function") {
        return mod;
      }
      if (aliases.some((alias) => typeof mod[alias] === "function")) {
        return mod;
      }
    }
    throw new Error(
      `${exportName || aliases.join("|")} export not found in ${prefix}* modules`,
    );
  }
  return import(pathToFileURL(join(distDir, matches[0])).href);
}

function pickExport(mod, name, aliases = []) {
  if (typeof mod[name] === "function") {
    return mod[name];
  }
  for (const alias of aliases) {
    if (typeof mod[alias] === "function") {
      return mod[alias];
    }
  }
  throw new Error(`${name} export not found`);
}

async function loadOpenClawConfig(distDir, env) {
  let fallback = null;
  for (const name of readdirSync(distDir).sort()) {
    if (!name.startsWith("io-") || !name.endsWith(".js")) continue;
    const mod = await import(pathToFileURL(join(distDir, name)).href);
    if (typeof mod.loadConfig === "function") {
      return mod.loadConfig({ env });
    }
    if (typeof mod.a === "function" && fallback === null) {
      fallback = mod.a;
    }
  }
  if (typeof fallback === "function") {
    return fallback({ env });
  }
  throw new Error("loadConfig export not found in OpenClaw dist");
}

function providerMatchesFilter(provider, providerFilter) {
  const ids = [
    provider.id,
    ...(provider.aliases ?? []),
    ...(provider.hookAliases ?? []),
  ].map((id) => id?.trim().toLowerCase()).filter(Boolean);
  return ids.includes(providerFilter);
}

function hasLiveProviderCatalog(provider) {
  return (
    typeof provider.catalog?.run === "function" ||
    typeof provider.discovery?.run === "function"
  );
}

function providerAuthIds(provider) {
  return [
    provider.id,
    ...(provider.aliases ?? []),
    ...(provider.hookAliases ?? []),
  ]
    .map((id) => id?.trim().toLowerCase())
    .filter(Boolean);
}

function resolveProviderEnvApiKey(provider, runtimeEnv) {
  for (const envVar of provider.envVars ?? []) {
    const normalized = envVar.trim();
    const value = runtimeEnv[normalized]?.trim();
    if (normalized && value) {
      return { apiKey: value, discoveryApiKey: value };
    }
  }
  return undefined;
}

function modelFromProviderCatalog(provider, providerConfig, model) {
  const id = String(model.id ?? "").trim();
  return {
    id,
    name: String(model.name || id).trim(),
    provider,
    key: `${provider}/${id}`,
  };
}

async function loadLivePickerCatalog({ cfg, env, provider, workspaceDir, agentDir, modules }) {
  const {
    normalizeProviderId,
    resolveProviderCatalogPluginIdsForFilter,
    groupPluginDiscoveryProvidersByOrder,
    resolveRuntimePluginDiscoveryProviders,
    runProviderCatalog,
    normalizePluginDiscoveryResult,
    loadAuthProfileStoreWithoutExternalProfiles,
    createProviderApiKeyResolver,
    createProviderAuthResolver,
  } = modules;

  const providerFilter = normalizeProviderId(provider);
  if (!providerFilter) return [];

  const onlyPluginIds = await resolveProviderCatalogPluginIdsForFilter({
    cfg,
    env,
    providerFilter,
  });
  if (!onlyPluginIds || onlyPluginIds.length === 0) return [];

  let providers = (
    await resolveRuntimePluginDiscoveryProviders({
      config: cfg,
      env,
      onlyPluginIds,
      includeUntrustedWorkspacePlugins: false,
      ...(workspaceDir ? { workspaceDir } : {}),
    })
  )
    .filter((entry) => providerMatchesFilter(entry, providerFilter))
    .filter(hasLiveProviderCatalog);

  if (providers.length === 0) {
    const runtimeMod = await import(
      pathToFileURL(join(process.env.OPENCLAW_DIST, "providers.runtime.js")).href
    );
    const resolvePluginProviders = runtimeMod.resolvePluginProviders;
    providers = resolvePluginProviders({
      config: cfg,
      env,
      onlyPluginIds,
      includeUntrustedWorkspacePlugins: false,
      mode: "setup",
      activate: false,
      cache: false,
      ...(workspaceDir ? { workspaceDir } : {}),
    }).filter(
      (entry) =>
        providerMatchesFilter(entry, providerFilter) && hasLiveProviderCatalog(entry),
    );
  }

  let authStore;
  const getAuthStore = () =>
    authStore ??
    loadAuthProfileStoreWithoutExternalProfiles(agentDir, {
      allowKeychainPrompt: false,
    });
  const resolveProviderApiKey = createProviderApiKeyResolver(env, getAuthStore, cfg);
  const resolveProviderAuth = createProviderAuthResolver(env, getAuthStore, cfg);
  const resolveFastProviderApiKey = (entry, providerId = entry.id) => {
    const normalizedProviderId = normalizeProviderId(providerId);
    if (providerAuthIds(entry).includes(normalizedProviderId)) {
      const fromEnv = resolveProviderEnvApiKey(entry, env);
      if (fromEnv) return fromEnv;
    }
    return resolveProviderApiKey(providerId);
  };

  const byOrder = groupPluginDiscoveryProvidersByOrder(providers);
  const rows = [];
  const seen = new Set();

  for (const order of DISCOVERY_ORDERS) {
    for (const entry of byOrder[order] ?? []) {
      let result;
      try {
        result = await runProviderCatalog({
          provider: entry,
          config: cfg,
          env,
          agentDir,
          resolveProviderApiKey: (providerId) =>
            resolveFastProviderApiKey(entry, providerId?.trim() || entry.id),
          resolveProviderAuth: (providerId, options) =>
            resolveProviderAuth(providerId?.trim() || entry.id, options),
          ...(workspaceDir ? { workspaceDir } : {}),
        });
      } catch {
        continue;
      }
      const normalized = normalizePluginDiscoveryResult({ provider: entry, result });
      for (const [providerIdRaw, providerConfig] of Object.entries(normalized)) {
        const providerId = normalizeProviderId(providerIdRaw);
        if (providerId !== providerFilter || !Array.isArray(providerConfig.models)) continue;
        for (const model of providerConfig.models) {
          const row = modelFromProviderCatalog(providerId, providerConfig, model);
          if (seen.has(row.key)) continue;
          seen.add(row.key);
          rows.push(row);
        }
      }
    }
  }

  return rows.sort((left, right) => {
    const byName = left.name.localeCompare(right.name);
    if (byName !== 0) return byName;
    return left.key.localeCompare(right.key);
  });
}

async function main() {
  const { provider } = parseArgs(process.argv);
  const distDir = process.env.OPENCLAW_DIST;
  if (!distDir) {
    throw new Error("OPENCLAW_DIST is required");
  }

  const providerIdMod = await importDist(distDir, "provider-id-", {
    exportName: "normalizeProviderId",
    aliases: ["i"],
  });
  const listProviderCatalog = await importDist(distDir, "list.provider-catalog-", {
    exportName: "resolveProviderCatalogPluginIdsForFilter",
    aliases: ["r"],
  });
  const providerDiscovery = await importDist(distDir, "provider-discovery-", {
    exportName: "runProviderCatalog",
    aliases: ["i"],
  });
  const secrets = await importDist(distDir, "models-config.providers.secrets-", {
    exportName: "createProviderApiKeyResolver",
    aliases: ["t"],
  });
  const store = await importDist(distDir, "store-", {
    exportName: "ensureAuthProfileStoreWithoutExternalProfiles",
  });
  const agentScopeConfig = await importDist(distDir, "agent-scope-config-", {
    exportName: "resolveDefaultAgentDir",
    aliases: ["s"],
  });

  const env = { ...process.env };
  const cfg = await loadOpenClawConfig(distDir, env);
  const resolveDefaultAgentDir = pickExport(agentScopeConfig, "resolveDefaultAgentDir", ["s"]);
  const agentDir = resolveDefaultAgentDir(cfg, env);
  const workspaceDir = process.env.OPENCLAW_WORKSPACE_DIR || undefined;

  const modules = {
    normalizeProviderId: pickExport(providerIdMod, "normalizeProviderId", ["i"]),
    resolveProviderCatalogPluginIdsForFilter: pickExport(
      listProviderCatalog,
      "resolveProviderCatalogPluginIdsForFilter",
      ["r"],
    ),
    groupPluginDiscoveryProvidersByOrder: pickExport(
      providerDiscovery,
      "groupPluginDiscoveryProvidersByOrder",
      ["t"],
    ),
    resolveRuntimePluginDiscoveryProviders: pickExport(
      providerDiscovery,
      "resolveRuntimePluginDiscoveryProviders",
      ["r"],
    ),
    runProviderCatalog: pickExport(providerDiscovery, "runProviderCatalog", ["i"]),
    normalizePluginDiscoveryResult: pickExport(
      providerDiscovery,
      "normalizePluginDiscoveryResult",
      ["n"],
    ),
    loadAuthProfileStoreWithoutExternalProfiles: pickExport(
      store,
      "ensureAuthProfileStoreWithoutExternalProfiles",
    ),
    createProviderApiKeyResolver: pickExport(secrets, "createProviderApiKeyResolver", ["t"]),
    createProviderAuthResolver: pickExport(secrets, "createProviderAuthResolver", ["n"]),
  };

  const models = await loadLivePickerCatalog({
    cfg,
    env,
    provider,
    workspaceDir,
    agentDir,
    modules,
  });

  process.stdout.write(
    JSON.stringify({
      ok: true,
      source: "picker_catalog",
      provider,
      count: models.length,
      models,
    }),
  );
}

main().catch((err) => {
  const message = err instanceof Error ? err.message : String(err);
  process.stderr.write(`${message}\n`);
  process.stdout.write(JSON.stringify({ ok: false, error: message, models: [] }));
  process.exit(1);
});
