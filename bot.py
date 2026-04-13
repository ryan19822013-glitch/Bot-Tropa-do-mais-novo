import requests
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.constants import ParseMode
import mercadopago

# ==================== CONFIGURAÇÕES ====================
TOKEN = "8713124469:AAGCO1MichVkgpIsc__vURreS8e8oX5Qfbo"
ADMIN_ID = 8309449775
GRUPO_LINK = "https://t.me/+laIYEeIQuuc1ZWEx"

# Supabase via REST (sem SDK problemático)
SUPABASE_URL = "https://cebywxcpmkrqwbbhddra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNlYnl3eGNwbWtycXdiYmhkZHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMjYyMTQsImV4cCI6MjA5MTYwMjIxNH0.4hj5uTjLyz5GqvNztMf_XyIpPdzq1obcybGelLEVN74"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = "APP_USR-8313019935361645-040523-f5273bbb40e6f8b1cfa385cbb7716aa5-800117337"
sdk = mercadopago.SDK(MERCADO_PAGO_ACCESS_TOKEN)

# Estados
AGUARDANDO_PIX_VALOR = 1
AGUARDANDO_SUPORTE = 2
AGUARDANDO_GIFT = 3
AGUARDANDO_NOVA_BIN = 4
AGUARDANDO_VALOR_GIFT = 5

# ==================== FUNÇÕES SUPABASE VIA REST ====================
def supabase_get(table, filters=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*"
    if filters:
        for key, value in filters.items():
            url += f"&{key}=eq.{value}"
    response = requests.get(url, headers=HEADERS)
    return response.json()

def supabase_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.post(url, headers=HEADERS, json=data)
    return response.json()

def supabase_update(table, data, filters):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = []
    for key, value in filters.items():
        params.append(f"{key}=eq.{value}")
    if params:
        url += "?" + "&".join(params)
    response = requests.patch(url, headers=HEADERS, json=data)
    return response

def get_user(user_id):
    users = supabase_get("usuarios", {"user_id": str(user_id)})
    if not users:
        novo_user = {
            "user_id": str(user_id),
            "saldo": 0.0,
            "compras": 0,
            "gasto": 0.0,
            "data_registro": datetime.now().strftime("%d/%m/%Y")
        }
        supabase_insert("usuarios", novo_user)
        return novo_user
    return users[0]

def atualizar_saldo(user_id, valor, is_adicao=True):
    user = get_user(user_id)
    novo_saldo = user["saldo"] + valor if is_adicao else user["saldo"] - valor
    novo_compras = user["compras"] + (1 if not is_adicao else 0)
    novo_gasto = user["gasto"] + (valor if not is_adicao else 0)
    
    supabase_update("usuarios", {
        "saldo": novo_saldo,
        "compras": novo_compras,
        "gasto": novo_gasto
    }, {"user_id": str(user_id)})

def get_bins():
    return supabase_get("bins")

def get_bin(bin_id):
    bins = supabase_get("bins", {"bin_id": bin_id})
    return bins[0] if bins else None

def add_bin(bin_id, quantidade, preco):
    supabase_insert("bins", {
        "bin_id": bin_id,
        "nome": bin_id,
        "quantidade": quantidade,
        "preco": preco
    })

def add_gift(codigo, valor):
    supabase_insert("gifts", {
        "codigo": codigo.upper(),
        "valor": valor
    })

def resgatar_gift_db(codigo, user_id):
    gifts = supabase_get("gifts", {"codigo": codigo.upper()})
    if gifts:
        valor = gifts[0]["valor"]
        supabase_update("gifts", {
            "resgatado_por": str(user_id),
            "resgatado_em": datetime.now().strftime("%d/%m/%Y %H:%M")
        }, {"codigo": codigo.upper()})
        return valor
    return 0

def salvar_pedido_pix(pedido_id, user_id, valor, qr_code=""):
    supabase_insert("pedidos_pix", {
        "pedido_id": str(pedido_id),
        "user_id": str(user_id),
        "valor": valor,
        "status": "PENDENTE",
        "qr_code": qr_code
    })

def get_pedido_pix(pedido_id):
    pedidos = supabase_get("pedidos_pix", {"pedido_id": str(pedido_id)})
    return pedidos[0] if pedidos else None

def update_pedido_status(pedido_id, status):
    supabase_update("pedidos_pix", {"status": status}, {"pedido_id": str(pedido_id)})

def get_estatisticas():
    usuarios = supabase_get("usuarios")
    bins = supabase_get("bins")
    total_compras = sum(u.get("compras", 0) for u in usuarios)
    faturamento = sum(u.get("gasto", 0) for u in usuarios)
    saldo_total = sum(u.get("saldo", 0) for u in usuarios)
    
    return {
        "total_usuarios": len(usuarios),
        "saldo_total": saldo_total,
        "total_compras": total_compras,
        "faturamento": faturamento,
        "total_estoque": sum(b.get("quantidade", 0) for b in bins)
    }

# ==================== TECLADOS ====================
def gerar_teclado_menu(user_id):
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
        f"🏳️ Bandeira: VISA\n"
        f"🏦 Banco: BANCO BRADESCO, S.A.\n"
        f"💳 Tipo: CREDIT\n"
        f"🎖️ Categoria: INFINITE\n"
        f"💱 Moeda: BRL\n"
        f"🌍 País: BR\n\n"
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
    
    # Simula GGs
    ggs = [f"GG {bin_id}xxxxxx{i:02d}" for i in range(1, min(6, bin_info['quantidade']+1))]
    
    caption = f"💳 GG's\n🃏 BIN: {bin_id}xxxxxx\n🏳️ VISA | 🏦 BANCO BRADESCO, S.A.\n📦 {bin_info['quantidade']} | Pág 1/5\n\n"
    
    keyboard = []
    for i, gg in enumerate(ggs[:5], 1):
        caption += f"  {i}. {gg} — R$ {bin_info['preco']:.2f}\n"
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"bin_{bin_id}")])
    
    await query.edit_message_caption(
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def comprar_logins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    caption = "🔑 *Logins*\n\n❌ Nenhum disponível."
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

# ==================== ADICIONAR SALDO ====================
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
            pedido_id = payment["id"]
            
            salvar_pedido_pix(str(pedido_id), str(update.effective_user.id), valor, qr_code)
            
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
    usuarios = supabase_get("usuarios")
    
    caption = (
        f"📊 *ESTATÍSTICAS COMPLETAS*\n\n"
        f"👥 Total de usuários: {stats.get('total_usuarios', 0)}\n"
        f"💰 Saldo total em carteira: R$ {stats.get('saldo_total', 0):.2f}\n"
        f"🛍️ Total de compras: {stats.get('total_compras', 0)}\n"
        f"💵 Faturamento total: R$ {stats.get('faturamento', 0):.2f}\n"
        f"📦 Estoque total: {stats.get('total_estoque', 0)}\n\n"
        f"👤 *Últimos usuários:*\n"
    )
    
    for user in usuarios[:5]:
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
    
    print("🤖 Bot rodando com Supabase REST - Sem erros!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()