/*
 * app.js — lógica do painel do Olho d'Água.
 *
 * A cada 2 s busca na API:
 *   /api/resumo   → números do topo e relógio simulado
 *   /api/predios  → mapa (Leaflet) e lista de unidades
 *   /api/alertas  → lista de alertas
 *   /api/predios/<id>/leituras e /consumo_horario → gráficos (Chart.js) da unidade selecionada
 *
 * Todos os dados são SIMULADOS.
 */

const INTERVALO_MS = 2000;
const LONDRINA = [-23.31, -51.16];

// Situação de cada unidade: cor (mapa e bolinhas), texto e classes do selo
const SITUACOES = {
  alerta:   { cor: "#dc2626", texto: "Alerta",                selo: "bg-red-100 text-red-700" },
  fora:     { cor: "#f59e0b", texto: "Em observação",         selo: "bg-amber-100 text-amber-800" },
  fechado:  { cor: "#3730a3", texto: "Água cortada",          selo: "bg-indigo-100 text-indigo-800" },
  uso:      { cor: "#0ea5e9", texto: "Em uso",                selo: "bg-sky-100 text-sky-800" },
  parado:   { cor: "#94a3b8", texto: "Sem consumo",           selo: "bg-slate-100 text-slate-600" },
  semsinal: { cor: "#cbd5e1", texto: "Sem sinal",             selo: "bg-slate-100 text-slate-500" },
  inativo:  { cor: "#e2e8f0", texto: "Desativada",            selo: "bg-slate-100 text-slate-400" },
};
const LEGENDA = ["alerta", "fora", "fechado", "uso", "parado", "inativo"];

// Tipos de prédio do cadastro (dados/predios.json)
const TIPOS = {
  escola:         { icone: "🏫", nome: "Escola municipal",          curto: "Escola" },
  cmei:           { icone: "🧸", nome: "CMEI (educação infantil)",  curto: "CMEI" },
  administrativo: { icone: "🏛️", nome: "Secretaria / administrativo", curto: "Administrativo" },
  saude:          { icone: "🏥", nome: "Unidade Básica de Saúde",   curto: "UBS" },
  esporte:        { icone: "🏀", nome: "Esporte",                   curto: "Esporte" },
  cultura:        { icone: "🎭", nome: "Cultura",                   curto: "Cultura" },
  assistencia:    { icone: "🤝", nome: "Assistência social",        curto: "Assistência" },
};
const tipo = p => TIPOS[p.tipo] || { icone: "🏢", nome: p.tipo, curto: p.tipo };

let selecionado = null;
let ultimosPredios = [];

