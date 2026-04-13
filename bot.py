import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from supabase import create_client, Client
import mercadopago

# ==================== CONFIGURAÇÕES ====================
TOKEN = "8713124469:AAGCO1MichVkgpIsc__vURreS8e8oX5Qfbo"
ADMIN_ID = 8309449775
GRUPO_LINK = "https://t.me/+laIYEeIQuuc1ZWEx"
SUPORTE_USER = "@Tropadomaisnovo33"

# Supabase
SUPABASE_URL = "https://cebywxcpmkrqwbbhddra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNlYnl3eGNwbWtycXdiYmhkZHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMjYyMTQsImV4cCI6MjA5MTYwMjIxNH0.4hj5uTjLyz5GqvNztMf_XyIpPdzq1obcybGelLEVN74"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = "APP_USR-8313019935361645-040523-f5273bbb40e6f8b1cfa385cbb7716aa5-800117337"
sdk = mercadopago.SDK(MERCADO_PAGO_ACCESS_TOKEN)

# Estados para conversas
AGUARDANDO_PIX_VALOR = 1
AGUARDANDO_SUPORTE = 2
AGUARDANDO_GIFT = 3
AGUARDANDO_NOVA_BIN = 4
AGUARDANDO_VALOR_GIFT = 5

# ==================== FUNÇÕES SUPABASE ====================
def get_user(user_id: str) -> dict:
    """Busca ou cria usuário no Supabase"""
    result = supabase.table("usuarios").select("*").eq("user_id", str(user_id)).execute()
    
    if not result.data:
        novo_user = {
            "user_id": str(user_id),
            "saldo": 0.0,
            "compras": 0,
            "gasto": 0.0,
            "data_registro": datetime.now().strftime("%d/%m/%Y")
        }
        supabase.table("usuarios").insert(novo_user).execute()
        return novo_user
    
    return result.data[0]

def atualizar_saldo(user_id: str, valor: float, is_adicao: bool = True):
    """Atualiza saldo do usuário"""
    user = get_user(user_id)
    novo_saldo = user["saldo"] + valor if is_adicao else user["saldo"] - valor
    novo_compras = user["compras"] + (1 if not is_adicao else 0)
    novo_gasto = user["gasto"] + (valor if not is_adicao else 0)
    
    supabase.table("usuarios").update({
        "saldo": novo_saldo,
        "compras": novo_compras,
        "gasto": novo_gasto
    }).eq("user_id", str(user_id)).execute()

def get_bins() -> list:
    """Retorna todas as BINs"""
    result = supabase.table("bins").select("*").execute()
    return result.data

def get_bin(bin_id: str) -> dict:
    """Retorna uma BIN específica"""
    result = supabase.table("bins").select("*").eq("bin_id", bin_id).execute()
    return result.data[0] if result.data else None

def add_bin(bin_id: str, quantidade: int, preco: float):
    """Adiciona nova BIN"""
    supabase.table("bins").insert({
        "bin_id": bin_id,
        "nome": bin_id,
        "quantidade": quantidade,
        "preco": preco
    }).execute()

def update_bin_quantidade(bin_id: str, quantidade: int):
    """Atualiza quantidade de uma BIN"""
    supabase.table("bins").update({"quantidade": quantidade}).eq("bin_id", bin_id).execute()

def add_gift(codigo: str, valor: float):
    """Adiciona um novo gift"""
    supabase.table("gifts").insert({
        "codigo": codigo.upper(),
        "valor": valor
    }).execute()

def resgatar_gift_db(codigo: str, user_id: str) -> float:
    """Resgata um gift e retorna o valor"""
    result = supabase.table("gifts").select("*").eq("codigo", codigo.upper()).execute()
    if result.data:
        valor = result.data[0]["valor"]
        supabase.table("gifts").update({
            "resgatado_por": str(user_id),
            "resgatado_em": datetime.now().strftime("%d/%m/%Y %H:%M")
        }).eq("codigo", codigo.upper()).execute()
        return valor
    return 0

