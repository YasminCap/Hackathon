/*
 * app.js — lógica do painel do Olho d'Água.
 *
 * A cada 2 s busca na API:
 *   /api/resumo   → cartões e relógio simulado
 *   /api/predios  → mapa (Leaflet) e lista lateral
 *   /api/predios/<id>/leituras e /consumo_horario → gráficos (Chart.js) do prédio selecionado
 *
 * Todos os dados são SIMULADOS.
 */

const INTERVALO_MS = 2000;
const LONDRINA = [-23.31, -51.16];

// Cores por situação (iguais à legenda do mapa)
const SITUACOES = {
  uso:      { cor: "#10b981", texto: "em uso" },
  parado:   { cor: "#7dd3fc", texto: "parado" },
  fora:     { cor: "#f97316", texto: "fluxo fora do horário" },
  fechado:  { cor: "#1e40af", texto: "registro fechado" },
  semsinal: { cor: "#94a3b8", texto: "sem sinal" },
  inativo:  { cor: "#94a3b8", texto: "desativado" },
};

let selecionado = null;         // id do prédio aberto nos gráficos
const marcadores = {};          // id → L.circleMarker
let ultimosPredios = [];

// ------------------------------------------------------------------ utilidades
function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(n, casas = 1) {
  return Number(n).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

async function buscar(url, opcoes) {
  const r = await fetch(url, opcoes);
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}: ${await r.text()}`);
  return r.json();
}

/** O horário da última leitura (Londrina, simulado) está dentro do horário de uso? */
function emHorario(predio) {
  if (!predio.ultima_leitura) return false;
  const [data, hora] = predio.ultima_leitura.split(" ");
  const [a, m, d] = data.split("-").map(Number);
  const diaSemana = new Date(a, m - 1, d).getDay();   // 0 = domingo, 6 = sábado
  if (diaSemana === 0 || diaSemana === 6) return false;
  const minutos = s => { const [h, mi] = s.split(":").map(Number); return h * 60 + mi; };
  const [ini, fim] = predio.horario_uso.split("-").map(minutos);
  const agora = minutos(hora);
  return agora >= ini && agora < fim;
}

/** Situação visual do prédio. "Fora do horário" é só um destaque — a detecção vem no passo 5. */
function situacao(p) {
  if (!p.ativo) return "inativo";
  if (!p.online) return "semsinal";
  if (p.registro === "fechado") return "fechado";
  if (p.vazao_lpm > 0 && !emHorario(p)) return "fora";
  return p.vazao_lpm > 0 ? "uso" : "parado";
}

// ------------------------------------------------------------------------ mapa
const mapa = L.map("mapa").setView(LONDRINA, 12);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; OpenStreetMap",
}).addTo(mapa);

// O Tailwind via CDN aplica o layout depois que o mapa nasce; sem isso o Leaflet
// calcula o tamanho errado (blocos cinza e marcadores fora do lugar).
new ResizeObserver(() => mapa.invalidateSize()).observe(document.getElementById("mapa"));
window.addEventListener("load", () => mapa.invalidateSize());

function atualizarMapa(predios) {
  for (const p of predios) {
    const s = SITUACOES[situacao(p)];
    const raio = 8 + Math.min(14, Math.sqrt(p.vazao_lpm || 0) * 1.6); // maior = mais vazão
    const popup = `<b>${esc(p.nome)}</b><br>${esc(s.texto)}<br>` +
      (p.vazao_lpm != null ? `${fmt(p.vazao_lpm, 2)} L/min` : "—");
    if (!marcadores[p.id]) {
      marcadores[p.id] = L.circleMarker([p.lat, p.lon], { weight: 2, color: "#0f172a", fillOpacity: 0.9 })
        .addTo(mapa)
        .on("click", () => selecionar(p.id));
      marcadores[p.id].bindPopup(popup);
    }
    marcadores[p.id].setStyle({ fillColor: s.cor }).setRadius(raio).setPopupContent(popup);
  }
}

// ---------------------------------------------------------------------- lista
// Cada item é criado UMA vez e depois só tem os textos atualizados: recriar a lista
// inteira a cada 2 s faria cliques "sumirem" no meio da troca.
const itensLista = {};  // id → { li, bolinha, detalhe, vazao }

function atualizarLista(predios) {
  const ul = document.getElementById("lista");
  for (const p of predios) {
    if (!itensLista[p.id]) {
      const li = document.createElement("li");
      li.className = "px-3 py-2 flex items-center gap-3 cursor-pointer hover:bg-slate-50";
      li.innerHTML = `
        <span class="w-3 h-3 rounded-full shrink-0" data-bolinha></span>
        <div class="min-w-0">
          <div class="font-medium truncate">${esc(p.nome)}</div>
          <div class="text-xs text-slate-500" data-detalhe></div>
        </div>
        <div class="ml-auto text-right tabular-nums text-sm" data-vazao></div>`;
      li.addEventListener("click", () => selecionar(p.id));
      ul.appendChild(li);
      itensLista[p.id] = {
        li,
        bolinha: li.querySelector("[data-bolinha]"),
        detalhe: li.querySelector("[data-detalhe]"),
        vazao: li.querySelector("[data-vazao]"),
      };
    }
    const item = itensLista[p.id];
    const sit = situacao(p);
    item.li.classList.toggle("bg-sky-50", p.id === selecionado);
    item.bolinha.style.background = SITUACOES[sit].cor;
    item.detalhe.textContent = `${p.tipo.toUpperCase()} · ${p.regiao || ""} · ${SITUACOES[sit].texto}`;
    item.vazao.textContent = p.vazao_lpm != null ? `${fmt(p.vazao_lpm, 2)} L/min` : "—";
    item.vazao.classList.toggle("text-orange-600", sit === "fora");
    item.vazao.classList.toggle("font-semibold", sit === "fora");
  }
}

// ------------------------------------------------------------------- gráficos
const opcoesBase = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: { legend: { display: false } },
  scales: { y: { beginAtZero: true } },
};

const graficoVazao = new Chart(document.getElementById("grafico-vazao"), {
  type: "line",
  data: { labels: [], datasets: [{ data: [], borderColor: "#0284c7", backgroundColor: "rgba(2,132,199,.15)",
                                   fill: true, pointRadius: 0, borderWidth: 2, tension: 0.2 }] },
  options: { ...opcoesBase, scales: { ...opcoesBase.scales, x: { ticks: { maxTicksLimit: 8 } } } },
});

const graficoHoras = new Chart(document.getElementById("grafico-horas"), {
  type: "bar",
  data: { labels: [], datasets: [{ data: [], backgroundColor: "#38bdf8" }] },
  options: opcoesBase,
});

async function atualizarGraficos() {
  if (!selecionado) return;
  const [serie, horas] = await Promise.all([
    buscar(`/api/predios/${selecionado}/leituras?limite=180`),
    buscar(`/api/predios/${selecionado}/consumo_horario?horas=24`),
  ]);
  graficoVazao.data.labels = serie.leituras.map(l => l.ts_local.slice(11, 16));
  graficoVazao.data.datasets[0].data = serie.leituras.map(l => l.vazao_lpm);
  graficoVazao.update();

  graficoHoras.data.labels = horas.horas.map(h => h.hora.slice(8, 10) + "/" + h.hora.slice(11, 13) + "h");
  graficoHoras.data.datasets[0].data = horas.horas.map(h => h.litros);
  graficoHoras.update();
}

function atualizarCabecalhoPredio() {
  const p = ultimosPredios.find(x => x.id === selecionado);
  if (!p) return;
  const s = SITUACOES[situacao(p)];
  document.getElementById("titulo-predio").textContent = p.nome;
  document.getElementById("status-predio").innerHTML =
    `<span class="px-2 py-0.5 rounded text-white" style="background:${s.cor}">${esc(s.texto)}</span>
     <span class="text-slate-500 ml-2">uso: ${esc(p.horario_uso)} (dias úteis) · média ${fmt(p.media_diaria_litros, 0)} L/dia</span>`;

  // Botão de registro (manual pelo painel; no passo 5 o mesmo comando sai do Telegram)
  const acoes = document.getElementById("acoes-predio");
  if (!p.ativo) { acoes.innerHTML = ""; return; }
  acoes.innerHTML = p.registro === "fechado"
    ? `<button onclick="comando('abrir_registro')" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm px-3 py-1.5 rounded">Reabrir registro</button>`
    : `<button onclick="comando('fechar_registro')" class="bg-red-600 hover:bg-red-700 text-white text-sm px-3 py-1.5 rounded">Fechar registro</button>`;
}