// ------------------------------------------------------------------ utilidades
function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(n, casas = 1) {
  return Number(n).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function hora(ts) {  // '2026-11-13 01:58:00' → '13/11 01:58'
  return ts ? `${ts.slice(8, 10)}/${ts.slice(5, 7)} ${ts.slice(11, 16)}` : "";
}

async function buscar(url, opcoes) {
  const r = await fetch(url, opcoes);
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}: ${await r.text()}`);
  return r.json();
}

/** O horário da última leitura (Londrina, simulado) está dentro do horário de uso? */
function emHorario(predio) {
  if (!predio.ultima_leitura) return false;
  const [data, h] = predio.ultima_leitura.split(" ");
  const [a, m, d] = data.split("-").map(Number);
  const diaSemana = new Date(a, m - 1, d).getDay();   // 0 = domingo, 6 = sábado
  if ((diaSemana === 0 || diaSemana === 6) && predio.dias_uso !== "todos") return false;
  const minutos = s => { const [hh, mm] = s.split(":").map(Number); return hh * 60 + mm; };
  const [ini, fim] = predio.horario_uso.split("-").map(minutos);
  const agora = minutos(h);
  return agora >= ini && agora < fim;
}

/** "alerta" vem da detecção do backend; "fora" (em observação) é água correndo fora do
 *  horário que ainda não virou alerta — pode ser só um uso rápido. */
function situacao(p) {
  if (!p.ativo) return "inativo";
  if (!p.online) return "semsinal";
  if (p.alerta) return "alerta";
  if (p.registro === "fechado") return "fechado";
  if (p.vazao_lpm > 0 && !emHorario(p)) return "fora";
  return p.vazao_lpm > 0 ? "uso" : "parado";
}

function selo(sit) {
  const s = SITUACOES[sit];
  return `<span class="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full ${s.selo}">
    <span class="w-2 h-2 rounded-full" style="background:${s.cor}"></span>${s.texto}</span>`;
}

// ------------------------------------------------------------------------ mapa
const mapa = L.map("mapa", { scrollWheelZoom: false }).setView(LONDRINA, 12);
// OpenStreetMap (livre, sem chave). O CSS do index.html deixa as cores mais suaves.
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(mapa);

// O Tailwind via CDN aplica o layout depois que o mapa nasce; sem isso o Leaflet
// calcula o tamanho errado (blocos cinza e marcadores fora do lugar).
new ResizeObserver(() => mapa.invalidateSize()).observe(document.getElementById("mapa"));
window.addEventListener("load", () => mapa.invalidateSize());

document.getElementById("legenda").innerHTML = LEGENDA.map(k =>
  `<span class="inline-flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full" style="background:${SITUACOES[k].cor}"></span>${SITUACOES[k].texto}</span>`
).join("");

const marcadores = {};  // id → L.circleMarker

function atualizarMapa(predios) {
  for (const p of predios) {
    const sit = situacao(p);
    const raio = sit === "alerta" ? 14 : 7 + Math.min(9, Math.sqrt(p.vazao_lpm || 0) * 1.2);
    const popup = `<b>${esc(p.nome)}</b><br>${SITUACOES[sit].texto}` +
      (p.vazao_lpm != null ? ` · ${fmt(p.vazao_lpm, 1)} L/min` : "");
    if (!marcadores[p.id]) {
      marcadores[p.id] = L.circleMarker([p.lat, p.lon], { color: "#fff", weight: 2, fillOpacity: 0.95 })
        .addTo(mapa).bindPopup(popup)
        .on("click", () => selecionar(p.id));
    }
    marcadores[p.id].setStyle({ fillColor: SITUACOES[sit].cor }).setRadius(raio).setPopupContent(popup);
    if (sit === "alerta") marcadores[p.id].bringToFront();
  }
}

// ------------------------------------------------------------------- unidades
// Cada item é criado UMA vez e depois só tem os textos atualizados: recriar a lista
// inteira a cada 2 s faria cliques "sumirem" no meio da troca.
const itensLista = {};

function atualizarLista(predios) {
  const ul = document.getElementById("lista");
  for (const p of predios) {
    if (!itensLista[p.id]) {
      const li = document.createElement("li");
      li.className = "px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-slate-50 transition-colors";
      li.innerHTML = `
        <span data-bolinha class="w-2.5 h-2.5 rounded-full shrink-0"></span>
        <div class="min-w-0">
          <div class="text-sm font-medium truncate">${tipo(p).icone} ${esc(p.nome)}</div>
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
    item.detalhe.textContent = `${tipo(p).curto} · ${p.regiao || ""} · ${SITUACOES[sit].texto}`;
    item.vazao.textContent = p.vazao_lpm != null ? `${fmt(p.vazao_lpm, 1)} L/min` : "—";
    item.vazao.className = "ml-auto text-right tabular-nums text-sm " +
      (sit === "alerta" ? "text-red-600 font-semibold" : sit === "fora" ? "text-amber-600 font-semibold" : "text-slate-600");
  }
}

// -------------------------------------------------------------------- alertas
let assinaturaAlertas = null;  // só redesenha quando algo muda