def salvar_pedido_pix(pedido_id: str, user_id: str, valor: float, qr_code: str = "", qr_base64: str = ""):
    """Salva pedido PIX"""
    supabase.table("pedidos_pix").insert({
        "pedido_id": str(pedido_id),
        "user_id": str(user_id),
        "valor": valor,
        "status": "PENDENTE",
        "qr_code": qr_code,
        "qr_code_base64": qr_base64
    }).execute()

def get_pedido_pix(pedido_id: str) -> dict:
    """Busca pedido PIX"""
    result = supabase.table("pedidos_pix").select("*").eq("pedido_id", str(pedido_id)).execute()
    return result.data[0] if result.data else None

def update_pedido_status(pedido_id: str, status: str):
    """Atualiza status do pedido"""
    supabase.table("pedidos_pix").update({"status": status}).eq("pedido_id", str(pedido_id)).execute()

def get_estatisticas() -> dict:
    """Retorna estatísticas do sistema"""
    result = supabase.table("vw_estatisticas").select("*").execute()
    if result.data:
        return result.data[0]
    return {
        "total_usuarios": 0,
        "saldo_total": 0,
        "total_compras": 0,
        "faturamento": 0,
        "total_estoque": 0
    }

# ==================== TECLADOS ====================
def gerar_teclado_menu(user_id: int):
    keyboard = [
        [InlineKeyboardButton("🛒 Produtos", callback_data="produtos")],
        [InlineKeyboardButton("🏷️ Comprar Por Bin", callback_data="comprar_bin")],
        [InlineKeyboardButton("📞 Suporte", callback_data="suporte")],
        [InlineKeyboardButton("💰 Adicionar Saldo", callback_data="adicionar_saldo")],
        [InlineKeyboardButton("👤 Perfil", callback_data="perfil")],
        [InlineKeyboardButton("🎁 Resgatar Gifts", callback_data="resgatar_gift")]
    ]
    if str(user_id) == str(ADMIN_ID):
        keyboard.append([InlineKeyboardButton("👑 Painel Admin", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

# ==================== HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(str(user_id))
    
    caption = (
        f"👋 Olá, {update.effective_user.first_name}!\n\n"
        f"🆔 ID: {user_id}\n"
        f"💰 Saldo: R$ {user['saldo']:.2f}\n"
        f"📢 Grupo: [Clique aqui]({GRUPO_LINK})\n\n"
        f"Use o menu abaixo 👇"
    )
    
    try:
        with open("12694.jpg", 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=gerar_teclado_menu(user_id),
                parse_mode=ParseMode.MARKDOWN
            )
    except:
        await update.message.reply_text(
            caption,
            reply_markup=gerar_teclado_menu(user_id),
            parse_mode=ParseMode.MARKDOWN
        )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(str(user_id))
    
    caption = (
        f"👋 Olá, {query.from_user.first_name}!\n\n"
        f"🆔 ID: {user_id}\n"
        f"💰 Saldo: R$ {user['saldo']:.2f}\n"
        f"📢 Grupo: [Clique aqui]({GRUPO_LINK})\n\n"
        f"Use o menu abaixo 👇"
    )
    
    try:
        with open("12694.jpg", 'rb') as photo:
            await query.edit_message_media(
                media=InputMediaPhoto(media=photo, caption=caption, parse_mode=ParseMode.MARKDOWN),
                reply_markup=gerar_teclado_menu(user_id)
            )
    except:
        await query.edit_message_caption(
            caption=caption,
            reply_markup=gerar_teclado_menu(user_id),
            parse_mode=ParseMode.MARKDOWN
        )

async def produtos_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💳 Comprar GG's", callback_data="comprar_ggs")],
        [InlineKeyboardButton("🔑 Comprar Logins", callback_data="comprar_logins")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="menu")]
    ]
    await query.edit_message_caption(
        caption="🛒 *PRODUTOS*\n\nEscolha uma opção:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def comprar_ggs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bins = get_bins()
    keyboard = []
    for bin in bins:
        keyboard.append([InlineKeyboardButton(f"{bin['bin_id']} | ({bin['quantidade']})", callback_data=f"bin_{bin['bin_id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="produtos")])
    
    await query.edit_message_caption(
        caption="🏪 *ESCOLHA SUA BIN*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def mostrar_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bin_id = query.data.replace("bin_", "")
    bin_info = get_bin(bin_id)
    
    if not bin_info:
        await query.edit_message_caption("❌ BIN não encontrada!")
        return
    
    caption = (
        f"-----&&----\n\n"
        f"💳 BIN: {bin_id}xxxxxx\n"
        f"🏳️ Bandeira: {bin_info.get('bandeira', 'VISA')}\n"
        f"🏦 Banco: {bin_info.get('banco', 'BANCO BRADESCO, S.A.')}\n"
        f"💳 Tipo: {bin_info.get('tipo', 'CREDIT')}\n"
        f"🎖️ Categoria: {bin_info.get('categoria', 'INFINITE')}\n"
        f"💱 Moeda: {bin_info.get('moeda', 'BRL')}\n"
        f"🌍 País: {bin_info.get('pais', 'BR')}\n\n"
        f"📦 Estoque: ({bin_info['quantidade']} GG's)\n\n"
        f"Clique para ver:"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"💳 Ver GG's #{bin_id}", callback_data=f"ver_ggs_{bin_id}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="comprar_ggs")]
    ]
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def ver_ggs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bin_id = query.data.replace("ver_ggs_", "")
    bin_info = get_bin(bin_id)
    
    ggs = json.loads(bin_info.get('ggs_json', '[]'))
    
    if not ggs:
        ggs = [f"GG {bin_id}xxxxxx{i:02d}" for i in range(1, min(6, bin_info['quantidade']+1))]
    
    caption = f"💳 GG's\n🃏 BIN: {bin_id}xxxxxx\n🏳️ VISA | 🏦 BANCO BRADESCO, S.A.\n📦 {bin_info['quantidade']} | Pág 1/5\n\n"
    
    keyboard = []
    for i, gg in enumerate(ggs[:5], 1):
        caption += f"  {i}. {gg} — R$ {bin_info['preco']:.2f}\n"
        keyboard.append([InlineKeyboardButton(str(i), callback_data=f"comprar_gg_{bin_id}_{i-1}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"bin_{bin_id}")])
    
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def comprar_logins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    result = supabase.table("logins").select("*").eq("disponivel", 1).execute()
    logins = result.data
    
    if not logins:
        caption = "🔑 *Logins*\n\n❌ Nenhum disponível."
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="produtos")]]
    else:
        caption = "🔑 *Logins disponíveis*\n\n"
        for login in logins[:10]:
            caption += f"📧 {login['email']} — R$ {login['preco']:.2f}\n"
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="produtos")]]
    
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(str(user_id))
    
    caption = (
        f"👤 *Perfil*\n\n"
        f"🆔 {user_id}\n"
        f"🔥 sup7\n"
        f"✏️ @{query.from_user.username if query.from_user.username else 'sem_username'}\n"
        f"📅 {user['data_registro']}\n"
        f"💰 R$ {user['saldo']:.2f}\n"
        f"🛍️ Compras: {user['compras']}\n"
        f"💸 Gasto: R$ {user['gasto']:.2f}"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]]
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def comprar_por_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(str(user_id))
    bins = get_bins()
    
    keyboard = []
    for bin in bins:
        keyboard.append([InlineKeyboardButton(f"{bin['bin_id']} | ({bin['quantidade']})", callback_data=f"comprar_bin_item_{bin['bin_id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu")])
    
    caption = f"🏪 *ESCOLHA SUA BIN*\n\n👤 🆔 {user_id} | 💰 R$ {user['saldo']:.2f}\n\nPágina 1/1"
    
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== SUPORTE ====================
async def suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_caption(
        caption="📞 *Suporte*\n\nDescreva sua dúvida:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu")]]),
        parse_mode=ParseMode.MARKDOWN
    )
    return AGUARDANDO_SUPORTE

