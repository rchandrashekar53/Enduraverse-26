import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  telemetry: defineTable({
    temp: v.number(),
    status: v.string(),
    timestamp: v.number(),
    minTemp: v.optional(v.number()),
    maxTemp: v.optional(v.number()),
    avgTemp: v.optional(v.number()),
    ambientTemp: v.optional(v.number()),
    grid: v.optional(v.array(v.array(v.number()))),
  }),

  defects: defineTable({
    storageId: v.id("_storage"),
    heatSignature: v.number(),
    timeDetected: v.string(),
  }),
});