function atualizarAlertas(alertas, registros) {
  const assinatura = alertas.map(a => a.id + a.status + (registros[a.dispositivo] || "")).join("|");
  if (assinatura === assinaturaAlertas) return;
  assinaturaAlertas = assinatura;
  const ul = document.getElementById("alertas");
  if (!alertas.length) {
    ul.innerHTML = `<li class="h-full grid place-items-center text-center py-10">
      <div><div class="text-3xl">✅</div><div class="text-sm font-medium text-emerald-700 mt-2">Nenhum vazamento</div>
      <div class="text-xs text-slate-400">Os alertas aparecem aqui automaticamente.</div></div></li>`;
    return;
  }
  ul.innerHTML = alertas.map(a => {
    const ativo = a.status === "ativo";
    const titulo = a.tipo === "vazamento" ? "Vazamento provável" : "Consumo excessivo";
    const fechado = registros[a.dispositivo] === "fechado";
    const botao = ativo && !fechado
      ? `<button data-fechar="${esc(a.dispositivo)}" class="bg-red-600 hover:bg-red-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg">🔒 Fechar registro</button>`
      : "";
    if (ativo) {
      return `<li data-predio="${esc(a.dispositivo)}" class="rounded-xl border border-red-200 bg-red-50 p-3 cursor-pointer">
        <div class="flex items-center gap-2 text-sm font-semibold text-red-700">${a.tipo === "vazamento" ? "🚨" : "⚠️"} ${titulo}</div>
        <div class="text-sm font-medium text-slate-900 mt-1">${esc(a.nome)}</div>
        <div class="text-xs text-slate-600 mt-0.5">Provável causa: ${esc(a.provavel_causa)}</div>
        <div class="text-xs text-slate-600">${fmt(a.vazao_estimada, 1)} L/min · desde ${hora(a.inicio_sim)}</div>
        <div class="mt-2 flex items-center gap-2">${botao}${fechado ? `<span class="text-xs text-indigo-700">🔒 registro fechado — aguardando o fluxo zerar</span>` : ""}</div>
      </li>`;
    }
    return `<li data-predio="${esc(a.dispositivo)}" class="rounded-xl border border-slate-200 p-3 cursor-pointer">
      <div class="flex items-center gap-2 text-sm font-medium text-emerald-700">✅ Resolvido</div>
      <div class="text-sm text-slate-800 mt-0.5">${esc(a.nome)}</div>
      <div class="text-xs text-slate-500">${titulo.toLowerCase()} · ${esc(a.provavel_causa)}</div>
      <div class="text-xs text-slate-500">${hora(a.resolvido_sim)} · perda estimada ≈ ${fmt(a.litros_perdidos, 0)} L</div>
    </li>`;
  }).join("");
}

// clique num alerta: o botão fecha o registro; o resto do cartão abre a unidade
document.getElementById("alertas").addEventListener("click", e => {
  const botao = e.target.closest("[data-fechar]");
  if (botao) { comando(botao.dataset.fechar, "fechar_registro"); return; }
  const li = e.target.closest("[data-predio]");
  if (li) selecionar(li.dataset.predio);
});

// ------------------------------------------------------------------- gráficos
Chart.defaults.font.family = "Inter, system-ui, sans-serif";
Chart.defaults.color = "#64748b";

const opcoesBase = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: { legend: { display: false } },
  scales: {
    y: { beginAtZero: true, grid: { color: "#f1f5f9" }, border: { display: false } },
    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
  },
};

const graficoVazao = new Chart(document.getElementById("grafico-vazao"), {
  type: "line",
  data: { labels: [], datasets: [{ data: [], borderColor: "#0284c7", backgroundColor: "rgba(14,165,233,.12)",
                                   fill: true, pointRadius: 0, borderWidth: 2, tension: 0.25 }] },
  options: opcoesBase,
});