async def receber_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    duvida = update.message.text
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📞 *NOVA MENSAGEM DE SUPORTE*\n\n👤 Usuário: {user.first_name}\n🆔 ID: {user.id}\n@: @{user.username if user.username else 'sem username'}\n\n💬 Mensagem:\n{duvida}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await update.message.reply_text("✅ Mensagem enviada! Aguarde o retorno.")
    return ConversationHandler.END

# ==================== ADICIONAR SALDO (MERCADO PAGO) ====================
async def adicionar_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(str(user_id))
    
    keyboard = [
        [InlineKeyboardButton("💸 Adicionar Saldo via PIX", callback_data="pix_adicionar")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="menu")]
    ]
    
    await query.edit_message_caption(
        caption=f"💰 *Saldo*\n\n💵 R$ {user['saldo']:.2f}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def pix_adicionar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_caption(
        caption="💸 *PIX*\n\nDigite o valor (mín R$ 10,00):\nEx: 50.00",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu")]]),
        parse_mode=ParseMode.MARKDOWN
    )
    return AGUARDANDO_PIX_VALOR

async def processar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = float(update.message.text.replace(',', '.'))
        if valor < 10:
            await update.message.reply_text("❌ Valor mínimo é R$ 10,00!")
            return AGUARDANDO_PIX_VALOR
        
        payment_data = {
            "transaction_amount": valor,
            "description": f"Adição de saldo - User {update.effective_user.id}",
            "payment_method_id": "pix",
            "payer": {"email": f"user{update.effective_user.id}@temp.com"}
        }
        
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]
        
        if "point_of_interaction" in payment:
            qr_code = payment["point_of_interaction"]["transaction_data"]["qr_code"]
            qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
            pedido_id = payment["id"]
            
            salvar_pedido_pix(str(pedido_id), str(update.effective_user.id), valor, qr_code, qr_code_base64)
            
            await update.message.reply_text(
                f"✅ *PIX Gerado!*\n\n"
                f"💰 R$ {valor:.2f}\n"
                f"🆔 {pedido_id}\n\n"
                f"📋 *Copia e Cola:*\n`{qr_code}`\n\n"
                f"Clique ✅ após pagar.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Já paguei!", callback_data=f"verificar_pix_{pedido_id}")],
                [InlineKeyboardButton("⬅️ Menu", callback_data="menu")]
            ]
            await update.message.reply_text("Confirme após o pagamento:", reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END
        else:
            await update.message.reply_text("❌ Erro ao gerar PIX. Tente novamente.")
            return ConversationHandler.END
            
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")
        return ConversationHandler.END

async def verificar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pedido_id = query.data.replace("verificar_pix_", "")
    pedido = get_pedido_pix(pedido_id)
    
    if not pedido:
        await query.edit_message_caption("❌ Pedido não encontrado.")
        return
    
    payment = sdk.payment().get(int(pedido_id))
    status = payment["response"].get("status")
    
    if status == "approved":
        atualizar_saldo(pedido["user_id"], pedido["valor"])
        update_pedido_status(pedido_id, "APROVADO")
        await query.edit_message_caption("✅ *Pagamento confirmado!* Saldo adicionado com sucesso!", parse_mode=ParseMode.MARKDOWN)
        await menu(update, context)
    else:
        keyboard = [
            [InlineKeyboardButton("🔄 Verificar", callback_data=f"verificar_pix_{pedido_id}")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu")]
        ]
        await query.edit_message_caption(
            f"⏳ *Pendente*\n\nStatus: {status}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== RESGATE GIFT ====================
async def resgatar_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_caption(
        caption="🎁 *Resgatar Gift*\n\nDigite o código:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu")]]),
        parse_mode=ParseMode.MARKDOWN
    )
    return AGUARDANDO_GIFT

