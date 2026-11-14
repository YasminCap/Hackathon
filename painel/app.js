/*
 * app.js — lógica do painel do LeakFinder Londrina.
 *
 * A cada 2 s busca na API:
 *   /api/resumo, /api/predios, /api/alertas, /api/economia → números, demonstrativo, mapa, listas
 *   /api/predios/<id>/semanal, /leituras, /consumo_horario   → gráficos da unidade selecionada
 *   /api/alertas?finalizados=true                             → aba Finalizados (quando aberta)
 * Cadastro: POST /api/predios. Campo de operação: POST /api/alertas/<id>/operacao.
 *
 * Todos os dados são SIMULADOS.
 */

const INTERVALO_MS = 2000;
const LONDRINA = [-23.31, -51.16];

// Situação de cada unidade: cor (mapa e bolinhas), texto e classes do selo
const SITUACOES = {
  alerta:     { cor: "#dc2626", texto: "Alerta",            selo: "bg-red-100 text-red-700" },
  fora:       { cor: "#f59e0b", texto: "Em observação",     selo: "bg-amber-100 text-amber-800" },
  uso:        { cor: "#0ea5e9", texto: "Em uso",            selo: "bg-sky-100 text-sky-800" },
  parado:     { cor: "#94a3b8", texto: "Sem consumo",       selo: "bg-slate-100 text-slate-600" },
  aguardando: { cor: "#8b5cf6", texto: "Aguardando câmera", selo: "bg-violet-100 text-violet-800" },
  semsinal:   { cor: "#cbd5e1", texto: "Sem sinal",         selo: "bg-slate-100 text-slate-500" },
  inativo:    { cor: "#e2e8f0", texto: "Desativada",        selo: "bg-slate-100 text-slate-400" },
};
const LEGENDA = ["alerta", "fora", "uso", "parado", "aguardando", "inativo"];

// Campo de operação de cada alerta (preenchido pelo gestor)
const OPERACOES = {
  pendente:   { texto: "Pendente",               classe: "bg-amber-100 text-amber-800" },
  informado:  { texto: "Informado à manutenção", classe: "bg-sky-100 text-sky-800" },
  consertado: { texto: "Consertado",             classe: "bg-emerald-100 text-emerald-800" },
};

// Tipos de unidade do cadastro (dados/predios.json)
const TIPOS = {
  escola:         { icone: "🏫", nome: "Escola municipal",            curto: "Escola" },
  cmei:           { icone: "🧸", nome: "CMEI (educação infantil)",    curto: "CMEI" },
  administrativo: { icone: "🏛️", nome: "Secretaria / administrativo", curto: "Administrativo" },
  saude:          { icone: "🏥", nome: "Unidade Básica de Saúde",     curto: "UBS" },
  esporte:        { icone: "🏀", nome: "Esporte",                     curto: "Esporte" },
  cultura:        { icone: "🎭", nome: "Cultura",                     curto: "Cultura" },
  assistencia:    { icone: "🤝", nome: "Assistência social",          curto: "Assistência" },
};
const LITROS_POR_ALUNO = { escola: 10, cmei: 25 };
const tipo = p => TIPOS[p.tipo] || { icone: "🏢", nome: p.tipo, curto: p.tipo };

let selecionado = null;
let ultimosPredios = [];
let abaAtual = "geral";

