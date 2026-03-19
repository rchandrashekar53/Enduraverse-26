import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const logDefect = mutation({
  args: {
    storageId: v.id("_storage"),
    heatSignature: v.number(),
    timeDetected: v.string(),
  },
  handler: async (ctx, args) => {
    await ctx.db.insert("defects", {
      storageId: args.storageId,
      heatSignature: args.heatSignature,
      timeDetected: args.timeDetected,
    });
  },
});

export const getAll = query({
  args: {},
  handler: async (ctx) => {
    const defects = await ctx.db.query("defects").order("desc").collect();

    return await Promise.all(
      defects.map(async (defect) => {
        const imageUrl = await ctx.storage.getUrl(defect.storageId);
        return { ...defect, imageUrl };
      }),
    );
  },
});