// --------------------------------------------------------------------- ações
function selecionar(id) {
  selecionado = id;
  atualizarLista(ultimosPredios);
  atualizarCabecalhoPredio();
  atualizarGraficos().catch(console.error);
}

async function comando(acao) {
  const p = ultimosPredios.find(x => x.id === selecionado);
  const verbo = acao === "fechar_registro" ? "FECHAR" : "REABRIR";
  if (!p || !confirm(`${verbo} o registro de ${p.nome}?`)) return;
  try {
    await buscar(`/api/predios/${p.id}/comando`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acao, autorizado_por: "painel" }),
    });
    await ciclo();
  } catch (erro) {
    alert("Não foi possível enviar o comando:\n" + erro.message);
  }
}

// ------------------------------------------------------------- ciclo principal
async function ciclo() {
  try {
    const [resumo, dados] = await Promise.all([buscar("/api/resumo"), buscar("/api/predios")]);
    ultimosPredios = dados.predios;

    document.getElementById("relogio").textContent = resumo.relogio_simulado
      ? "🕒 " + resumo.relogio_simulado.slice(8, 10) + "/" + resumo.relogio_simulado.slice(5, 7) +
        " " + resumo.relogio_simulado.slice(11, 16) + " (simulado)"
      : "🕒 aguardando leituras";
    document.getElementById("conexao").textContent = resumo.mqtt_conectado ? "🟢 MQTT conectado" : "🔴 MQTT desconectado";
    document.getElementById("c-online").textContent = `${resumo.predios_online} / ${resumo.predios_ativos}`;
    document.getElementById("c-vazao").textContent = `${fmt(resumo.vazao_total_lpm)} L/min`;
    const fora = ultimosPredios.filter(p => situacao(p) === "fora").length;
    const cFora = document.getElementById("c-fora");
    cFora.textContent = fora;
    cFora.className = "text-2xl font-bold " + (fora ? "text-orange-600" : "");
    document.getElementById("c-fechados").textContent = resumo.registros_fechados;

    if (!selecionado) {
      const primeiro = ultimosPredios.find(p => p.ativo);
      if (primeiro) selecionado = primeiro.id;
    }
    atualizarMapa(ultimosPredios);
    atualizarLista(ultimosPredios);
    atualizarCabecalhoPredio();
    await atualizarGraficos();
  } catch (erro) {
    document.getElementById("conexao").textContent = "🔴 API fora do ar";
    console.error(erro);
  }
}

ciclo();
setInterval(ciclo, INTERVALO_MS);