async def processar_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    codigo = update.message.text.strip().upper()
    user_id = str(update.effective_user.id)
    valor = resgatar_gift_db(codigo, user_id)
    
    if valor > 0:
        atualizar_saldo(user_id, valor)
        await update.message.reply_text(f"✅ Gift resgatado! +R$ {valor:.2f} adicionado ao seu saldo.")
    else:
        await update.message.reply_text("❌ Código inválido ou já utilizado!")
    
    return ConversationHandler.END

# ==================== PAINEL ADMIN ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Apenas o administrador!", show_alert=True)
        return
    
    stats = get_estatisticas()
    
    keyboard = [
        [InlineKeyboardButton("➕ Adicionar BIN", callback_data="admin_add_bin")],
        [InlineKeyboardButton("➕ Adicionar Gift", callback_data="admin_add_gift")],
        [InlineKeyboardButton("📊 Estatísticas", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
    ]
    
    caption = (
        f"👑 *Painel Admin*\n\n"
        f"📈 *Estatísticas rápidas:*\n"
        f"👥 Usuários: {stats.get('total_usuarios', 0)}\n"
        f"💰 Saldo total: R$ {stats.get('saldo_total', 0):.2f}\n"
        f"🛍️ Compras: {stats.get('total_compras', 0)}\n"
        f"💵 Faturamento: R$ {stats.get('faturamento', 0):.2f}\n"
        f"📦 Estoque: {stats.get('total_estoque', 0)}"
    )
    
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def admin_add_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.edit_message_caption(
        caption="➕ *Adicionar Nova BIN*\n\nDigite no formato:\n`BIN,QUANTIDADE,PRECO`\n\nExemplo:\n`406670,10,8.00`",
        parse_mode=ParseMode.MARKDOWN
    )
    return AGUARDANDO_NOVA_BIN

async def admin_add_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.edit_message_caption(
        caption="🎁 *Adicionar Gift*\n\nDigite no formato:\n`CODIGO,VALOR`\n\nExemplo:\n`GIFT123,50.00`",
        parse_mode=ParseMode.MARKDOWN
    )
    return AGUARDANDO_VALOR_GIFT

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    stats = get_estatisticas()
    
    usuarios_result = supabase.table("usuarios").select("*").order("data_registro", desc=True).limit(10).execute()
    
    caption = (
        f"📊 *ESTATÍSTICAS COMPLETAS*\n\n"
        f"👥 Total de usuários: {stats.get('total_usuarios', 0)}\n"
        f"💰 Saldo total em carteira: R$ {stats.get('saldo_total', 0):.2f}\n"
        f"🛍️ Total de compras: {stats.get('total_compras', 0)}\n"
        f"💵 Faturamento total: R$ {stats.get('faturamento', 0):.2f}\n"
        f"📦 Estoque total: {stats.get('total_estoque', 0)}\n\n"
        f"👤 *Últimos usuários:*\n"
    )
    
    for user in usuarios_result.data[:5]:
        caption += f"🆔 {user['user_id']} - R$ {user['saldo']:.2f}\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_panel")]]
    
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def processar_nova_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = update.message.text.strip()
        partes = texto.split(',')
        
        if len(partes) != 3:
            await update.message.reply_text("❌ Formato inválido! Use: `BIN,QUANTIDADE,PRECO`", parse_mode=ParseMode.MARKDOWN)
            return AGUARDANDO_NOVA_BIN
        
        bin_id = partes[0].strip()
        quantidade = int(partes[1].strip())
        preco = float(partes[2].strip())
        
        add_bin(bin_id, quantidade, preco)
        await update.message.reply_text(f"✅ BIN {bin_id} adicionada com sucesso!\n📦 {quantidade} unidades\n💰 R$ {preco:.2f}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")
    
    return ConversationHandler.END