// ------------------------------------------------------------------ utilidades
function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(n, casas = 1) {
  return Number(n).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function reais(n) {
  return Number(n).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function litrosLegivel(l) {  // 1.234 L / 12,3 mil L / 1,2 milhão de L
  if (l >= 1e6) return `${fmt(l / 1e6, 1)} milhão de L`;
  if (l >= 1e4) return `${fmt(l / 1e3, 1)} mil L`;
  return `${fmt(l, 0)} L`;
}

function hora(ts) {  // '2026-11-13 01:58:00' → '13/11 01:58'
  return ts ? `${ts.slice(8, 10)}/${ts.slice(5, 7)} ${ts.slice(11, 16)}` : "";
}

function avisar(texto) {
  const el = document.getElementById("aviso");
  el.textContent = texto;
  el.classList.remove("hidden");
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => el.classList.add("hidden"), 3500);
}

async function buscar(url, opcoes) {
  const r = await fetch(url, opcoes);
  if (!r.ok) {
    let msg = await r.text();
    try { msg = JSON.parse(msg).detail || msg; } catch { /* texto puro */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
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
  if (p.camera_instalada === false) return "aguardando";
  if (!p.online) return "semsinal";
  if (p.alerta) return "alerta";
  if (p.vazao_lpm > 0 && !emHorario(p)) return "fora";
  return p.vazao_lpm > 0 ? "uso" : "parado";
}

function selo(sit) {
  const s = SITUACOES[sit];
  return `<span class="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full ${s.selo}">
    <span class="w-2 h-2 rounded-full" style="background:${s.cor}"></span>${s.texto}</span>`;
}

// ------------------------------------------------------------------------ abas
document.querySelectorAll("[data-aba]").forEach(botao =>
  botao.addEventListener("click", () => mostrarAba(botao.dataset.aba)));

function mostrarAba(nome) {
  abaAtual = nome;
  for (const a of ["geral", "cadastro", "finalizados"]) {
    document.getElementById(`aba-${a}`).classList.toggle("hidden", a !== nome);
  }
  document.querySelectorAll("[data-aba]").forEach(b => b.classList.toggle("ativa", b.dataset.aba === nome));
  if (nome === "geral") setTimeout(() => mapa.invalidateSize(), 50);
  if (nome === "cadastro") iniciarMapaCadastro();
  if (nome === "finalizados") atualizarFinalizados().catch(console.error);
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

// --------------------------------------------------------- campo de operação
function campoOperacao(a) {
  const opcoes = Object.entries(OPERACOES).map(([valor, o]) =>
    `<option value="${valor}" ${a.operacao === valor ? "selected" : ""}>${o.texto}</option>`).join("");
  return `<label class="flex items-center gap-2 text-xs text-slate-600">Operação:
    <select data-operacao="${a.id}" class="text-xs font-medium rounded-lg border-0 px-2 py-1 ${OPERACOES[a.operacao]?.classe || ""}">${opcoes}</select>
  </label>`;
}

async function salvarOperacao(sel) {
  try {
    await buscar(`/api/alertas/${sel.dataset.operacao}/operacao`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operacao: sel.value }),
    });
    if (sel.value === "consertado") avisar("Alerta finalizado — ele foi para a aba Finalizados.");
    await ciclo();
    if (abaAtual === "finalizados") await atualizarFinalizados();
  } catch (erro) {
    alert("Não foi possível salvar a operação:\n" + erro.message);
  }
}

// ------------------------------------------------------- alertas em andamento
let assinaturaAlertas = null;  // só redesenha quando algo muda

function atualizarAlertas(alertas) {
  const assinatura = alertas.map(a => a.id + a.status + a.operacao).join("|");
  if (assinatura === assinaturaAlertas) return;
  assinaturaAlertas = assinatura;
  const ul = document.getElementById("alertas");
  if (!alertas.length) {
    ul.innerHTML = `<li class="h-full grid place-items-center text-center py-10">
      <div><div class="text-3xl">✅</div><div class="text-sm font-medium text-emerald-700 mt-2">Nenhum vazamento em andamento</div>
      <div class="text-xs text-slate-400">Os alertas aparecem aqui automaticamente.</div></div></li>`;
    return;
  }
  ul.innerHTML = alertas.map(a => {
    const ativo = a.status === "ativo";
    const titulo = a.tipo === "vazamento" ? "Vazamento provável" : "Consumo excessivo";
    if (ativo) {
      return `<li data-predio="${esc(a.dispositivo)}" class="rounded-xl border border-red-200 bg-red-50 p-3 cursor-pointer">
        <div class="flex items-center gap-2 text-sm font-semibold text-red-700">${a.tipo === "vazamento" ? "🚨" : "⚠️"} ${titulo}</div>
        <div class="text-sm font-medium text-slate-900 mt-1">${esc(a.nome)}</div>
        <div class="text-xs text-slate-600 mt-0.5">Provável causa: ${esc(a.provavel_causa)}</div>
        <div class="text-xs text-slate-600">${fmt(a.vazao_estimada, 1)} L/min · desde ${hora(a.inicio_sim)}</div>
        <div class="mt-2">${campoOperacao(a)}</div>
      </li>`;
    }
    return `<li data-predio="${esc(a.dispositivo)}" class="rounded-xl border border-slate-200 p-3 cursor-pointer">
      <div class="flex items-center gap-2 text-sm font-medium text-emerald-700">✅ Vazamento parou</div>
      <div class="text-sm text-slate-800 mt-0.5">${esc(a.nome)}</div>
      <div class="text-xs text-slate-500">${titulo.toLowerCase()} · ${esc(a.provavel_causa)}</div>
      <div class="text-xs text-slate-500">${hora(a.resolvido_sim)} · perda ≈ ${fmt(a.litros_perdidos, 0)} L</div>
      <div class="mt-2">${campoOperacao(a)}</div>
    </li>`;
  }).join("");
}

// clique num alerta abre a unidade (menos no campo de operação)
document.getElementById("alertas").addEventListener("click", e => {
  if (e.target.closest("label")) return;
  const li = e.target.closest("[data-predio]");
  if (li) selecionar(li.dataset.predio);
});
document.getElementById("alertas").addEventListener("change", e => {
  const sel = e.target.closest("[data-operacao]");
  if (sel) salvarOperacao(sel);
});

// ---------------------------------------------------------------- finalizados
async function atualizarFinalizados() {
  const dados = await buscar("/api/alertas?finalizados=true&limite=200");
  const corpo = document.getElementById("tabela-finalizados");
  if (!dados.alertas.length) {
    corpo.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-slate-400">Nenhum alerta finalizado ainda.</td></tr>`;
    return;
  }
  corpo.innerHTML = dados.alertas.map(a => {
    const e = a.economia;
    return `<tr>
      <td class="px-4 py-2"><div class="font-medium">${esc(a.nome)}</div></td>
      <td class="px-4 py-2"><div>${a.tipo === "vazamento" ? "Vazamento" : "Consumo excessivo"}</div>
        <div class="text-xs text-slate-500">${esc(a.provavel_causa)}</div></td>
      <td class="px-4 py-2 text-xs whitespace-nowrap">${hora(a.inicio_sim)} → ${a.resolvido_sim ? hora(a.resolvido_sim) : "<i>vazamento ainda não parou</i>"}</td>
      <td class="px-4 py-2 text-right tabular-nums">${a.litros_perdidos != null ? `${fmt(a.litros_perdidos, 0)} L` : "—"}</td>
      <td class="px-4 py-2 text-right tabular-nums text-sky-800">${e ? litrosLegivel(e.litros_nao_desperdicados) : "—"}</td>
      <td class="px-4 py-2 text-right tabular-nums text-emerald-700 font-medium">${e ? reais(e.valor_rs) : "—"}</td>
      <td class="px-4 py-2">${campoOperacao(a)}</td>
    </tr>`;
  }).join("");
}

document.getElementById("tabela-finalizados").addEventListener("change", e => {
  const sel = e.target.closest("[data-operacao]");
  if (sel) salvarOperacao(sel);
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
                                   fill: true, pointRadius: 2, borderWidth: 2,
                                   // cada foto mostra a média da meia hora ANTERIOR a ela: degrau "before"
                                   stepped: "before" }] },
  options: opcoesBase,
});

