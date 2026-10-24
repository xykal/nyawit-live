// Official Server Telemetry Monitor for Nyawit Live 3D Dedicated Multiplayer, Chat & Voice API
const elOnline = document.getElementById("mOnline");
const elPing = document.getElementById("mPing");
const elEvent = document.getElementById("mEvent");
const elWeek = document.getElementById("mWeek");
const elRooms = document.getElementById("roomsList");
const elRanks = document.getElementById("rankList");
const elChats = document.getElementById("chatList");

function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function pollServer() {
  const t0 = performance.now();
  try {
    const [stRes, rmRes] = await Promise.all([fetch("/api/status"), fetch("/api/rooms")]);
    const st = await stRes.json();
    const rm = await rmRes.json();
    const rtt = Math.round(performance.now() - t0);

    elOnline.textContent = `${st.onlineTotalInWorld || 0} AKTIF`;
    elPing.textContent = `ONLINE (${rtt} ms)`;
    elEvent.textContent = st.event?.title || "PANEN RAYA CERAH";
    elWeek.textContent = st.tournament?.weekId || "--";

    elRooms.innerHTML = (rm.rooms || [])
      .map(
        (r) => `<div class="row">
          <div><strong>${esc(r.name)}</strong><br><span style="color:#8E9AA6;font-size:11px">${esc(r.id)} | ${esc(r.region)}</span></div>
          <code>${r.onlineTotalInWorld}/${r.maxPlayers}</code>
        </div>`
      )
      .join("");

    const topRows = (st.topPlayers || []).slice(0, 8);
    elRanks.innerHTML = topRows.length > 0
      ? topRows
          .map(
            (p) => `<div class="row">
              <div><strong>#${p.rank} ${esc(p.name)}</strong><br><span style="color:#8E9AA6;font-size:11px">${esc(p.title)}</span></div>
              <code style="color:#F59E0B">${Number(p.totalKg || 0).toLocaleString("id-ID")} Kg</code>
            </div>`
          )
          .join("")
      : `<div class="row"><span style="color:#8E9AA6;font-size:12px">MENUNGGU SETORAN PEMAIN ASLI PERTAMA</span><code>0 Kg</code></div>`;

    const chatRows = (st.recentChat || []).slice(-10).reverse();
    elChats.innerHTML = chatRows.length > 0
      ? chatRows
          .map(
            (c) => `<div class="chat-item"><b>[${esc(c.channel.toUpperCase())}] ${esc(c.senderName)}:</b> ${esc(c.text)}</div>`
          )
          .join("")
      : `<div class="chat-item"><span style="color:#8E9AA6">Server 100% Real-Player Only — belum ada percakapan pemain aktif.</span></div>`;
  } catch {
    elPing.textContent = "RECONNECTING";
  }
}

pollServer();
setInterval(pollServer, 5000);
