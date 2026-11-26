// Génère registry/mechanics.json depuis le code officiel épinglé (zod schemas + enums).
import * as S from "@openfront/engine-api/Schemas";
import * as G from "@openfront/engine-api/game/GameTypes";
import fs from "fs";

const intents: Record<string, unknown> = {};
for (const [name, v] of Object.entries(S)) {
  if (!name.endsWith("IntentSchema") || name === "IntentSchema" || name === "StampedIntentSchema") continue;
  const shape = (v as any)?.shape ?? (v as any)?._zod?.def?.shape;
  if (!shape) { intents[name] = { error: "shape introuvable" }; continue; }
  const fields: Record<string, string> = {};
  for (const [k, f] of Object.entries<any>(shape)) {
    fields[k] = f?._zod?.def?.type ?? f?.def?.type ?? typeof f;
    if (k === "type") fields[k] = "literal:" + (f?._zod?.def?.values?.[0] ?? f?.value);
  }
  intents[name] = fields;
}
const enums: Record<string, string[]> = {};
for (const [name, v] of Object.entries(G)) {
  if (v && typeof v === "object" && !Array.isArray(v) && Object.values(v as object).every((x) => typeof x === "string" || typeof x === "number") && Object.keys(v as object).length) {
    enums[name] = Object.keys(v as object).filter((k) => isNaN(Number(k)));
  }
}
const out = { engine_commit: process.env.ENGINE_COMMIT ?? "unknown", intents, enums };
fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 2));
console.log("intents:", Object.keys(intents).length, "enums:", Object.keys(enums).length);
