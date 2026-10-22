import { DurableObject } from "cloudflare:workers";
import {
  RAM_POS,
  SPAWN_CENTER,
  DAILY_REWARDS,
  WEEKLY_TOURNAMENT_TIERS,
  generatePlantationTrees,
  terrainHeight,
} from "./worldSpec.js";

const TREES_STATIC = generatePlantationTrees();
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

function jsonResp(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...CORS_HEADERS,
    },
  });
}

function getIsoWeekInfo(nowMs = Date.now()) {
  const d = new Date(nowMs);
  const utc = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dayNum = utc.getUTCDay() || 7;
  utc.setUTCDate(utc.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((utc - yearStart) / 86400000 + 1) / 7);
  const weekId = `${utc.getUTCFullYear()}-W${String(weekNo).padStart(2, "0")}`;
  // Next Monday 00:00:00 UTC reset
  const curDay = d.getUTCDay() || 7;
  const nextMonday = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + (8 - curDay), 0, 0, 0);
  return { weekId, endsAtMs: nextMonday };
}

function utcDayKey(nowMs = Date.now()) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

function sanitizeText(raw, maxLen = 140) {
  return String(raw || "")
    .replace(/[\u0000-\u001f<>]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLen);
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const DEFAULT_AVATAR = {
  hat: "hat_caping",
  back: "back_basket",
  tool: "tool_egrek",
  outfitHex: "#27AE60",
  aura: "leaf",
  title: "Pemanen Kebun",
};

const VALID_HATS = new Set(["hat_caping", "hat_safety", "hat_headband", "hat_cowboy", "hat_crown_gold"]);
const VALID_BACKS = new Set(["back_basket", "back_pack", "back_cape", "back_wings_gold"]);
const VALID_TOOLS = new Set(["tool_egrek", "tool_dodos", "tool_egrek_dragon"]);

export class PlantationHub extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.env = env;
    this.sql = ctx.storage.sql;
    this.sessions = new Map();
    this.treeStates = TREES_STATIC.map((t, idx) => ({
      state: idx % 13 === 0 ? 2 : 1, // 2 = Sawit Emas Sultan, 1 = Matang Merah, 0 = Regrowing
      regrowAt: 0,
    }));
    this.worldEvent = {
      kind: "CERAH_PANEN",
      title: "PANEN RAYA CERAH",
      multiplier: 1.0,
      endsAt: Date.now() + 70000,
    };
    this.boars = [
      { id: "boar_1", x: -24, z: 54, yaw: 0.4, phase: 0.0, scaredUntil: 0 },
      { id: "boar_2", x: 30, z: 62, yaw: -1.2, phase: 2.1, scaredUntil: 0 },
    ];
    this.bots = [
      {
        id: "bot_mandor_ucok",
        name: "Mandor Ucok",
        isBot: true,
        x: 6.5,
        y: 0,
        z: 18.0,
        yaw: 0.5,
        anim: 1,
        inTruck: true,
        cargo: 7,
        avatar: { hat: "hat_safety", back: "back_pack", tool: "tool_egrek", outfitHex: "#E67E22", aura: "spark", title: "Mandor Blok A" },
        targetTree: 12,
        chatCooldown: 18,
      },
      {
        id: "bot_kang_asep",
        name: "Kang Asep Sawit",
        isBot: true,
        x: -16.0,
        y: 0,
        z: 28.0,
        yaw: -0.9,
        anim: 1,
        inTruck: false,
        cargo: 4,
        avatar: { hat: "hat_caping", back: "back_basket", tool: "tool_egrek", outfitHex: "#2ECC71", aura: "leaf", title: "Raja Egrek" },
        targetTree: 34,
        chatCooldown: 34,
      },
      {
        id: "bot_juragan_rini",
        name: "Juragan Rini",
        isBot: true,
        x: 18.0,
        y: 0,
        z: -4.0,
        yaw: 2.1,
        anim: 1,
        inTruck: true,
        cargo: 10,
        avatar: { hat: "hat_crown_gold", back: "back_wings_gold", tool: "tool_egrek_dragon", outfitHex: "#1E222B", aura: "gold", title: "JUARA MINGGUAN" },
        targetTree: 58,
        chatCooldown: 52,
      },
    ];
    this.tickTimer = null;
    this.initDb();
  }

  initDb() {
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS players (
        id TEXT PRIMARY KEY,
        token TEXT NOT NULL,
        name TEXT NOT NULL,
        social_provider TEXT DEFAULT 'guest',
        social_handle TEXT DEFAULT '',
        coins INTEGER DEFAULT 150000,
        gems INTEGER DEFAULT 20,
        total_kg INTEGER DEFAULT 0,
        best_haul_kg INTEGER DEFAULT 0,
        all_time_score INTEGER DEFAULT 0,
        streak_day INTEGER DEFAULT 0,
        last_claim_day TEXT DEFAULT '',
        avatar_json TEXT NOT NULL,
        unlocked_json TEXT NOT NULL,
        claimed_tiers_json TEXT DEFAULT '[]',
        updated_at INTEGER DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS weekly_scores (
        week_id TEXT NOT NULL,
        player_id TEXT NOT NULL,
        player_name TEXT NOT NULL,
        title TEXT DEFAULT '',
        outfit_hex TEXT DEFAULT '#27AE60',
        hat TEXT DEFAULT 'hat_caping',
        points INTEGER DEFAULT 0,
        kg_delivered INTEGER DEFAULT 0,
        PRIMARY KEY (week_id, player_id)
      );
      CREATE TABLE IF NOT EXISTS chat_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        sender_title TEXT DEFAULT '',
        channel TEXT DEFAULT 'global',
        message TEXT NOT NULL,
        created_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS share_cards (
        code TEXT PRIMARY KEY,
        player_name TEXT NOT NULL,
        title TEXT NOT NULL,
        total_kg INTEGER NOT NULL,
        all_time_score INTEGER NOT NULL,
        weekly_points INTEGER NOT NULL,
        rank_num INTEGER NOT NULL,
        social_handle TEXT DEFAULT '',
        hat TEXT DEFAULT 'hat_caping',
        created_at INTEGER NOT NULL
      );
    `);

    // Seed realistic starter competitive standings once so the leaderboard & tournament feel exciting immediately!
    const countRow = [...this.sql.exec(`SELECT COUNT(*) AS c FROM players`)][0];
    if (!countRow || Number(countRow.c) === 0) {
      const { weekId } = getIsoWeekInfo();
      const starters = [
        ["seed_1", "Juragan Rini", "google", "@rini.sawit", 14850000, 340, 4820, 49600, "hat_crown_gold", "#1E222B", "RAJA SAWIT NUSANTARA", 3420],
        ["seed_2", "Mandor Ucok", "tiktok", "@ucok.canter", 9620000, 190, 3390, 34800, "hat_safety", "#E67E22", "Mandor Utama", 2190],
        ["seed_3", "Kang Asep Egrek", "instagram", "@asep.kebun", 7140000, 145, 2510, 26100, "hat_caping", "#2ECC71", "Pendekar Kebun", 1640],
        ["seed_4", "Bang Dika Oleng", "x", "@dika_sawit", 5280000, 110, 1890, 19400, "hat_cowboy", "#C0392B", "Sopir Canter Pro", 1120],
        ["seed_5", "Pakde Slamet PKS", "whatsapp", "Komunitas Sawit Riau", 3890000, 80, 1340, 14100, "hat_headband", "#2980B9", "Pemanen Senior", 780],
      ];
      const now = Date.now();
      for (const [id, name, prov, handle, coins, gems, kg, score, hat, hex, title, wpts] of starters) {
        const av = JSON.stringify({ ...DEFAULT_AVATAR, hat, outfitHex: hex, title });
        const unl = JSON.stringify(["hat_caping", "back_basket", "tool_egrek", hat]);
        this.sql.exec(
          `INSERT INTO players (id, token, name, social_provider, social_handle, coins, gems, total_kg, best_haul_kg, all_time_score, streak_day, last_claim_day, avatar_json, unlocked_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 3, '2026-10-21', ?, ?, ?)`,
          id, `seed_tok_${id}`, name, prov, handle, coins, gems, kg, 360, score, av, unl, now
        );
        this.sql.exec(
          `INSERT INTO weekly_scores (week_id, player_id, player_name, title, outfit_hex, hat, points, kg_delivered)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
          weekId, id, name, title, hex, hat, wpts, kg
        );
      }
      this.sql.exec(
        `INSERT INTO chat_log (sender_id, sender_name, sender_title, channel, message, created_at) VALUES
         ('seed_2', 'Mandor Ucok', 'Mandor Utama', 'global', 'Selamat datang di Kebun Sawit Raya! Pohon Sawit Emas baru tumbuh di blok utara!', ?),
         ('seed_1', 'Juragan Rini', 'RAJA SAWIT NUSANTARA', 'global', 'Gas setor TBS ke Timbangan PKS mumpung harga sawit tinggi bre!', ?)`,
        now - 25000, now - 8000
      );
    }
  }

  ensureLoop() {
    if (this.tickTimer) return;
    this.lastTickMs = Date.now();
    this.tickTimer = setInterval(() => this.tick(), 125); // 8 Hz authoritative world broadcast, clients interpolate at 60-120 FPS!
  }

  stopLoopIfIdle() {
    if (this.sessions.size === 0 && this.tickTimer) {
      clearInterval(this.tickTimer);
      this.tickTimer = null;
    }
  }

  tick() {
    const now = Date.now();
    const dt = Math.min(0.25, Math.max(0.02, (now - this.lastTickMs) / 1000));
    this.lastTickMs = now;

    // 1. Regrow harvested oil palms & cycle world weather/price events
    const treeChanges = [];
    for (let i = 0; i < this.treeStates.length; i++) {
      const st = this.treeStates[i];
      if (st.state === 0 && now >= st.regrowAt) {
        const goldChance = this.worldEvent.kind === "DEMAM_EMAS" ? 0.34 : TREES_STATIC[i].sultanBias;
        st.state = Math.random() < goldChance ? 2 : 1;
        st.regrowAt = 0;
        treeChanges.push([i, st.state]);
      }
    }

    if (now >= this.worldEvent.endsAt) {
      const roll = Math.random();
      if (roll < 0.36) {
        this.worldEvent = { kind: "DEMAM_EMAS", title: "DEMAM SAWIT EMAS 24K (POIN 1.5X)", multiplier: 1.5, endsAt: now + 65000 };
        for (let k = 0; k < 10; k++) {
          const idx = Math.floor(Math.random() * this.treeStates.length);
          this.treeStates[idx].state = 2;
          treeChanges.push([idx, 2]);
        }
      } else if (roll < 0.68) {
        this.worldEvent = { kind: "HUJAN_BADAI", title: "HUJAN BADAI PETIR - HARGA PKS 2.0X!", multiplier: 2.0, endsAt: now + 60000 };
      } else {
        this.worldEvent = { kind: "CERAH_PANEN", title: "PANEN RAYA CERAH - HARGA NORMAL", multiplier: 1.0, endsAt: now + 70000 };
      }
      this.broadcast({ type: "event", event: this.worldEvent });
    }

    if (treeChanges.length > 0) {
      this.broadcast({ type: "trees_delta", changes: treeChanges });
    }

    // 2. Update wild Celeng boars
    for (const b of this.boars) {
      b.phase += dt * (now < b.scaredUntil ? 3.4 : 1.25);
      const rad = now < b.scaredUntil ? 22.0 : 13.0;
      const cx = b.id === "boar_1" ? -26.0 : 28.0;
      const cz = b.id === "boar_1" ? 56.0 : 60.0;
      const nx = cx + Math.cos(b.phase) * rad;
      const nz = cz + Math.sin(b.phase * 0.85) * rad;
      b.yaw = Math.atan2(nx - b.x, nz - b.z);
      b.x = +nx.toFixed(2);
      b.z = +nz.toFixed(2);
    }

    // 3. Keep estate bots active when human count < 6 so the plantation is always lively!
    const activePeers = [];
    for (const s of this.sessions.values()) {
      activePeers.push({
        id: s.playerId,
        n: s.profile.name,
        b: 0,
        x: +s.x.toFixed(2),
        y: +s.y.toFixed(2),
        z: +s.z.toFixed(2),
        yaw: +s.yaw.toFixed(3),
        a: s.anim,
        tr: s.inTruck ? 1 : 0,
        cg: s.cargo,
        av: s.profile.avatar,
      });
    }

    if (this.sessions.size < 6) {
      for (const bot of this.bots) {
        const tgt = bot.cargo >= 10 ? RAM_POS : TREES_STATIC[bot.targetTree % TREES_STATIC.length];
        const dx = tgt.x - bot.x;
        const dz = tgt.z - bot.z;
        const dist = Math.hypot(dx, dz);
        if (dist > 2.2) {
          const spd = (bot.inTruck ? 9.5 : 4.8) * dt;
          bot.yaw = Math.atan2(dx, dz);
          bot.x += (dx / dist) * spd;
          bot.z += (dz / dist) * spd;
          bot.y = terrainHeight(bot.x, bot.z);
          bot.anim = 1;
        } else {
          bot.anim = 2;
          if (bot.cargo >= 10) {
            bot.cargo = 0;
            bot.targetTree = Math.floor(Math.random() * TREES_STATIC.length);
          } else {
            bot.cargo += 2;
            bot.targetTree = (bot.targetTree + 17) % TREES_STATIC.length;
          }
        }
        activePeers.push({
          id: bot.id,
          n: bot.name,
          b: 1,
          x: +bot.x.toFixed(2),
          y: +bot.y.toFixed(2),
          z: +bot.z.toFixed(2),
          yaw: +bot.yaw.toFixed(3),
          a: bot.anim,
          tr: bot.inTruck ? 1 : 0,
          cg: bot.cargo,
          av: bot.avatar,
        });
      }
    }

    this.broadcast({
      type: "world",
      t: now,
      peers: activePeers,
      boars: this.boars.map((b) => ({ id: b.id, x: b.x, z: b.z, yaw: +b.yaw.toFixed(2) })),
    });
  }

  broadcast(payload, excludeSocket = null) {
    const raw = JSON.stringify(payload);
    for (const ws of this.sessions.keys()) {
      if (ws === excludeSocket) continue;
      try {
        ws.send(raw);
      } catch {
        this.sessions.delete(ws);
      }
    }
  }

  loadOrCreatePlayer(reqId, reqToken, reqName) {
    let row = null;
    if (reqId && reqToken) {
      row = [...this.sql.exec(`SELECT * FROM players WHERE id = ? AND token = ?`, reqId, reqToken)][0] || null;
    }
    const now = Date.now();
    if (!row) {
      const id = "p_" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
      const token = crypto.randomUUID().replace(/-/g, "");
      const cleanName = sanitizeText(reqName, 20) || "Pemanen" + Math.floor(100 + Math.random() * 899);
      const unlocked = ["hat_caping", "back_basket", "tool_egrek"];
      this.sql.exec(
        `INSERT INTO players (id, token, name, coins, gems, avatar_json, unlocked_json, updated_at)
         VALUES (?, ?, ?, 150000, 25, ?, ?, ?)`,
        id, token, cleanName, JSON.stringify(DEFAULT_AVATAR), JSON.stringify(unlocked), now
      );
      row = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, id)][0];
    } else if (reqName && sanitizeText(reqName, 20).length >= 2) {
      const cleanName = sanitizeText(reqName, 20);
      this.sql.exec(`UPDATE players SET name = ?, updated_at = ? WHERE id = ?`, cleanName, now, row.id);
      row.name = cleanName;
    }
    return this.hydrateProfile(row);
  }

  hydrateProfile(row) {
    const today = utcDayKey();
    const { weekId } = getIsoWeekInfo();
    const wRow = [...this.sql.exec(`SELECT points FROM weekly_scores WHERE week_id = ? AND player_id = ?`, weekId, row.id)][0];
    let avatar = DEFAULT_AVATAR;
    let unlocked = ["hat_caping", "back_basket", "tool_egrek"];
    let claimedTiers = [];
    try { avatar = { ...DEFAULT_AVATAR, ...JSON.parse(row.avatar_json) }; } catch {}
    try { unlocked = JSON.parse(row.unlocked_json); } catch {}
    try { claimedTiers = JSON.parse(row.claimed_tiers_json || "[]"); } catch {}

    return {
      id: row.id,
      token: row.token,
      name: row.name,
      socialProvider: row.social_provider || "guest",
      socialHandle: row.social_handle || "",
      coins: Number(row.coins) || 0,
      gems: Number(row.gems) || 0,
      totalKg: Number(row.total_kg) || 0,
      bestHaulKg: Number(row.best_haul_kg) || 0,
      allTimeScore: Number(row.all_time_score) || 0,
      weeklyPoints: wRow ? Number(wRow.points) : 0,
      streakDay: Number(row.streak_day) || 0,
      lastClaimDay: row.last_claim_day || "",
      canClaimDaily: row.last_claim_day !== today,
      avatar,
      unlocked,
      claimedTiers,
    };
  }

  getGlobalLeaderboard(limit = 20) {
    const rows = [...this.sql.exec(
      `SELECT id, name, social_provider, social_handle, coins, total_kg, all_time_score, avatar_json
       FROM players ORDER BY all_time_score DESC, total_kg DESC LIMIT ?`,
      limit
    )];
    return rows.map((r, i) => {
      let av = DEFAULT_AVATAR;
      try { av = { ...DEFAULT_AVATAR, ...JSON.parse(r.avatar_json) }; } catch {}
      return {
        rank: i + 1,
        id: r.id,
        name: r.name,
        socialProvider: r.social_provider || "guest",
        socialHandle: r.social_handle || "",
        coins: Number(r.coins),
        totalKg: Number(r.total_kg),
        score: Number(r.all_time_score),
        title: av.title,
        hat: av.hat,
        outfitHex: av.outfitHex,
      };
    });
  }

  getTournamentPayload(playerId = null) {
    const { weekId, endsAtMs } = getIsoWeekInfo();
    const rows = [...this.sql.exec(
      `SELECT player_id, player_name, title, outfit_hex, hat, points, kg_delivered
       FROM weekly_scores WHERE week_id = ? ORDER BY points DESC LIMIT 20`,
      weekId
    )];
    const standings = rows.map((r, i) => ({
      rank: i + 1,
      id: r.player_id,
      name: r.player_name,
      title: r.title,
      outfitHex: r.outfit_hex,
      hat: r.hat,
      points: Number(r.points),
      kgDelivered: Number(r.kg_delivered),
    }));
    let myRank = 0;
    if (playerId) {
      const idx = standings.findIndex((s) => s.id === playerId);
      myRank = idx >= 0 ? idx + 1 : standings.length + 1;
    }
    return {
      weekId,
      endsAtMs,
      standings,
      myRank,
      tiers: WEEKLY_TOURNAMENT_TIERS,
    };
  }

  getRecentChat() {
    const rows = [...this.sql.exec(`SELECT sender_id, sender_name, sender_title, channel, message, created_at FROM chat_log ORDER BY id DESC LIMIT 30`)];
    return rows.reverse().map((r) => ({
      senderId: r.sender_id,
      senderName: r.sender_name,
      title: r.sender_title,
      channel: r.channel,
      text: r.message,
      ts: Number(r.created_at),
    }));
  }

  handleWsMessage(ws, raw) {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }
    const sess = this.sessions.get(ws);
    if (!sess) return;
    const now = Date.now();

    switch (msg.type) {
      case "hello": {
        sess.profile = this.loadOrCreatePlayer(msg.playerId, msg.token, msg.name);
        sess.playerId = sess.profile.id;
        ws.send(JSON.stringify({
          type: "welcome",
          serverTime: now,
          profile: sess.profile,
          trees: this.treeStates.map((s) => s.state),
          event: this.worldEvent,
          dailyRewards: DAILY_REWARDS,
          globalLeaderboard: this.getGlobalLeaderboard(20),
          tournament: this.getTournamentPayload(sess.playerId),
          chatHistory: this.getRecentChat(),
        }));
        this.broadcast({
          type: "system_notice",
          text: `${sess.profile.name} bergabung ke Kebun Sawit Live!`,
        }, ws);
        break;
      }

      case "ping": {
        ws.send(JSON.stringify({ type: "pong", clientTs: msg.ts || now, serverTs: now }));
        break;
      }

      case "state": {
        if (typeof msg.x === "number" && Number.isFinite(msg.x)) sess.x = Math.max(-108, Math.min(108, msg.x));
        if (typeof msg.y === "number" && Number.isFinite(msg.y)) sess.y = Math.max(-5, Math.min(30, msg.y));
        if (typeof msg.z === "number" && Number.isFinite(msg.z)) sess.z = Math.max(-108, Math.min(108, msg.z));
        if (typeof msg.yaw === "number" && Number.isFinite(msg.yaw)) sess.yaw = msg.yaw;
        if (typeof msg.anim === "number") sess.anim = msg.anim | 0;
        if (typeof msg.inTruck === "boolean") sess.inTruck = msg.inTruck;
        break;
      }

      case "harvest": {
        const tid = msg.treeId | 0;
        if (tid < 0 || tid >= TREES_STATIC.length) break;
        if (now - sess.lastHarvestAt < 420) break;
        const tStatic = TREES_STATIC[tid];
        const tState = this.treeStates[tid];
        const dist = Math.hypot(tStatic.x - sess.x, tStatic.z - sess.z);
        if (dist > 9.5 || tState.state === 0) break;

        const maxCap = sess.inTruck ? 24 : 12;
        if (sess.cargo >= maxCap) {
          ws.send(JSON.stringify({ type: "toast", kind: "warn", text: "Muatan penuh! Segera setor TBS ke Timbangan PKS!" }));
          break;
        }

        sess.lastHarvestAt = now;
        const isGold = tState.state === 2;
        tState.state = 0;
        tState.regrowAt = now + (isGold ? 28000 : 18000);

        const bunches = isGold ? 3 : 2;
        sess.cargo = Math.min(maxCap, sess.cargo + bunches);
        if (isGold) sess.goldCargo += 1;
        sess.combo = now - sess.comboAt < 9000 ? Math.min(10, sess.combo + 1) : 1;
        sess.comboAt = now;

        this.broadcast({
          type: "harvest_fx",
          treeId: tid,
          byId: sess.playerId,
          byName: sess.profile.name,
          isGold,
          x: tStatic.x,
          z: tStatic.z,
        });
        ws.send(JSON.stringify({
          type: "cargo_sync",
          cargo: sess.cargo,
          goldCargo: sess.goldCargo,
          maxCap,
          combo: sess.combo,
          isGold,
        }));
        break;
      }

      case "sell": {
        if (sess.cargo <= 0) break;
        const distRam = Math.hypot(RAM_POS.x - sess.x, RAM_POS.z - sess.z);
        if (distRam > 16.0) {
          ws.send(JSON.stringify({ type: "toast", kind: "warn", text: "Dekati Jembatan Timbang RAM di depan Pabrik PKS!" }));
          break;
        }
        const normalBunches = Math.max(0, sess.cargo - sess.goldCargo * 3);
        const kgDelivered = normalBunches * 28 + sess.goldCargo * 95;
        const streakMult = 1.0 + Math.min(0.35, sess.profile.streakDay * 0.05);
        const comboMult = 1.0 + sess.combo * 0.04;
        const eventMult = this.worldEvent.multiplier || 1.0;

        const rupiahEarned = Math.round(kgDelivered * 3200 * eventMult * streakMult * comboMult);
        const gemsEarned = 2 + sess.goldCargo * 5 + (kgDelivered >= 300 ? 4 : 0);
        const scoreEarned = Math.round(kgDelivered * 12 * eventMult + sess.goldCargo * 280);
        const tourneyPts = Math.round(kgDelivered * 0.85 * eventMult + sess.goldCargo * 90);

        sess.cargo = 0;
        sess.goldCargo = 0;

        this.sql.exec(
          `UPDATE players
           SET coins = coins + ?,
               gems = gems + ?,
               total_kg = total_kg + ?,
               best_haul_kg = MAX(best_haul_kg, ?),
               all_time_score = all_time_score + ?,
               updated_at = ?
           WHERE id = ?`,
          rupiahEarned, gemsEarned, kgDelivered, kgDelivered, scoreEarned, now, sess.playerId
        );

        const { weekId } = getIsoWeekInfo(now);
        this.sql.exec(
          `INSERT INTO weekly_scores (week_id, player_id, player_name, title, outfit_hex, hat, points, kg_delivered)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(week_id, player_id) DO UPDATE SET
             player_name = excluded.player_name,
             title = excluded.title,
             outfit_hex = excluded.outfit_hex,
             hat = excluded.hat,
             points = weekly_scores.points + excluded.points,
             kg_delivered = weekly_scores.kg_delivered + excluded.kg_delivered`,
          weekId, sess.playerId, sess.profile.name, sess.profile.avatar.title,
          sess.profile.avatar.outfitHex, sess.profile.avatar.hat, tourneyPts, kgDelivered
        );

        const updatedRow = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, sess.playerId)][0];
        sess.profile = this.hydrateProfile(updatedRow);

        ws.send(JSON.stringify({
          type: "sell_receipt",
          kgDelivered,
          rupiahEarned,
          gemsEarned,
          scoreEarned,
          tourneyPts,
          profile: sess.profile,
          globalLeaderboard: this.getGlobalLeaderboard(20),
          tournament: this.getTournamentPayload(sess.playerId),
        }));

        if (kgDelivered >= 120) {
          this.broadcast({
            type: "system_notice",
            text: `${sess.profile.name} setor ${kgDelivered} Kg TBS (Rp ${rupiahEarned.toLocaleString("id-ID")}) di PKS!`,
          });
        }
        break;
      }

      case "horn": {
        for (const b of this.boars) {
          if (Math.hypot(b.x - sess.x, b.z - sess.z) < 22.0) {
            b.scaredUntil = now + 9000;
          }
        }
        this.broadcast({ type: "horn_fx", byId: sess.playerId, x: sess.x, z: sess.z });
        break;
      }

      case "chat": {
        if (now - sess.lastChatAt < 900) break;
        const text = sanitizeText(msg.text, 140);
        if (!text) break;
        sess.lastChatAt = now;
        const channel = msg.channel === "kebun" ? "kebun" : "global";
        this.sql.exec(
          `INSERT INTO chat_log (sender_id, sender_name, sender_title, channel, message, created_at)
           VALUES (?, ?, ?, ?, ?, ?)`,
          sess.playerId, sess.profile.name, sess.profile.avatar.title, channel, text, now
        );
        this.sql.exec(`DELETE FROM chat_log WHERE id NOT IN (SELECT id FROM chat_log ORDER BY id DESC LIMIT 60)`);
        this.broadcast({
          type: "chat",
          senderId: sess.playerId,
          senderName: sess.profile.name,
          title: sess.profile.avatar.title,
          channel,
          text,
          ts: now,
        });
        break;
      }

      case "avatar": {
        const reqAv = msg.avatar || {};
        const nextAv = { ...sess.profile.avatar };
        if (VALID_HATS.has(reqAv.hat)) nextAv.hat = reqAv.hat;
        if (VALID_BACKS.has(reqAv.back)) nextAv.back = reqAv.back;
        if (VALID_TOOLS.has(reqAv.tool)) nextAv.tool = reqAv.tool;
        if (typeof reqAv.outfitHex === "string" && /^#[0-9A-Fa-f]{6}$/.test(reqAv.outfitHex)) {
          nextAv.outfitHex = reqAv.outfitHex.toUpperCase();
        }
        if (typeof reqAv.aura === "string") nextAv.aura = sanitizeText(reqAv.aura, 16);
        if (typeof reqAv.title === "string" && sanitizeText(reqAv.title, 28)) {
          nextAv.title = sanitizeText(reqAv.title, 28);
        }
        const nextName = msg.name ? sanitizeText(msg.name, 20) || sess.profile.name : sess.profile.name;

        this.sql.exec(
          `UPDATE players SET name = ?, avatar_json = ?, updated_at = ? WHERE id = ?`,
          nextName, JSON.stringify(nextAv), now, sess.playerId
        );
        const updatedRow = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, sess.playerId)][0];
        sess.profile = this.hydrateProfile(updatedRow);
        ws.send(JSON.stringify({ type: "profile_sync", profile: sess.profile }));
        break;
      }

      case "daily_claim": {
        const today = utcDayKey(now);
        const row = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, sess.playerId)][0];
        if (!row || row.last_claim_day === today) {
          ws.send(JSON.stringify({ type: "toast", kind: "info", text: "Reward harian hari ini sudah diklaim! Kembali besok untuk streak berikutnya!" }));
          break;
        }
        const yesterday = utcDayKey(now - 86400000);
        const nextStreak = row.last_claim_day === yesterday ? ((Number(row.streak_day) % 7) + 1) : (Number(row.streak_day) >= 1 && Number(row.streak_day) < 7 ? Number(row.streak_day) + 1 : 1);
        const reward = DAILY_REWARDS[nextStreak - 1];
        let unlocked = [];
        try { unlocked = JSON.parse(row.unlocked_json || "[]"); } catch {}
        if (reward.unlock && !unlocked.includes(reward.unlock)) unlocked.push(reward.unlock);

        this.sql.exec(
          `UPDATE players SET coins = coins + ?, gems = gems + ?, streak_day = ?, last_claim_day = ?, unlocked_json = ?, updated_at = ? WHERE id = ?`,
          reward.coins, reward.gems, nextStreak, today, JSON.stringify(unlocked), now, sess.playerId
        );
        const updated = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, sess.playerId)][0];
        sess.profile = this.hydrateProfile(updated);
        ws.send(JSON.stringify({
          type: "daily_claimed",
          day: nextStreak,
          reward,
          profile: sess.profile,
        }));
        break;
      }

      case "tournament_claim": {
        const tierId = String(msg.tierId || "");
        const tier = WEEKLY_TOURNAMENT_TIERS.find((t) => t.id === tierId);
        if (!tier) break;
        const row = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, sess.playerId)][0];
        const hydrated = this.hydrateProfile(row);
        const tour = this.getTournamentPayload(sess.playerId);
        const qualifies = hydrated.weeklyPoints >= tier.minPts || (tier.id === "tier_champion" && tour.myRank > 0 && tour.myRank <= 3 && hydrated.weeklyPoints >= 300);
        if (!qualifies) {
          ws.send(JSON.stringify({ type: "toast", kind: "warn", text: `Butuh ${tier.minPts} Poin Turnamen untuk klaim ${tier.label}!` }));
          break;
        }
        if (hydrated.claimedTiers.includes(tier.id)) {
          ws.send(JSON.stringify({ type: "toast", kind: "info", text: "Hadiah turnamen ini sudah diklaim!" }));
          break;
        }
        const nextClaimed = [...hydrated.claimedTiers, tier.id];
        const nextUnlocked = [...hydrated.unlocked];
        if (tier.unlock && !nextUnlocked.includes(tier.unlock)) nextUnlocked.push(tier.unlock);
        const nextAv = { ...hydrated.avatar, title: tier.title };
        if (tier.unlock && VALID_HATS.has(tier.unlock)) nextAv.hat = tier.unlock;
        if (tier.unlock && VALID_BACKS.has(tier.unlock)) nextAv.back = tier.unlock;
        if (tier.unlock && VALID_TOOLS.has(tier.unlock)) nextAv.tool = tier.unlock;

        this.sql.exec(
          `UPDATE players SET coins = coins + ?, gems = gems + ?, avatar_json = ?, unlocked_json = ?, claimed_tiers_json = ?, updated_at = ? WHERE id = ?`,
          tier.coins, tier.gems, JSON.stringify(nextAv), JSON.stringify(nextUnlocked), JSON.stringify(nextClaimed), now, sess.playerId
        );
        const updated = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, sess.playerId)][0];
        sess.profile = this.hydrateProfile(updated);
        ws.send(JSON.stringify({
          type: "tournament_claimed",
          tier,
          profile: sess.profile,
          tournament: this.getTournamentPayload(sess.playerId),
        }));
        break;
      }

      case "auth_social": {
        this.handleSocialLink(ws, sess, msg);
        break;
      }

      case "refresh_boards": {
        ws.send(JSON.stringify({
          type: "boards",
          globalLeaderboard: this.getGlobalLeaderboard(20),
          tournament: this.getTournamentPayload(sess.playerId),
        }));
        break;
      }
    }
  }

  async handleSocialLink(ws, sess, msg) {
    let provider = sanitizeText(msg.provider || "google", 16).toLowerCase();
    let handle = sanitizeText(msg.handle || "", 40);
    let displayName = sanitizeText(msg.displayName || "", 20);

    // Real Google ID Token verification if client supplies Google Credential JWT!
    if (msg.googleIdToken && typeof msg.googleIdToken === "string") {
      try {
        const verifyResp = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(msg.googleIdToken)}`);
        if (verifyResp.ok) {
          const claims = await verifyResp.json();
          if (claims.email) {
            provider = "google";
            handle = claims.email;
            displayName = sanitizeText(claims.name || claims.given_name || claims.email.split("@")[0], 20);
          }
        }
      } catch {}
    }

    if (!handle) {
      handle = `@${(displayName || sess.profile.name).toLowerCase().replace(/\s+/g, "")}`;
    }
    const finalName = displayName || sess.profile.name;
    this.sql.exec(
      `UPDATE players SET name = ?, social_provider = ?, social_handle = ?, gems = gems + 30, updated_at = ? WHERE id = ?`,
      finalName, provider, handle, Date.now(), sess.playerId
    );
    const updated = [...this.sql.exec(`SELECT * FROM players WHERE id = ?`, sess.playerId)][0];
    sess.profile = this.hydrateProfile(updated);
    ws.send(JSON.stringify({
      type: "social_linked",
      profile: sess.profile,
      bonusGems: 30,
    }));
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS_HEADERS });

    if (request.headers.get("Upgrade")?.toLowerCase() === "websocket") {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      server.accept();

      const starterProfile = this.loadOrCreatePlayer(
        url.searchParams.get("pid"),
        url.searchParams.get("tok"),
        url.searchParams.get("name")
      );
      const sess = {
        ws: server,
        playerId: starterProfile.id,
        profile: starterProfile,
        x: SPAWN_CENTER.x + (Math.random() - 0.5) * 8.0,
        y: terrainHeight(SPAWN_CENTER.x, SPAWN_CENTER.z),
        z: SPAWN_CENTER.z + (Math.random() - 0.5) * 6.0,
        yaw: 0.0,
        anim: 0,
        inTruck: false,
        cargo: 0,
        goldCargo: 0,
        combo: 1,
        comboAt: 0,
        lastHarvestAt: 0,
        lastChatAt: 0,
      };
      this.sessions.set(server, sess);
      this.ensureLoop();

      server.addEventListener("message", (ev) => this.handleWsMessage(server, ev.data));
      const cleanup = () => {
        this.sessions.delete(server);
        this.stopLoopIfIdle();
      };
      server.addEventListener("close", cleanup);
      server.addEventListener("error", cleanup);

      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname === "/api/status") {
      return jsonResp({
        ok: true,
        game: "Nyawit Live 3D",
        onlineRealPlayers: this.sessions.size,
        onlineTotalInWorld: this.sessions.size + (this.sessions.size < 6 ? this.bots.length : 0),
        event: this.worldEvent,
        tournament: this.getTournamentPayload(),
        topPlayers: this.getGlobalLeaderboard(10),
      });
    }

    if (url.pathname === "/api/share" && request.method === "POST") {
      const body = await request.json().catch(() => ({}));
      const code = crypto.randomUUID().replace(/-/g, "").slice(0, 8);
      const lb = this.getGlobalLeaderboard(50);
      const pid = sanitizeText(body.playerId || "", 32);
      const foundIdx = lb.findIndex((x) => x.id === pid);
      const rankNum = foundIdx >= 0 ? foundIdx + 1 : Math.max(1, lb.length);

      const playerName = sanitizeText(body.playerName || "Juragan Sawit", 24);
      const title = sanitizeText(body.title || "Pemanen Kebun", 32);
      const totalKg = Math.max(0, Number(body.totalKg) || 0);
      const allTimeScore = Math.max(0, Number(body.score) || 0);
      const weeklyPoints = Math.max(0, Number(body.weeklyPoints) || 0);
      const socialHandle = sanitizeText(body.socialHandle || "", 40);
      const hat = VALID_HATS.has(body.hat) ? body.hat : "hat_caping";

      this.sql.exec(
        `INSERT INTO share_cards (code, player_name, title, total_kg, all_time_score, weekly_points, rank_num, social_handle, hat, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        code, playerName, title, totalKg, allTimeScore, weeklyPoints, rankNum, socialHandle, hat, Date.now()
      );
      const origin = this.env.PUBLIC_ORIGIN || `${url.protocol}//${url.host}`;
      return jsonResp({
        ok: true,
        code,
        shareUrl: `${origin}/s/${code}`,
        shareText: `Gue udah panen ${totalKg.toLocaleString("id-ID")} Kg TBS Sawit (Rank #${rankNum} - ${title}) di NYAWIT LIVE 3D! Ayo mabar panen & balap truk Canter live: ${origin}/s/${code}`,
      });
    }

    if (url.pathname.startsWith("/s/")) {
      const code = sanitizeText(url.pathname.slice(3), 16);
      const card = [...this.sql.exec(`SELECT * FROM share_cards WHERE code = ?`, code)][0];
      const origin = this.env.PUBLIC_ORIGIN || `${url.protocol}//${url.host}`;
      const pName = escapeHtml(card ? card.player_name : "Juragan Sawit");
      const pTitle = escapeHtml(card ? card.title : "RAJA SAWIT NUSANTARA");
      const pKg = card ? Number(card.total_kg).toLocaleString("id-ID") : "1.250";
      const pScore = card ? Number(card.all_time_score).toLocaleString("id-ID") : "18.400";
      const pRank = card ? Number(card.rank_num) : 1;
      const pHandle = escapeHtml(card?.social_handle || "@nyawit.live");

      const html = `<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${pName} — Rank #${pRank} di Nyawit Live 3D</title>
<meta property="og:title" content="${pName} (${pTitle}) — Rank #${pRank} Global Nyawit Live 3D!">
<meta property="og:description" content="Total Setoran ${pKg} Kg TBS Sawit · Skor ${pScore} · Mabar Live 3D di Android APK & Browser!">
<meta property="og:image" content="${origin}/assets/og_banner.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" sizes="32x32" href="/brand/favicon_website_32.png">
<style>
@font-face{font-family:'XyVerse Display';src:url('/brand/XyVerseDisplay-Semibold.woff2') format('woff2');font-weight:600}
body{margin:0;min-height:100vh;background:#0D0D0D;color:#fff;font-family:system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;padding:20px}
.card{max-width:540px;width:100%;background:#141917;border:1px solid #2b4c3a;border-radius:20px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.65)}
.hero{width:100%;height:240px;object-fit:cover;display:block}
.pad{padding:26px}
.eyebrow{font-family:'XyVerse Display',sans-serif;color:#5ce092;font-size:13px;letter-spacing:.12em}
h1{font-family:'XyVerse Display',sans-serif;margin:8px 0 4px;font-size:28px;text-transform:uppercase}
.sub{color:#9fb2a8;font-size:14px;margin-bottom:20px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:22px}
.stat{background:#0D0D0D;border:1px solid #24382d;border-radius:12px;padding:12px;text-align:center}
.stat b{display:block;font-size:20px;color:#ffd54f}
.stat span{font-size:11px;color:#8fa398;text-transform:uppercase}
.actions{display:grid;gap:10px}
a.btn{display:block;text-align:center;padding:14px 18px;border-radius:12px;font-weight:700;text-decoration:none;font-size:15px}
a.primary{background:#22c55e;color:#08120c}
a.apk{background:#eab308;color:#111}
.brand{display:flex;justify-content:space-between;align-items:center;margin-top:20px;padding-top:16px;border-top:1px solid #223029;color:#7d8f85;font-size:12px}
.brand img{height:24px}
</style>
</head>
<body>
  <div class="card">
    <img class="hero" src="/assets/og_banner.png" alt="Nyawit Live 3D">
    <div class="pad">
      <div class="eyebrow">PENCAPAIAN JURAGAN SAWIT LIVE</div>
      <h1>${pName}</h1>
      <div class="sub">${pTitle} · ${pHandle}</div>
      <div class="stats">
        <div class="stat"><b>#${pRank}</b><span>Global Rank</span></div>
        <div class="stat"><b>${pKg} Kg</b><span>Total Setoran TBS</span></div>
        <div class="stat"><b>${pScore}</b><span>Skor Kompetitif</span></div>
      </div>
      <div class="actions">
        <a class="btn primary" href="/">MAIN MABAR LIVE DI BROWSER 3D</a>
        <a class="btn apk" href="/download/apk">DOWNLOAD ANDROID APK (NATIVE C# ENGINE)</a>
      </div>
      <div class="brand">
        <span>Built on XyVerse Infrastructure</span>
        <img src="/brand/logo_utama_horizontal_transparan_putih.png" alt="XyVerse Tech">
      </div>
    </div>
  </div>
</body>
</html>`;
      return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }

    return new Response("Not found", { status: 404 });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS_HEADERS });

    if (url.pathname === "/download/apk") {
      return Response.redirect(`https://github.com/${env.GITHUB_REPO || "xykal/nyawit-live"}/releases/latest/download/NyawitLive-v1.0.0-universal.apk`, 302);
    }

    if (url.pathname === "/ws" || url.pathname.startsWith("/api/") || url.pathname.startsWith("/s/")) {
      const id = env.PLANTATION_HUB.idFromName("kebun-sumatera-01");
      const stub = env.PLANTATION_HUB.get(id);
      return stub.fetch(request);
    }

    return env.ASSETS.fetch(request);
  },
};
