"""
telegram_bot.py — alertas para a equipe de manutenção no Telegram.

  • Envia "🚨 Vazamento provável" / "⚠️ Consumo excessivo" com os botões
    [🔒 Fechar registro] [🔓 Reabrir registro].
  • Clique no botão → comando MQTT hidrometro/<id>/comando com
    autorizado_por = "telegram:<user_id>" (fica registrado no banco).
  • Envia "✅ Resolvido" quando o fluxo zera, como resposta ao alerta original.
  • /start mostra o id do chat (para configurar TELEGRAM_CHAT_ID no .env);
    /status lista os alertas ativos.

Segurança: só o chat configurado em TELEGRAM_CHAT_ID pode acionar os botões e o /status.

Sem TELEGRAM_TOKEN no .env, o sistema continua funcionando e os alertas
saem só no terminal (útil para desenvolver sem o bot).
"""

from __future__ import annotations

import asyncio
import html
from datetime import datetime
from typing import Callable

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyParameters, Update)
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes)

from . import db
from .config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

RODAPE = "\n\n<i>Dados simulados — protótipo Olho d'Água</i>"


# ------------------------------------------------------------- formatação
def _hora(ts_local: str) -> str:
    """'2026-11-13 01:58:00' → '13/11 01:58'"""
    return datetime.strptime(ts_local, "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")


def teclado(predio_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔒 Fechar registro", callback_data=f"fechar_registro:{predio_id}"),
        InlineKeyboardButton("🔓 Reabrir registro", callback_data=f"abrir_registro:{predio_id}"),
    ]])