const graficoHoras = new Chart(document.getElementById("grafico-horas"), {
  type: "bar",
  data: { labels: [], datasets: [{ data: [], backgroundColor: "#7dd3fc", borderRadius: 4 }] },
  options: opcoesBase,
});

const graficoSemanal = new Chart(document.getElementById("grafico-semanal"), {
  type: "bar",
  data: { labels: [], datasets: [
    { type: "bar", label: "Consumo da semana", data: [], backgroundColor: [], borderRadius: 4 },
    { type: "line", label: "Média semanal", data: [], borderColor: "#0f172a", borderDash: [6, 4],
      borderWidth: 1.5, pointRadius: 0 },
  ] },
  options: { ...opcoesBase, plugins: { legend: { display: true, labels: { boxWidth: 12 } } } },
});

const graficoEconomia = new Chart(document.getElementById("grafico-economia"), {
  type: "bar",
  data: { labels: [], datasets: [{ data: [], backgroundColor: "#34d399", borderRadius: 4 }] },
  options: opcoesBase,
});

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

async function atualizarGraficos() {
  if (!selecionado) return;
  const [serie, horas, semanal] = await Promise.all([
    buscar(`/api/predios/${selecionado}/leituras?limite=48`),  // 48 fotos = 24 h
    buscar(`/api/predios/${selecionado}/consumo_horario?horas=24`),
    buscar(`/api/predios/${selecionado}/semanal?semanas=8`),
  ]);
  graficoVazao.data.labels = serie.leituras.map(l => l.ts_local.slice(11, 16));
  graficoVazao.data.datasets[0].data = serie.leituras.map(l => l.vazao_lpm);
  graficoVazao.update();

  graficoHoras.data.labels = horas.horas.map(h => h.hora.slice(11, 13) + "h");
  graficoHoras.data.datasets[0].data = horas.horas.map(h => h.litros);
  graficoHoras.update();

  // histórico semanal: barra mais clara = semana incompleta (fora da média)
  const s = semanal.semanas;
  graficoSemanal.data.labels = s.map(x => `${x.inicio.slice(8, 10)}/${x.inicio.slice(5, 7)}`);
  graficoSemanal.data.datasets[0].data = s.map(x => x.litros);
  graficoSemanal.data.datasets[0].backgroundColor = s.map(x => x.completa ? "#0ea5e9" : "#bae6fd");
  graficoSemanal.data.datasets[1].data = s.map(() => semanal.media_semanal);
  graficoSemanal.update();

  document.getElementById("info-semanal").textContent =
    semanal.media_semanal != null ? `${fmt(semanal.media_semanal, 0)} L` : "—";
  const v = semanal.variacao_pct, el = document.getElementById("semanal-variacao");
  if (v == null) {
    el.textContent = semanal.semana_atual ? "· semana atual ainda em andamento" : "";
    el.className = "text-xs text-slate-400";
  } else {
    el.textContent = `· semana atual ${fmt(Math.abs(v), 0)}% ${v >= 0 ? "acima" : "abaixo"} da média`;
    el.className = "text-xs font-medium " + (v > 20 ? "text-red-600" : v < 0 ? "text-emerald-700" : "text-slate-600");
  }
}