async def processar_novo_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = update.message.text.strip()
        partes = texto.split(',')
        
        if len(partes) != 2:
            await update.message.reply_text("❌ Formato inválido! Use: `CODIGO,VALOR`", parse_mode=ParseMode.MARKDOWN)
            return AGUARDANDO_VALOR_GIFT
        
        codigo = partes[0].strip().upper()
        valor = float(partes[1].strip())
        
        add_gift(codigo, valor)
        await update.message.reply_text(f"✅ Gift adicionado com sucesso!\n🎁 Código: `{codigo}`\n💰 Valor: R$ {valor:.2f}", parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")
    
    return ConversationHandler.END

# ==================== MAIN ====================
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(produtos_menu, pattern="^produtos$"))
    app.add_handler(CallbackQueryHandler(comprar_ggs, pattern="^comprar_ggs$"))
    app.add_handler(CallbackQueryHandler(mostrar_bin, pattern="^bin_"))
    app.add_handler(CallbackQueryHandler(ver_ggs, pattern="^ver_ggs_"))
    app.add_handler(CallbackQueryHandler(comprar_logins, pattern="^comprar_logins$"))
    app.add_handler(CallbackQueryHandler(comprar_por_bin, pattern="^comprar_bin$"))
    app.add_handler(CallbackQueryHandler(perfil, pattern="^perfil$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_add_bin, pattern="^admin_add_bin$"))
    app.add_handler(CallbackQueryHandler(admin_add_gift, pattern="^admin_add_gift$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(adicionar_saldo, pattern="^adicionar_saldo$"))
    app.add_handler(CallbackQueryHandler(pix_adicionar, pattern="^pix_adicionar$"))
    app.add_handler(CallbackQueryHandler(verificar_pix, pattern="^verificar_pix_"))
    app.add_handler(CallbackQueryHandler(resgatar_gift, pattern="^resgatar_gift$"))
    
    # Conversas
    conv_suporte = ConversationHandler(
        entry_points=[CallbackQueryHandler(suporte, pattern="^suporte$")],
        states={AGUARDANDO_SUPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_suporte)]},
        fallbacks=[CallbackQueryHandler(menu, pattern="^menu$")]
    )
    
    conv_pix = ConversationHandler(
        entry_points=[CallbackQueryHandler(pix_adicionar, pattern="^pix_adicionar$")],
        states={AGUARDANDO_PIX_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, processar_pix)]},
        fallbacks=[CallbackQueryHandler(menu, pattern="^menu$")]
    )
    
    conv_gift = ConversationHandler(
        entry_points=[CallbackQueryHandler(resgatar_gift, pattern="^resgatar_gift$")],
        states={AGUARDANDO_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, processar_gift)]},
        fallbacks=[CallbackQueryHandler(menu, pattern="^menu$")]
    )
    
    conv_new_bin = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_bin, pattern="^admin_add_bin$")],
        states={AGUARDANDO_NOVA_BIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, processar_nova_bin)]},
        fallbacks=[CallbackQueryHandler(admin_panel, pattern="^admin_panel$")]
    )
    
    conv_new_gift = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_gift, pattern="^admin_add_gift$")],
        states={AGUARDANDO_VALOR_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, processar_novo_gift)]},
        fallbacks=[CallbackQueryHandler(admin_panel, pattern="^admin_panel$")]
    )
    
    app.add_handler(conv_suporte)
    app.add_handler(conv_pix)
    app.add_handler(conv_gift)
    app.add_handler(conv_new_bin)
    app.add_handler(conv_new_gift)
    
    print("🤖 Bot rodando com Supabase - Dados persistentes!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()