def texto_alerta(evento: dict) -> str:
    a, p = evento["alerta"], evento["predio"]
    nome = html.escape(p["nome"])
    if evento["evento"] == "novo":
        titulo = "🚨 <b>Vazamento provável</b>" if a["tipo"] == "vazamento" else "⚠️ <b>Consumo excessivo</b>"
        v = a["vazao_estimada"]
        return (
            f"{titulo}\n🏫 <b>{nome}</b>\n\n"
            f"{html.escape(a['detalhe'])}\n"
            f"💧 Vazão do problema: <b>{v:.1f} L/min</b> (≈ {v * 60:.0f} L/h)\n"
            f"🔎 Provável causa: {html.escape(a['provavel_causa'])}\n"
            f"🕒 Início {_hora(a['inicio_sim'])} · detectado {_hora(a['detectado_sim'])} (horário simulado)"
            + RODAPE
        )
    # resolvido
    # max(0, ...): se o simulador for reiniciado, o relógio pode "voltar" no tempo
    duracao = max(0.0, (datetime.strptime(a["resolvido_sim"], "%Y-%m-%d %H:%M:%S")
                        - datetime.strptime(a["inicio_sim"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60)
    texto = (
        f"✅ <b>Resolvido</b> — {nome}\n"
        f"{html.escape(a['motivo_resolucao'])} às {_hora(a['resolvido_sim'])}.\n"
        f"⏱️ Duração ≈ {duracao:.0f} min · 💧 perda estimada ≈ {a['litros_perdidos']:.0f} L"
    )
    if evento.get("registro") == "fechado":
        texto += "\n\n⚠️ O registro está fechado: o defeito pode continuar. Acione a manutenção antes de reabrir."
    return texto + RODAPE


def _sem_tags(texto: str) -> str:
    """Versão para o terminal (sem HTML)."""
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        texto = texto.replace(tag, "")
    return html.unescape(texto)


# ------------------------------------------------------------------- bot
class NotificadorTelegram:
    def __init__(self, predios: dict[str, dict], enviar_comando: Callable[[str, str, str], dict]):
        self.predios = predios
        self.enviar_comando = enviar_comando
        self.app: Application | None = None

    @property
    def ativo(self) -> bool:
        return self.app is not None and TELEGRAM_CHAT_ID is not None

    async def iniciar(self) -> None:
        if not TELEGRAM_TOKEN:
            print("[TELEGRAM] TELEGRAM_TOKEN vazio no .env — alertas só no terminal.")
            return
        try:
            app = Application.builder().token(TELEGRAM_TOKEN).build()
            app.add_handler(CommandHandler("start", self._cmd_start))
            app.add_handler(CommandHandler("status", self._cmd_status))
            app.add_handler(CallbackQueryHandler(self._ao_clicar))
            await app.initialize()   # valida o token (getMe)
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
        except Exception as erro:
            print(f"[TELEGRAM] Não foi possível iniciar o bot: {erro!r} — alertas só no terminal.")
            return
        self.app = app
        print(f"[TELEGRAM] Bot @{app.bot.username} no ar.")
        if not TELEGRAM_CHAT_ID:
            print(f"[TELEGRAM] TELEGRAM_CHAT_ID vazio: mande /start para @{app.bot.username} "
                  "para descobrir o id do chat e coloque no .env.")

    async def parar(self) -> None:
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    # ------------------------------------------------------------- envio
    async def notificar(self, evento: dict) -> None:
        texto = texto_alerta(evento)
        print("\n[ALERTA]\n" + _sem_tags(texto) + "\n")
        if not self.ativo:
            return
        a = evento["alerta"]
        try:
            if evento["evento"] == "novo":
                msg = await self.app.bot.send_message(
                    TELEGRAM_CHAT_ID, texto, parse_mode=ParseMode.HTML,
                    reply_markup=teclado(evento["predio"]["id"]),
                )
                await asyncio.to_thread(db.salvar_telegram_msg, a["id"], msg.message_id)
            else:
                resposta = (ReplyParameters(message_id=a["telegram_msg_id"], allow_sending_without_reply=True)
                            if a.get("telegram_msg_id") else None)
                await self.app.bot.send_message(
                    TELEGRAM_CHAT_ID, texto, parse_mode=ParseMode.HTML, reply_parameters=resposta,
                )
        except Exception as erro:  # sem internet etc.: o alerta continua no banco e no painel
            print(f"[TELEGRAM] Falha ao enviar: {erro!r}")

    # ---------------------------------------------------------- handlers
    @staticmethod
    def _autorizado(update: Update) -> bool:
        chat = update.effective_chat
        return chat is not None and TELEGRAM_CHAT_ID is not None and str(chat.id) == str(TELEGRAM_CHAT_ID)

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if self._autorizado(update):
            texto = "💧 Olho d'Água: este chat recebe os alertas de vazamento dos prédios municipais."
        else:
            texto = (f"💧 Olho d'Água\nO id deste chat é <code>{chat_id}</code>.\n"
                     "Para receber alertas, coloque esse número em TELEGRAM_CHAT_ID no .env e reinicie o backend.")
        await update.message.reply_text(texto + RODAPE, parse_mode=ParseMode.HTML)

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._autorizado(update):
            await update.message.reply_text("Chat não autorizado.")
            return
        ativos = [a for a in await asyncio.to_thread(db.alertas_recentes, 50) if a["status"] == "ativo"]
        if not ativos:
            await update.message.reply_text("✅ Nenhum alerta ativo." + RODAPE, parse_mode=ParseMode.HTML)
            return
        linhas = [f"• <b>{html.escape(self.predios[a['dispositivo']]['nome'])}</b>: "
                  f"{html.escape(a['provavel_causa'])} ({a['vazao_estimada']:.1f} L/min)" for a in ativos]
        await update.message.reply_text("🚨 Alertas ativos:\n" + "\n".join(linhas) + RODAPE,
                                        parse_mode=ParseMode.HTML)

    async def _ao_clicar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        consulta = update.callback_query
        if not self._autorizado(update):
            await consulta.answer("Chat não autorizado.", show_alert=True)
            return
        try:
            acao, predio_id = consulta.data.split(":", 1)
            predio = self.predios[predio_id]
        except (ValueError, KeyError):
            await consulta.answer("Botão inválido.", show_alert=True)
            return
        usuario = consulta.from_user
        try:
            await asyncio.to_thread(self.enviar_comando, predio_id, acao, f"telegram:{usuario.id}")
        except (ConnectionError, ValueError) as erro:
            await consulta.answer(f"Não foi possível enviar: {erro}", show_alert=True)
            return
        await consulta.answer("Comando enviado ✅")
        verbo = "🔒 FECHADO" if acao == "fechar_registro" else "🔓 REABERTO"
        await consulta.message.reply_text(
            f"{verbo}: registro de <b>{html.escape(predio['nome'])}</b> por "
            f"{html.escape(usuario.full_name)}." + RODAPE,
            parse_mode=ParseMode.HTML,
        )