// -------------------------------------------------------------------- detalhe
function atualizarDetalhe() {
  const p = ultimosPredios.find(x => x.id === selecionado);
  if (!p) return;
  const sit = situacao(p);
  document.getElementById("titulo-predio").textContent = `${tipo(p).icone} ${p.nome}`;
  document.getElementById("sub-predio").textContent = `${tipo(p).nome} · região ${p.regiao || "—"}` +
    (p.ultima_leitura ? ` · última foto do hidrômetro às ${p.ultima_leitura.slice(11, 16)}` : "") +
    (p.camera_instalada === false ? " · câmera ainda não instalada" : "");
  document.getElementById("status-predio").innerHTML = selo(sit);
  document.getElementById("info-vazao").textContent = p.vazao_lpm != null ? `${fmt(p.vazao_lpm, 1)} L/min` : "—";
  document.getElementById("info-horario").textContent =
    `${p.horario_uso.replace("-", " às ")} · ${p.dias_uso === "todos" ? "todos os dias" : "seg a sex"}`;
  // média = alunos × litros por aluno (base: estudos que mediram escolas públicas; ver CLAUDE.md)
  document.getElementById("info-media").textContent = !p.ativo ? "—"
    : p.alunos ? `${fmt(p.media_diaria_litros, 0)} L · ${p.alunos} ${p.tipo === "cmei" ? "crianças" : "alunos"} × ${p.litros_por_aluno} L`
    : `${fmt(p.media_diaria_litros, 0)} L`;
}

function selecionar(id) {
  selecionado = id;
  if (abaAtual !== "geral") mostrarAba("geral");
  atualizarLista(ultimosPredios);
  atualizarDetalhe();
  atualizarGraficos().catch(console.error);
}

// ------------------------------------------------------- demonstrativo (R$)
function atualizarEconomia(e) {
  document.getElementById("e-litros").textContent = litrosLegivel(e.litros_nao_desperdicados);
  document.getElementById("e-valor").textContent = reais(e.valor_rs);
  document.getElementById("e-ocorrencias").textContent =
    e.ocorrencias ? `${fmt(e.m3_nao_desperdicados, 1)} m³ · ${e.ocorrencias} vazamento(s) interrompido(s)` : "nenhum vazamento interrompido ainda";
  document.getElementById("e-hipotese").textContent = `Como calculamos: ${e.hipotese} Valores simulados.`;
  graficoEconomia.data.labels = e.por_mes.map(m => `${MESES[Number(m.mes.slice(5, 7)) - 1]}/${m.mes.slice(2, 4)}`);
  graficoEconomia.data.datasets[0].data = e.por_mes.map(m => m.valor_rs);
  graficoEconomia.update();
}

// --------------------------------------------------------- cadastrar unidade
let mapaCadastro = null, marcadorCadastro = null, localCadastro = null;