const graficoHoras = new Chart(document.getElementById("grafico-horas"), {
  type: "bar",
  data: { labels: [], datasets: [{ data: [], backgroundColor: "#7dd3fc", borderRadius: 4 }] },
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

  graficoHoras.data.labels = horas.horas.map(h => h.hora.slice(11, 13) + "h");
  graficoHoras.data.datasets[0].data = horas.horas.map(h => h.litros);
  graficoHoras.update();
}

// -------------------------------------------------------------------- detalhe
function atualizarDetalhe() {
  const p = ultimosPredios.find(x => x.id === selecionado);
  if (!p) return;
  const sit = situacao(p);
  document.getElementById("titulo-predio").textContent = `${tipo(p).icone} ${p.nome}`;
  document.getElementById("sub-predio").textContent = `${tipo(p).nome} · região ${p.regiao || "—"}`;
  document.getElementById("status-predio").innerHTML = selo(sit);
  document.getElementById("info-vazao").textContent = p.vazao_lpm != null ? `${fmt(p.vazao_lpm, 1)} L/min` : "—";
  document.getElementById("info-horario").textContent =
    `${p.horario_uso.replace("-", " às ")} · ${p.dias_uso === "todos" ? "todos os dias" : "seg a sex"}`;
  document.getElementById("info-media").textContent = p.ativo ? `${fmt(p.media_diaria_litros, 0)} L` : "—";

  const acoes = document.getElementById("acoes-predio");
  const desejado = !p.ativo ? "" : p.registro === "fechado" ? "abrir" : "fechar";
  if (acoes.dataset.estado === desejado) return;  // evita recriar o botão a cada 2 s
  acoes.dataset.estado = desejado;
  acoes.innerHTML = desejado === "abrir"
    ? `<button onclick="comando(selecionado, 'abrir_registro')" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-2 rounded-lg">🔓 Reabrir registro</button>`
    : desejado === "fechar"
      ? `<button onclick="comando(selecionado, 'fechar_registro')" class="bg-white border border-red-300 text-red-700 hover:bg-red-50 text-sm font-medium px-4 py-2 rounded-lg">🔒 Fechar registro</button>`
      : "";
}

// --------------------------------------------------------------------- ações
function selecionar(id) {
  selecionado = id;
  atualizarLista(ultimosPredios);
  atualizarDetalhe();
  atualizarGraficos().catch(console.error);
}

async function comando(predioId, acao) {
  const p = ultimosPredios.find(x => x.id === predioId);
  const verbo = acao === "fechar_registro" ? "FECHAR" : "REABRIR";
  if (!p || !confirm(`${verbo} o registro de água de ${p.nome}?`)) return;
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
    const [resumo, dados, alertas] = await Promise.all([
      buscar("/api/resumo"), buscar("/api/predios"), buscar("/api/alertas?limite=20"),
    ]);
    ultimosPredios = dados.predios;
    const registros = Object.fromEntries(ultimosPredios.map(p => [p.id, p.registro]));

    // cabeçalho
    document.getElementById("relogio").textContent = resumo.relogio_simulado
      ? `🕒 ${hora(resumo.relogio_simulado)} (simulado)` : "🕒 aguardando leituras";
    const con = document.getElementById("conexao");
    con.textContent = resumo.mqtt_conectado ? "🟢 recebendo dados" : "🔴 sem conexão";
    const tg = document.getElementById("telegram");
    tg.textContent = resumo.telegram_ativo ? "📱 Telegram ligado" : "📱 Telegram desligado";
    tg.className = "ml-auto text-xs px-2 py-1 rounded-full " +
      (resumo.telegram_ativo ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500");

    // números
    document.getElementById("c-online").textContent = `${resumo.predios_online} de ${resumo.predios_ativos}`;
    document.getElementById("c-vazao").textContent = `${fmt(resumo.vazao_total_lpm, 0)} L/min`;
    document.getElementById("c-fechados").textContent = resumo.registros_fechados;
    const n = resumo.alertas_ativos;
    document.getElementById("c-alertas").textContent = n;
    document.getElementById("c-alertas").className = "text-2xl font-bold " + (n ? "text-red-600" : "text-slate-900");
    document.getElementById("c-alertas-dica").textContent = n ? "precisam de atenção" : "tudo certo";
    document.getElementById("cartao-alertas").classList.toggle("ring-2", n > 0);
    document.getElementById("cartao-alertas").classList.toggle("ring-red-300", n > 0);

    if (!selecionado) {
      const primeiro = ultimosPredios.find(p => p.ativo);
      if (primeiro) selecionado = primeiro.id;
    }
    atualizarAlertas(alertas.alertas, registros);
    atualizarMapa(ultimosPredios);
    atualizarLista(ultimosPredios);
    atualizarDetalhe();
    await atualizarGraficos();
  } catch (erro) {
    document.getElementById("conexao").textContent = "🔴 painel sem resposta do servidor";
    console.error(erro);
  }
}

ciclo();
setInterval(ciclo, INTERVALO_MS);