function iniciarMapaCadastro() {
  if (mapaCadastro) { setTimeout(() => mapaCadastro.invalidateSize(), 50); return; }
  mapaCadastro = L.map("mapa-cadastro").setView(LONDRINA, 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" })
    .addTo(mapaCadastro);
  mapaCadastro.on("click", e => {
    localCadastro = e.latlng;
    if (!marcadorCadastro) marcadorCadastro = L.marker(e.latlng).addTo(mapaCadastro);
    marcadorCadastro.setLatLng(e.latlng);
    document.getElementById("cad-local").textContent =
      `Local marcado: ${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;
  });
  setTimeout(() => mapaCadastro.invalidateSize(), 50);
}

const form = document.getElementById("form-cadastro");

function atualizarPreviaMedia() {
  const t = form.tipo.value, alunos = Number(form.alunos.value) || 0, l = LITROS_POR_ALUNO[t];
  document.getElementById("cad-media").innerHTML =
    `Média diária calculada: <b>${fmt(alunos * l, 0)} L</b> (${alunos} ${t === "cmei" ? "crianças" : "alunos"} × ${l} L)`;
}
form.addEventListener("input", atualizarPreviaMedia);
atualizarPreviaMedia();

form.addEventListener("submit", async e => {
  e.preventDefault();
  const erro = document.getElementById("cad-erro");
  erro.textContent = "";
  if (!form.nome.value.trim()) { erro.textContent = "Informe o nome da unidade."; return; }
  if (!localCadastro) { erro.textContent = "Clique no mapa para marcar o local da unidade."; return; }
  if (!form.abre.value || !form.fecha.value || form.abre.value >= form.fecha.value) {
    erro.textContent = "O horário de abertura precisa ser antes do de fechamento."; return;
  }
  try {
    const unidade = await buscar("/api/predios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nome: form.nome.value.trim(), tipo: form.tipo.value, regiao: form.regiao.value,
        lat: localCadastro.lat, lon: localCadastro.lng,
        horario_uso: `${form.abre.value}-${form.fecha.value}`, dias_uso: form.dias_uso.value,
        alunos: Number(form.alunos.value),
      }),
    });
    avisar(`${unidade.nome} cadastrada — aguardando a instalação da câmera.`);
    form.reset(); atualizarPreviaMedia();
    localCadastro = null;
    if (marcadorCadastro) { marcadorCadastro.remove(); marcadorCadastro = null; }
    document.getElementById("cad-local").textContent = "Nenhum local marcado.";
    await ciclo();
    selecionar(unidade.id);
  } catch (err) {
    erro.textContent = err.message;
  }
});

// ------------------------------------------------------------- ciclo principal
async function ciclo() {
  try {
    const [resumo, dados, alertas, economia] = await Promise.all([
      buscar("/api/resumo"), buscar("/api/predios"), buscar("/api/alertas?limite=30"), buscar("/api/economia"),
    ]);
    ultimosPredios = dados.predios;

    // cabeçalho
    document.getElementById("relogio").textContent = resumo.relogio_simulado
      ? `🕒 ${hora(resumo.relogio_simulado)} (simulado)` : "🕒 aguardando leituras";
    document.getElementById("conexao").textContent = resumo.mqtt_conectado ? "🟢 recebendo dados" : "🔴 sem conexão";
    document.getElementById("n-finalizados").textContent = resumo.finalizados;

    // números
    document.getElementById("c-online").textContent = `${resumo.predios_online} de ${resumo.predios_com_camera}`;
    const semCamera = resumo.predios_ativos - resumo.predios_com_camera;
    document.getElementById("c-online-dica").textContent =
      semCamera ? `enviando leituras · ${semCamera} aguardando câmera` : "enviando leituras";
    const n = resumo.alertas_ativos;
    document.getElementById("c-alertas").textContent = n;
    document.getElementById("c-alertas").className = "text-2xl font-bold " + (n ? "text-red-600" : "text-slate-900");
    document.getElementById("c-alertas-dica").textContent = n ? "precisam de atenção" : "tudo certo";
    document.getElementById("cartao-alertas").classList.toggle("ring-2", n > 0);
    document.getElementById("cartao-alertas").classList.toggle("ring-red-300", n > 0);
    const aguardando = resumo.aguardando_acao;
    document.getElementById("c-aguardando").textContent = aguardando;
    document.getElementById("c-aguardando").className = "text-2xl font-bold " + (aguardando ? "text-amber-600" : "text-slate-900");
    document.getElementById("c-consertados").textContent =
      (aguardando ? "manutenção ainda não informada" : "nada pendente") + ` · ${resumo.consertados} consertado(s)`;

    atualizarEconomia(economia);

    if (!selecionado) {
      const primeiro = ultimosPredios.find(p => p.ativo && p.camera_instalada !== false);
      if (primeiro) selecionado = primeiro.id;
    }
    atualizarAlertas(alertas.alertas);
    atualizarMapa(ultimosPredios);
    atualizarLista(ultimosPredios);
    atualizarDetalhe();
    if (abaAtual === "geral") await atualizarGraficos();
  } catch (erro) {
    document.getElementById("conexao").textContent = "🔴 painel sem resposta do servidor";
    console.error(erro);
  }
}

ciclo();
setInterval(ciclo, INTERVALO_MS);
