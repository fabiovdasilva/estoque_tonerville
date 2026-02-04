import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract, desc, cast, String, text, or_, and_
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
import traceback

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'printcontrol_secret'

# --- CONFIGURAÇÃO DE UPLOAD ---
UPLOAD_FOLDER = 'static/uploads/contratos'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

# --- UTILS ---
def limpar_int(valor):
    if not valor or str(valor).strip() == '': return 0
    try: return int(valor)
    except ValueError: return 0

def limpar_float(valor_str):
    if not valor_str or str(valor_str).strip() == '': return 0.0
    try:
        limpo = str(valor_str).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        return float(limpo)
    except ValueError: return 0.0

# --- MODELS ---
class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    margem_atencao_pct = db.Column(db.Integer, default=20)
    dias_alerta_vencimento = db.Column(db.Integer, default=7)
    ultimo_pedido_id = db.Column(db.Integer, default=0)

class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, default=datetime.now)
    acao = db.Column(db.String(100))
    detalhes = db.Column(db.Text)

def registrar_log(acao, detalhes):
    try:
        novo_log = SystemLog(acao=acao, detalhes=detalhes)
        db.session.add(novo_log)
    except Exception as e: print(f"Erro log: {e}")

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo_pessoa = db.Column(db.String(20))
    documento = db.Column(db.String(20))
    endereco = db.Column(db.String(200))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    data_fechamento = db.Column(db.Integer)
    observacao = db.Column(db.Text)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    marca = db.Column(db.String(50))
    compatibilidade = db.Column(db.String(150))
    quantidade = db.Column(db.Integer, default=0)
    minimo = db.Column(db.Integer, default=5)
    valor_pago = db.Column(db.Float, default=0.0) 
    valor_venda = db.Column(db.Float, default=0.0)
    observacao = db.Column(db.String(200))
    ativo = db.Column(db.Boolean, default=True)

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    data = db.Column(db.DateTime, default=datetime.now)
    valor_total = db.Column(db.Float, default=0.0)
    forma_pagamento = db.Column(db.String(50)) 
    data_vencimento = db.Column(db.Date)
    status_pagamento = db.Column(db.String(20), default='Pendente') 
    status_nf = db.Column(db.String(20), default='Falta NF') 
    numero_nf = db.Column(db.String(50))
    status_boleto = db.Column(db.String(20), nullable=True)
    numero_boleto = db.Column(db.String(50))
    status_envio = db.Column(db.String(20), default='Falta Enviar')
    status_geral = db.Column(db.String(20), default='Ativa')
    justificativa_cancelamento = db.Column(db.String(255))
    observacao = db.Column(db.Text)
    cliente = db.relationship('Cliente', backref='vendas')
    itens = db.relationship('ItemVenda', backref='venda', cascade="all, delete-orphan")

class ItemVenda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey('venda.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    valor_unitario = db.Column(db.Float, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    produto = db.relationship('Produto')

class PedidoSaida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_pedido = db.Column(db.Integer, unique=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    data = db.Column(db.DateTime, default=datetime.now)
    impressora = db.Column(db.String(100))
    observacao = db.Column(db.String(200))
    status = db.Column(db.String(20), default='Ativo')
    justificativa_cancelamento = db.Column(db.String(255))
    cliente = db.relationship('Cliente', backref='pedidos')
    itens = db.relationship('ItemPedido', backref='pedido', cascade="all, delete-orphan")

class ItemPedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_saida.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    produto = db.relationship('Produto')

class Movimentacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    tipo = db.Column(db.String(20))
    categoria_movimento = db.Column(db.String(50)) 
    numero_documento = db.Column(db.String(50)) 
    quantidade = db.Column(db.Integer, nullable=False)
    valor_unitario_entrada = db.Column(db.Float, default=0.0)
    data = db.Column(db.DateTime, default=datetime.now)
    destino_origem = db.Column(db.String(100))
    observacao = db.Column(db.String(200))
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_saida.id'), nullable=True)
    status = db.Column(db.String(20), default='Ativo')
    justificativa_cancelamento = db.Column(db.String(255))
    produto = db.relationship('Produto', backref='movimentacoes')

class Impressora(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marca = db.Column(db.String(50))
    modelo = db.Column(db.String(100), nullable=False)
    serial = db.Column(db.String(50), unique=True)
    mlt = db.Column(db.String(50)) 
    contador = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='Disponível')
    localizacao = db.Column(db.String(100), default='Estoque')
    observacao = db.Column(db.Text)
    data_aquisicao = db.Column(db.Date)
    
    historico = db.relationship('MovimentacaoImpressora', backref='impressora', cascade="all, delete-orphan")
    manutencoes = db.relationship('Manutencao', backref='impressora', cascade="all, delete-orphan")
    logs_manutencao = db.relationship('LogManutencao', backref='impressora', cascade="all, delete-orphan")

class MovimentacaoImpressora(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    impressora_id = db.Column(db.Integer, db.ForeignKey('impressora.id'), nullable=False)
    data = db.Column(db.DateTime, default=datetime.now)
    tipo = db.Column(db.String(50)) 
    origem = db.Column(db.String(100))
    destino = db.Column(db.String(100))
    contador_momento = db.Column(db.Integer)
    usuario = db.Column(db.String(50), default='Admin')
    observacao = db.Column(db.Text)

class Manutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    impressora_id = db.Column(db.Integer, db.ForeignKey('impressora.id'), nullable=False)
    numero_ordem = db.Column(db.Integer)
    data_inicio = db.Column(db.DateTime, default=datetime.now)
    data_fim = db.Column(db.DateTime)
    status_atual = db.Column(db.String(50), default='Aberta')
    motivo_inicial = db.Column(db.Text)
    logs = db.relationship('LogManutencao', backref='manutencao_pai', cascade="all, delete-orphan")

class LogManutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    manutencao_id = db.Column(db.Integer, db.ForeignKey('manutencao.id'), nullable=True) 
    impressora_id = db.Column(db.Integer, db.ForeignKey('impressora.id'), nullable=True)
    data = db.Column(db.DateTime, default=datetime.now)
    titulo = db.Column(db.String(100))
    observacao = db.Column(db.Text)
    usuario = db.Column(db.String(50), default='Admin')

class Fornecedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    telefone = db.Column(db.String(50))
    observacao = db.Column(db.Text)
    pedidos = db.relationship('PedidoCompra', backref='fornecedor', cascade="all, delete-orphan")

class PedidoCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedor.id'), nullable=False)
    valor_itens = db.Column(db.Float, default=0.0)
    frete = db.Column(db.Float, default=0.0)
    valor_total = db.Column(db.Float, default=0.0)
    prazo_pagamento = db.Column(db.String(50)) 
    data_emissao = db.Column(db.Date, default=datetime.now)
    data_entrega_prevista = db.Column(db.Date)
    status = db.Column(db.String(20), default='Pendente')
    observacao = db.Column(db.Text)
    itens = db.relationship('ItemPedidoCompra', backref='pedido', cascade="all, delete-orphan")

class ItemPedidoCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_compra.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=True)
    descricao = db.Column(db.String(200))
    quantidade = db.Column(db.Integer, nullable=False)
    valor_unitario = db.Column(db.Float, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    produto = db.relationship('Produto')

class Contrato(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    cliente = db.relationship('Cliente', backref='contratos') 
    
    numero_contrato = db.Column(db.String(50))
    data_inicio = db.Column(db.Date)
    data_fim = db.Column(db.Date)
    status = db.Column(db.String(20), default='Ativo')
    valor_mensal_total = db.Column(db.Float, default=0.0)
    dia_vencimento = db.Column(db.Integer)
    arquivo_pdf = db.Column(db.String(200))
    justificativa_cancelamento = db.Column(db.Text)
    
    itens = db.relationship('ContratoItem', backref='contrato', lazy=True)
    franquias = db.relationship('ContratoFranquia', backref='contrato', lazy=True)
    
    # Campos legados
    franquia_global_qtde = db.Column(db.Integer, default=0)
    valor_excedente_global = db.Column(db.Float, default=0.0)
    
class ContratoFranquia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contrato.id'), nullable=False)
    nome = db.Column(db.String(50))
    tipo = db.Column(db.String(20)) # "Compartilhada" ou "Individual"
    franquia_paginas = db.Column(db.Integer, default=0)
    valor_franquia = db.Column(db.Float, default=0.0)
    valor_excedente = db.Column(db.Float, default=0.0)
    itens = db.relationship('ContratoItem', backref='franquia_pai', lazy=True)

class ContratoItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contrato.id'), nullable=False)
    impressora_id = db.Column(db.Integer, db.ForeignKey('impressora.id'), nullable=False)
    franquia_id = db.Column(db.Integer, db.ForeignKey('contrato_franquia.id'), nullable=True)
    valor_locacao_unitario = db.Column(db.Float, default=0.0)
    tipo_franquia_item = db.Column(db.String(20)) # Legado/Fallback
    
    impressora = db.relationship('Impressora') 

# --- NOVO MODELO: HISTÓRICO DO CONTRATO ---
class ContratoHistorico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contrato.id'), nullable=False)
    data = db.Column(db.DateTime, default=datetime.now)
    usuario = db.Column(db.String(50), default='Sistema')
    acao = db.Column(db.String(50))
    detalhes = db.Column(db.Text)

def registrar_hist_contrato(contrato_id, acao, detalhes, usuario='Sistema'):
    try:
        novo = ContratoHistorico(contrato_id=contrato_id, acao=acao, detalhes=detalhes, usuario=usuario)
        db.session.add(novo)
        db.session.flush() 
    except Exception as e:
        print(f"Erro ao gravar historico contrato: {e}")



# --- NOVOS MODELS FINANCEIROS ---
class Banco(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_banco = db.Column(db.String(100), nullable=False)
    agencia_conta = db.Column(db.String(100))
    saldo_inicial = db.Column(db.Float, default=0.0)
    saldo_atual = db.Column(db.Float, default=0.0)
    lancamentos = db.relationship('LancamentoFinanceiro', backref='banco', lazy=True)

class LancamentoFinanceiro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20)) # 'Receita' ou 'Despesa'
    categoria_custo = db.Column(db.String(20)) # 'Fixo' ou 'Variavel'
    valor = db.Column(db.Float, nullable=False)
    data_vencimento = db.Column(db.Date)
    data_pagamento = db.Column(db.Date) # Se null, está pendente
    pago = db.Column(db.Boolean, default=False)
    banco_id = db.Column(db.Integer, db.ForeignKey('banco.id'), nullable=True)




  # --- ROTAS FINANCEIRAS ---

@app.route('/financeiro')
def financeiro():
    # 1. Configurações Básicas
    hoje = datetime.now()
    primeiro_dia_mes = hoje.replace(day=1)
    # Lógica simples para pegar ultimo dia do mes
    proximo_mes = hoje.replace(day=28) + timedelta(days=4)
    ultimo_dia_mes = proximo_mes - timedelta(days=proximo_mes.day)

    # 2. Filtros e Dados Gerais
    bancos = Banco.query.all()
    saldo_bancos_total = sum(b.saldo_atual for b in bancos)
    
    # 3. Dashboard: Totais do Mês (Confirmados)
    movs_mes = LancamentoFinanceiro.query.filter(
        LancamentoFinanceiro.data_pagamento >= primeiro_dia_mes,
        LancamentoFinanceiro.data_pagamento <= ultimo_dia_mes,
        LancamentoFinanceiro.pago == True
    ).all()
    
    total_receitas_mes = sum(l.valor for l in movs_mes if l.tipo == 'Receita')
    total_despesas_mes = sum(l.valor for l in movs_mes if l.tipo == 'Despesa')
    
    # 4. Situação do Dia (Saldo Hoje)
    # Pega tudo que foi pago HOJE
    movs_hoje = LancamentoFinanceiro.query.filter(
        extract('day', LancamentoFinanceiro.data_pagamento) == hoje.day,
        extract('month', LancamentoFinanceiro.data_pagamento) == hoje.month,
        extract('year', LancamentoFinanceiro.data_pagamento) == hoje.year,
        LancamentoFinanceiro.pago == True
    ).all()
    rec_hoje = sum(l.valor for l in movs_hoje if l.tipo == 'Receita')
    desp_hoje = sum(l.valor for l in movs_hoje if l.tipo == 'Despesa')
    saldo_dia_hoje = rec_hoje - desp_hoje # Positivo ou Negativo

    # 5. Previsão Fim de Mês
    # Pega pendentes até o fim do mês
    pendentes = LancamentoFinanceiro.query.filter(
        LancamentoFinanceiro.data_vencimento <= ultimo_dia_mes,
        LancamentoFinanceiro.pago == False
    ).all()
    pendente_receita = sum(l.valor for l in pendentes if l.tipo == 'Receita')
    pendente_despesa = sum(l.valor for l in pendentes if l.tipo == 'Despesa')
    
    saldo_projetado = saldo_bancos_total + pendente_receita - pendente_despesa

    # 6. Relatório Filtrado (Fixo/Variavel)
    filtro_tipo = request.args.get('filtro_tipo_custo', 'Todos')
    query_rel = LancamentoFinanceiro.query.filter(LancamentoFinanceiro.tipo == 'Despesa')
    if filtro_tipo != 'Todos':
        query_rel = query_rel.filter(LancamentoFinanceiro.categoria_custo == filtro_tipo)
    relatorio_despesas = query_rel.order_by(LancamentoFinanceiro.data_vencimento).limit(50).all()

    # 7. Lógica de Fluxo de Caixa (Conciliação)
    fc_banco_id = request.args.get('fc_banco_id')
    fc_banco_selecionado = int(fc_banco_id) if fc_banco_id else (bancos[0].id if bancos else None)
    fc_data_ini = request.args.get('fc_data_ini', primeiro_dia_mes.strftime('%Y-%m-%d'))
    fc_data_fim = request.args.get('fc_data_fim', ultimo_dia_mes.strftime('%Y-%m-%d'))
    
    fc_extrato = []
    fc_banco_obj = None
    fc_saldo_anterior = 0
    fc_total_receitas = 0
    fc_total_despesas = 0

    if fc_banco_selecionado:
        fc_banco_obj = Banco.query.get(fc_banco_selecionado)
        
        # Extrato do Período
        d_ini = datetime.strptime(fc_data_ini, '%Y-%m-%d')
        d_fim = datetime.strptime(fc_data_fim, '%Y-%m-%d')
        
        fc_extrato = LancamentoFinanceiro.query.filter(
            LancamentoFinanceiro.banco_id == fc_banco_selecionado,
            LancamentoFinanceiro.pago == True,
            LancamentoFinanceiro.data_pagamento >= d_ini,
            LancamentoFinanceiro.data_pagamento <= d_fim
        ).order_by(LancamentoFinanceiro.data_pagamento).all()
        
        # Totais do período
        fc_total_receitas = sum(l.valor for l in fc_extrato if l.tipo == 'Receita')
        fc_total_despesas = sum(l.valor for l in fc_extrato if l.tipo == 'Despesa')
        
        # Cálculo aproximado do saldo anterior (Backwards calculation)
        # Saldo Anterior = Saldo Atual - (Receitas Período - Despesas Período) - (Movs Futuras...)
        # Simplificação: Para conciliação exata, o ideal é ter tabela de fechamento diário.
        # Aqui usaremos a lógica: Saldo Anterior = (Saldo Atual) - (Tudo que aconteceu DEPOIS da data ini)
        # Mas para simplificar a visualização imediata pedida:
        fc_saldo_anterior = fc_banco_obj.saldo_atual - (fc_total_receitas - fc_total_despesas)

    return render_template('financeiro.html',
                           hoje=hoje,
                           bancos=bancos,
                           saldo_bancos_total=saldo_bancos_total,
                           total_receitas_mes=total_receitas_mes,
                           total_despesas_mes=total_despesas_mes,
                           saldo_dia_hoje=saldo_dia_hoje,
                           pendente_receita=pendente_receita,
                           pendente_despesa=pendente_despesa,
                           saldo_projetado=saldo_projetado,
                           relatorio_despesas=relatorio_despesas,
                           filtro_tipo_custo=filtro_tipo,
                           lancamentos_todos=LancamentoFinanceiro.query.order_by(LancamentoFinanceiro.data_vencimento.desc()).limit(20).all(),
                           fc_banco_selecionado=fc_banco_selecionado,
                           fc_banco_obj=fc_banco_obj,
                           fc_data_ini=fc_data_ini,
                           fc_data_fim=fc_data_fim,
                           fc_extrato=fc_extrato,
                           fc_saldo_anterior=fc_saldo_anterior,
                           fc_total_receitas=fc_total_receitas,
                           fc_total_despesas=fc_total_despesas)

@app.route('/criar_banco', methods=['POST'])
def criar_banco():
    nome = request.form.get('nome_banco')
    agencia = request.form.get('agencia_conta')
    saldo_ini = limpar_float(request.form.get('saldo_inicial'))
    
    novo = Banco(nome_banco=nome, agencia_conta=agencia, saldo_inicial=saldo_ini, saldo_atual=saldo_ini)
    db.session.add(novo)
    db.session.commit()
    flash('Banco cadastrado com sucesso.')
    return redirect(url_for('financeiro', tab_ativa='tab-bancos'))

@app.route('/novo_lancamento', methods=['POST'])
def novo_lancamento():
    try:
        desc = request.form.get('descricao')
        tipo = request.form.get('tipo')
        cat = request.form.get('categoria_custo')
        valor = limpar_float(request.form.get('valor'))
        banco_id = int(request.form.get('banco_id'))
        venc = datetime.strptime(request.form.get('data_vencimento'), '%Y-%m-%d')
        status = request.form.get('status')
        
        pago = (status == 'Pago')
        data_pgto = datetime.now() if pago else None
        
        novo = LancamentoFinanceiro(descricao=desc, tipo=tipo, categoria_custo=cat, valor=valor, 
                                    data_vencimento=venc, banco_id=banco_id, pago=pago, data_pagamento=data_pgto)
        
        if pago:
            banco = Banco.query.get(banco_id)
            if tipo == 'Receita': banco.saldo_atual += valor
            else: banco.saldo_atual -= valor
            
        db.session.add(novo)
        db.session.commit()
        flash('Lançamento registrado.')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}')
    return redirect(url_for('financeiro'))

@app.route('/baixa_lancamento', methods=['POST'])
def baixa_lancamento():
    id_lanc = request.form.get('id')
    lanc = LancamentoFinanceiro.query.get(id_lanc)
    if lanc and not lanc.pago:
        lanc.pago = True
        lanc.data_pagamento = datetime.now()
        
        banco = Banco.query.get(lanc.banco_id)
        if lanc.tipo == 'Receita': banco.saldo_atual += lanc.valor
        else: banco.saldo_atual -= lanc.valor
        
        db.session.commit()
        flash('Baixa realizada com sucesso.')
    return redirect(url_for('financeiro'))

@app.route('/ajuste_saldo_banco', methods=['POST'])
def ajuste_saldo_banco():
    banco_id = request.form.get('banco_id')
    novo_saldo = limpar_float(request.form.get('novo_saldo'))
    justificativa = request.form.get('justificativa')
    
    banco = Banco.query.get(banco_id)
    diferenca = novo_saldo - banco.saldo_atual
    
    if diferenca != 0:
        tipo = 'Receita' if diferenca > 0 else 'Despesa'
        valor_ajuste = abs(diferenca)
        
        # Cria um lançamento automático de ajuste
        ajuste = LancamentoFinanceiro(
            descricao=f"Ajuste Manual: {justificativa}",
            tipo=tipo,
            categoria_custo='Variavel',
            valor=valor_ajuste,
            data_vencimento=datetime.now(),
            data_pagamento=datetime.now(),
            pago=True,
            banco_id=banco.id
        )
        banco.saldo_atual = novo_saldo
        db.session.add(ajuste)
        db.session.commit()
        flash('Saldo ajustado com sucesso.')
        
    return redirect(url_for('financeiro', fc_banco_id=banco_id, tab_ativa='tab-caixa'))  





# --- CONTEXTO ---
@app.template_filter('currency')
def currency_filter(value):
    if value is None: value = 0
    return "R$ {:,.2f}".format(value).replace(",", "X").replace(".", ",").replace("X", ".")

@app.template_filter('formata_codigo')
def formata_codigo(id): return f"P{id:03d}"

@app.context_processor
def utility_processor():
    try:
        config = Configuracao.query.first()
        if not config:
            config = Configuracao()
            db.session.add(config)
            db.session.commit()
        return dict(hoje=datetime.now(), config=config)
    except: return dict(hoje=datetime.now(), config=None)

# --- ROTAS ---

# Certifique-se de ter importado isso no topo: 
# from sqlalchemy import extract, func

@app.route('/')
@app.route('/index')
def index():
    hoje = datetime.now()
    primeiro_dia_mes = hoje.replace(day=1)
    
    # 1. KPIs Gerais (Mantidos)
    vendas_mes = Venda.query.filter(Venda.data >= primeiro_dia_mes).all()
    total_vendas_mes = sum(v.valor_total for v in vendas_mes)
    
    contratos_ativos = Contrato.query.filter_by(status='Ativo').all()
    total_contratos_ativos = len(contratos_ativos)
    total_contratos_valor = sum(c.valor_mensal_total for c in contratos_ativos)
    
    itens_alerta = Produto.query.filter(Produto.quantidade <= Produto.minimo).all()
    total_itens_alerta = len(itens_alerta)
    
    # Pendências (Vendas vencidas pendentes)
    vendas_atrasadas = Venda.query.filter(
        Venda.status_pagamento == 'Pendente',
        Venda.data_vencimento < hoje.date()
    ).count()
    total_alertas = total_itens_alerta + vendas_atrasadas

    # 2. Dados para Gráfico Financeiro (Últimos 6 meses)
    grafico_labels = []
    grafico_receitas = []
    grafico_despesas = []

    for i in range(5, -1, -1):
        data_ref = hoje - timedelta(days=i*30) 
        mes = data_ref.month
        ano = data_ref.year
        grafico_labels.append(data_ref.strftime('%b'))

        # Tenta pegar do financeiro real, fallback para zero
        try:
            rec = db.session.query(func.sum(LancamentoFinanceiro.valor)).filter(
                extract('month', LancamentoFinanceiro.data_pagamento) == mes,
                extract('year', LancamentoFinanceiro.data_pagamento) == ano,
                LancamentoFinanceiro.tipo == 'Receita',
                LancamentoFinanceiro.pago == True
            ).scalar() or 0
            
            desp = db.session.query(func.sum(LancamentoFinanceiro.valor)).filter(
                extract('month', LancamentoFinanceiro.data_pagamento) == mes,
                extract('year', LancamentoFinanceiro.data_pagamento) == ano,
                LancamentoFinanceiro.tipo == 'Despesa',
                LancamentoFinanceiro.pago == True
            ).scalar() or 0
        except:
            rec = 0
            desp = 0
        
        grafico_receitas.append(rec)
        grafico_despesas.append(desp)

    # 3. Dados para Gráfico Pizza (Status Impressoras)
    # Contagem por status
    imp_disp = Impressora.query.filter_by(status='Disponível').count()
    imp_loc = Impressora.query.filter(or_(Impressora.status=='Locada', Impressora.status=='Em Cliente')).count()
    imp_manut = Impressora.query.filter_by(status='Manutenção').count()
    
    status_impressoras = {
        'Disponivel': imp_disp,
        'Locada': imp_loc,
        'Manutencao': imp_manut
    }

    # 4. TABELA 1: Vencimentos Próximos (Financeiro)
    # Pega vendas pendentes que vencem nos próximos 15 dias ou já venceram
    data_limite = hoje.date() + timedelta(days=15)
    lista_vencimentos = Venda.query.filter(
        Venda.status_pagamento == 'Pendente',
        Venda.data_vencimento <= data_limite
    ).order_by(Venda.data_vencimento).limit(5).all()

    # 5. TABELA 2: Movimentações Estoque (Entrada/Saída Itens)
    # Pega da tabela Movimentacao (Produtos)
    lista_mov_estoque = Movimentacao.query.order_by(Movimentacao.data.desc()).limit(7).all()

    # 6. TABELA 3: Movimentações Impressoras
    # Pega da tabela MovimentacaoImpressora
    lista_mov_impressoras = MovimentacaoImpressora.query.order_by(MovimentacaoImpressora.data.desc()).limit(7).all()

    return render_template('dashboard.html', 
                           hoje=hoje.strftime('%d/%m/%Y'),
                           total_vendas_mes=total_vendas_mes,
                           total_contratos_ativos=total_contratos_ativos,
                           total_contratos_valor=total_contratos_valor,
                           total_itens_alerta=total_itens_alerta,
                           total_alertas=total_alertas,
                           grafico_labels=grafico_labels,
                           grafico_receitas=grafico_receitas,
                           grafico_despesas=grafico_despesas,
                           status_impressoras=status_impressoras,
                           lista_vencimentos=lista_vencimentos,
                           lista_mov_estoque=lista_mov_estoque,
                           lista_mov_impressoras=lista_mov_impressoras)


@app.route('/notificacoes')
def notificacoes():
    config = Configuracao.query.first()
    margem = config.margem_atencao_pct if config else 20
    dias_vencimento = config.dias_alerta_vencimento if config else 7
    todos_produtos = Produto.query.all()
    itens_atencao = []
    for p in todos_produtos:
        if p.ativo:
            limite = p.minimo * (1 + margem / 100)
            if p.quantidade <= p.minimo: itens_atencao.append({'produto': p, 'status': 'Crítico', 'classe': 'bg-danger', 'row_class': 'row-alert-red'})
            elif p.quantidade <= limite: itens_atencao.append({'produto': p, 'status': 'Baixo', 'classe': 'bg-warning text-dark', 'row_class': 'row-alert-orange'})
    data_limite = datetime.now().date() + timedelta(days=dias_vencimento)
    vendas_vencendo = Venda.query.filter(Venda.status_pagamento != 'Pago', Venda.status_geral != 'Cancelada', Venda.data_vencimento <= data_limite).order_by(Venda.data_vencimento).all()
    return render_template('notificacoes.html', itens_atencao=itens_atencao, vendas_vencendo=vendas_vencendo)

@app.route('/estoque')
def estoque():
    marca_filtro = request.args.get('marca')
    apenas_disponiveis = request.args.get('disponiveis')
    query = Produto.query
    if marca_filtro and marca_filtro != 'Todas': query = query.filter(Produto.marca.ilike(f'%{marca_filtro}%'))
    if apenas_disponiveis: query = query.filter(Produto.quantidade > 0)
    produtos = query.all()
    historico = Movimentacao.query.order_by(Movimentacao.data.desc()).limit(30).all()
    valor_total_estoque = sum([p.quantidade * p.valor_pago for p in produtos])
    total_itens_estoque = sum([p.quantidade for p in produtos])
    top_saidas = db.session.query(Produto.nome, Produto.marca, func.sum(Movimentacao.quantidade).label('total')).join(Movimentacao).filter(Movimentacao.tipo.in_(['Saida_Locacao', 'Venda', 'Ajuste_Saida']), Movimentacao.status != 'Cancelado').group_by(Produto.id).order_by(desc('total')).limit(30).all()
    marcas = db.session.query(Produto.marca).distinct().all()
    lista_marcas = [m[0] for m in marcas if m[0]]
    return render_template('estoque.html', produtos=produtos, historico=historico, marcas=lista_marcas, valor_total_estoque=valor_total_estoque, total_itens_estoque=total_itens_estoque, top_saidas=top_saidas)

@app.route('/saida_locacao')
def saida_locacao():
    busca = request.args.get('busca')
    periodo = request.args.get('periodo')
    cliente_id = request.args.get('cliente_id')
    query = PedidoSaida.query
    if busca:
        term = f"%{busca}%"
        query = query.join(Cliente).filter((cast(PedidoSaida.numero_pedido, String).like(term)) | (Cliente.nome.like(term)) | (PedidoSaida.impressora.like(term)))
    if cliente_id and cliente_id != 'Todos': query = query.filter(PedidoSaida.cliente_id == int(cliente_id))
    if periodo == 'mes_passado':
        mes_passado = datetime.now().month - 1
        query = query.filter(extract('month', PedidoSaida.data) == mes_passado)
    elif periodo != 'todos': 
        mes_atual = datetime.now().month
        query = query.filter(extract('month', PedidoSaida.data) == mes_atual)
    pedidos = query.order_by(PedidoSaida.data.desc()).all()
    produtos = Produto.query.filter(Produto.quantidade > 0).all()
    clientes = Cliente.query.order_by(Cliente.nome).all()
    mes_atual = datetime.now().month
    top_clientes = db.session.query(Cliente.nome, func.sum(ItemPedido.quantidade).label('total_itens')).join(PedidoSaida, Cliente.pedidos).join(ItemPedido).filter(extract('month', PedidoSaida.data) == mes_atual, PedidoSaida.status == 'Ativo').group_by(Cliente.id).order_by(desc('total_itens')).limit(30).all()
    return render_template('saida_locacao.html', produtos=produtos, clientes=clientes, pedidos=pedidos, top_clientes=top_clientes, hoje=datetime.now())

@app.route('/clientes')
def clientes():
    todos_clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes.html', clientes=todos_clientes)

@app.route('/vendas')
def vendas():
    clientes = Cliente.query.order_by(Cliente.nome).all()
    produtos = Produto.query.filter(Produto.quantidade > 0).all()
    query = Venda.query.filter(Venda.status_geral != 'Cancelada')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    if data_inicio and data_fim:
        try:
            inicio = datetime.strptime(data_inicio, '%Y-%m-%d')
            fim = datetime.strptime(data_fim, '%Y-%m-%d').replace(hour=23, minute=59)
            query = query.filter(Venda.data.between(inicio, fim))
        except: pass
    status_filtro = request.args.get('status_filtro')
    hoje_date = datetime.now().date()
    if status_filtro == 'Pendentes': query = query.filter(Venda.status_pagamento != 'Pago')
    elif status_filtro == 'Finalizadas': query = query.filter(Venda.status_pagamento == 'Pago')
    elif status_filtro == 'Vencidas': query = query.filter(Venda.status_pagamento != 'Pago', Venda.data_vencimento < hoje_date)
    status_pagamento = request.args.get('status_pagamento')
    if status_pagamento and status_pagamento != 'Todos': query = query.filter(Venda.status_pagamento == status_pagamento)
    todas_vendas = query.order_by(Venda.data.desc()).all()
    vencimentos = Venda.query.filter(Venda.status_geral != 'Cancelada', Venda.status_pagamento != 'Pago', Venda.data_vencimento != None).order_by(Venda.data_vencimento).all()
    canceladas = Venda.query.filter(Venda.status_geral == 'Cancelada').order_by(Venda.data.desc()).all()
    return render_template('vendas.html', vendas=todas_vendas, vencimentos=vencimentos, canceladas=canceladas, clientes=clientes, produtos=produtos, hoje=datetime.now())

# ... [Bloco de rotas CRUD vendas/estoque/pedidos mantido igual] ...
@app.route('/cancelar_venda', methods=['POST'])
def cancelar_venda():
    venda_id = request.form.get('venda_id')
    justificativa = request.form.get('justificativa')
    venda = Venda.query.get(venda_id)
    if not venda: return redirect(url_for('vendas'))
    for item in venda.itens:
        produto = Produto.query.get(item.produto_id)
        produto.quantidade += item.quantidade
    movs = Movimentacao.query.filter_by(numero_documento=f"V-{venda.id}").all()
    for m in movs:
        m.status = 'Cancelado'
        m.justificativa_cancelamento = justificativa
        m.observacao = (m.observacao or '') + " [CANCELADO]"
    venda.status_geral = 'Cancelada'
    venda.justificativa_cancelamento = justificativa
    registrar_log('Cancelamento Venda', f'Venda #{venda.id} cancelada.')
    db.session.commit()
    flash('Venda cancelada com sucesso.')
    return redirect(url_for('vendas'))

@app.route('/cancelar_pedido_saida', methods=['POST'])
def cancelar_pedido_saida():
    pedido_id = request.form.get('pedido_id')
    justificativa = request.form.get('justificativa')
    pedido = PedidoSaida.query.get(pedido_id)
    if not pedido or pedido.status == 'Cancelado': return redirect(url_for('saida_locacao'))
    for item in pedido.itens:
        produto = Produto.query.get(item.produto_id)
        produto.quantidade += item.quantidade
    pedido.status = 'Cancelado'
    pedido.justificativa_cancelamento = justificativa
    movs = Movimentacao.query.filter_by(pedido_id=pedido.id).all()
    for m in movs: 
        m.status = 'Cancelado'
        m.justificativa_cancelamento = justificativa
        m.observacao = (m.observacao or '') + f" [CANCELADO: {justificativa}]"
    registrar_log('Cancelamento Pedido', f'Pedido #{pedido.numero_pedido} cancelado.')
    db.session.commit()
    flash('Pedido cancelado e estoque estornado.')
    return redirect(url_for('saida_locacao'))

@app.route('/cancelar_movimentacao', methods=['POST'])
def cancelar_movimentacao():
    mov_id = request.form.get('movimentacao_id')
    justificativa = request.form.get('justificativa')
    mov = Movimentacao.query.get(mov_id)
    if not mov or mov.status == 'Cancelado': return redirect(url_for('estoque'))
    produto = Produto.query.get(mov.produto_id)
    if mov.tipo == 'Entrada':
        if produto.quantidade < mov.quantidade:
            flash(f'Erro: Estoque insuficiente para cancelar entrada.')
            return redirect(url_for('estoque'))
        produto.quantidade -= mov.quantidade
    else: produto.quantidade += mov.quantidade
    mov.status = 'Cancelado'
    mov.justificativa_cancelamento = justificativa
    mov.observacao = (mov.observacao or '') + " [CANCELADO]"
    db.session.commit()
    return redirect(url_for('estoque'))

@app.route('/nova_venda', methods=['POST'])
def nova_venda():
    try:
        cliente_id = int(request.form['cliente_id'])
        forma_pagamento = request.form['forma_pagamento']
        vencimento_str = request.form.get('data_vencimento')
        data_vencimento = datetime.strptime(vencimento_str, '%Y-%m-%d').date() if vencimento_str else None
        status_boleto = 'Falta Boleto' if forma_pagamento == 'BOLETO' else None
        nova_venda = Venda(cliente_id=cliente_id, forma_pagamento=forma_pagamento, data_vencimento=data_vencimento, status_pagamento='Pendente', status_nf='Falta NF', status_boleto=status_boleto, status_envio='Falta Enviar', status_geral='Ativa', observacao=request.form.get('observacao'))
        db.session.add(nova_venda)
        db.session.commit()
        produtos_ids = request.form.getlist('produtos[]')
        quantidades = request.form.getlist('quantidades[]')
        valores = request.form.getlist('valores[]')
        valor_total_venda = 0
        for p_id, qtd, val in zip(produtos_ids, quantidades, valores):
            if not p_id: continue
            qtd = int(qtd)
            valor_unit = limpar_float(val)
            valor_item_total = qtd * valor_unit
            produto = Produto.query.get(int(p_id))
            if produto.quantidade < qtd:
                db.session.rollback()
                flash(f'Erro: Estoque insuficiente para {produto.nome}.')
                return redirect(url_for('vendas'))
            produto.quantidade -= qtd
            item = ItemVenda(venda_id=nova_venda.id, produto_id=produto.id, quantidade=qtd, valor_unitario=valor_unit, valor_total=valor_item_total)
            db.session.add(item)
            mov = Movimentacao(produto_id=produto.id, tipo='Venda', categoria_movimento='Venda', numero_documento=f"V-{nova_venda.id}", quantidade=qtd, destino_origem=nova_venda.cliente.nome, observacao=f"Venda #{nova_venda.id}")
            db.session.add(mov)
            valor_total_venda += valor_item_total
        nova_venda.valor_total = valor_total_venda
        registrar_log('Nova Venda', f'Venda #{nova_venda.id} criada.')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(e)
    return redirect(url_for('vendas'))

@app.route('/atualizar_venda', methods=['POST'])
def atualizar_venda():
    venda_id = request.form.get('venda_id')
    venda = Venda.query.get(venda_id)
    if not venda: return redirect(url_for('vendas'))
    novo_vencimento = request.form.get('data_vencimento')
    if novo_vencimento:
        try: venda.data_vencimento = datetime.strptime(novo_vencimento, '%Y-%m-%d').date()
        except ValueError: pass
    nova_forma = request.form.get('forma_pagamento')
    if nova_forma and nova_forma != venda.forma_pagamento:
        venda.forma_pagamento = nova_forma
        if nova_forma != 'BOLETO': venda.status_boleto = None; venda.numero_boleto = None
        elif not venda.status_boleto: venda.status_boleto = 'Falta Boleto'
    pgto = request.form.get('status_pagamento')
    if pgto: venda.status_pagamento = pgto
    status_nf = request.form.get('status_nf')
    numero_nf = request.form.get('numero_nf')
    if status_nf == 'NF Feita':
        if not numero_nf or numero_nf.strip() == '': return redirect(url_for('vendas'))
        venda.numero_nf = numero_nf
    if status_nf: venda.status_nf = status_nf
    status_boleto = request.form.get('status_boleto')
    numero_boleto = request.form.get('numero_boleto')
    if venda.forma_pagamento == 'BOLETO' and status_boleto:
        venda.status_boleto = status_boleto
        if status_boleto == 'Boleto Feito': venda.numero_boleto = numero_boleto
    status_envio = request.form.get('status_envio')
    if status_envio: venda.status_envio = status_envio
    db.session.commit()
    return redirect(url_for('vendas'))

@app.route('/criar_produto', methods=['POST'])
def criar_produto():
    nome_produto = request.form['nome']
    produto_existente = Produto.query.filter(func.lower(Produto.nome) == func.lower(nome_produto)).first()
    if produto_existente:
        flash('Erro: Produto já existe!')
        return redirect(url_for('estoque'))
    valor_venda = limpar_float(request.form.get('valor_venda'))
    ativo = True if request.form.get('ativo') else False
    novo = Produto(nome=nome_produto, categoria=request.form['categoria'], marca=request.form['marca'], compatibilidade=request.form['compatibilidade'], quantidade=0, minimo=int(request.form['minimo'] or 5), valor_pago=0.0, valor_venda=valor_venda, observacao=request.form['observacao'], ativo=ativo)
    db.session.add(novo)
    db.session.commit()
    return redirect(url_for('estoque'))

@app.route('/editar_produto', methods=['POST'])
def editar_produto():
    id_prod = request.form['produto_id']
    produto = Produto.query.get(id_prod)
    if produto:
        produto.nome = request.form['nome']
        produto.marca = request.form['marca']
        produto.categoria = request.form['categoria']
        produto.compatibilidade = request.form['compatibilidade']
        produto.minimo = int(request.form['minimo'])
        produto.valor_venda = limpar_float(request.form['valor_venda'])
        produto.observacao = request.form['observacao']
        produto.ativo = True if request.form.get('ativo') else False
        db.session.commit()
    return redirect(url_for('estoque'))

@app.route('/excluir_produto/<int:id>')
def excluir_produto(id):
    p = Produto.query.get(id)
    if p and p.quantidade == 0:
        Movimentacao.query.filter_by(produto_id=id).delete()
        db.session.delete(p)
        db.session.commit()
    return redirect(url_for('estoque'))

@app.route('/ajustar_estoque', methods=['POST'])
def ajustar_estoque():
    produto_id = int(request.form['produto_id'])
    tipo = request.form['tipo_ajuste']
    qtd = int(request.form['quantidade'])
    obs = request.form.get('observacao_ajuste')
    produto = Produto.query.get(produto_id)
    if tipo == 'Entrada':
        custo = limpar_float(request.form.get('valor_pago'))
        if custo <= 0:
            flash('ERRO: Para entrada de estoque, o Valor Unitário é obrigatório e deve ser maior que zero.')
            return redirect(url_for('estoque'))
        total = produto.quantidade * produto.valor_pago + qtd * custo
        produto.quantidade += qtd
        if produto.quantidade > 0: produto.valor_pago = total / produto.quantidade
        db.session.add(Movimentacao(produto_id=produto.id, tipo='Entrada', categoria_movimento=request.form.get('origem_tipo'), numero_documento=request.form.get('numero_documento'), quantidade=qtd, valor_unitario_entrada=custo, destino_origem=request.form.get('fornecedor'), observacao=obs))
    elif tipo == 'Saida':
        if produto.quantidade >= qtd:
            produto.quantidade -= qtd
            db.session.add(Movimentacao(produto_id=produto.id, tipo='Ajuste_Saida', categoria_movimento='Ajuste Manual', quantidade=qtd, destino_origem='Ajuste', observacao=obs))
        else:
            flash('Erro: Estoque insuficiente.')
            return redirect(url_for('estoque'))
    db.session.commit()
    return redirect(url_for('estoque'))

@app.route('/editar_entrada', methods=['POST'])
def editar_entrada():
    mov_id = request.form.get('movimentacao_id')
    novo_valor = limpar_float(request.form.get('novo_valor'))
    nova_qtd = int(request.form.get('nova_qtd'))
    mov = Movimentacao.query.get(mov_id)
    if not mov or mov.tipo != 'Entrada': return redirect(url_for('estoque'))
    produto = Produto.query.get(mov.produto_id)
    custo_total_atual = produto.quantidade * produto.valor_pago
    custo_total_sem_mov = custo_total_atual - (mov.quantidade * mov.valor_unitario_entrada)
    qtd_sem_mov = produto.quantidade - mov.quantidade
    nova_qtd_estoque = qtd_sem_mov + nova_qtd
    novo_custo_total = custo_total_sem_mov + (nova_qtd * novo_valor)
    if nova_qtd_estoque > 0: produto.valor_pago = novo_custo_total / nova_qtd_estoque
    else: produto.valor_pago = 0.0
    produto.quantidade = nova_qtd_estoque
    mov.quantidade = nova_qtd
    mov.valor_unitario_entrada = novo_valor
    db.session.commit()
    return redirect(url_for('estoque'))

@app.route('/gerar_pedido_saida', methods=['POST'])
def gerar_pedido_saida():
    cliente_id = int(request.form['cliente_id'])
    observacao = request.form.get('observacao')
    impressora = request.form.get('impressora')
    config = Configuracao.query.first()
    novo_numero = config.ultimo_pedido_id + 1
    config.ultimo_pedido_id = novo_numero
    pedido = PedidoSaida(numero_pedido=novo_numero, cliente_id=cliente_id, observacao=observacao, impressora=impressora, status='Ativo')
    db.session.add(pedido)
    produtos_ids = request.form.getlist('produtos[]')
    quantidades = request.form.getlist('quantidades[]')
    for p_id, qtd in zip(produtos_ids, quantidades):
        if not p_id: continue
        qtd = int(qtd)
        produto = Produto.query.get(int(p_id))
        if produto and produto.quantidade >= qtd:
            produto.quantidade -= qtd
            db.session.add(ItemPedido(pedido=pedido, produto=produto, quantidade=qtd))
            db.session.add(Movimentacao(produto_id=produto.id, tipo='Saida_Locacao', categoria_movimento='Pedido Saída', numero_documento=str(novo_numero), quantidade=qtd, destino_origem=pedido.cliente.nome, observacao=f'Pedido #{novo_numero} - {impressora}', pedido_id=pedido.id))
        else:
            db.session.rollback()
            flash(f'Estoque insuficiente: {produto.nome}')
            return redirect(url_for('saida_locacao'))
    db.session.commit()
    return redirect(url_for('saida_locacao'))

@app.route('/get_pedido_json/<int:id>')
def get_pedido_json(id):
    pedido = PedidoSaida.query.get_or_404(id)
    itens = [{'produto_id': i.produto_id, 'nome_produto': i.produto.nome, 'quantidade': i.quantidade} for i in pedido.itens]
    return jsonify({'id': pedido.id, 'cliente_id': pedido.cliente_id, 'data': pedido.data.strftime('%Y-%m-%d'), 'impressora': pedido.impressora, 'observacao': pedido.observacao, 'itens': itens})

@app.route('/salvar_edicao_pedido', methods=['POST'])
def salvar_edicao_pedido():
    try:
        pedido_id = request.form.get('pedido_id')
        pedido = PedidoSaida.query.get(pedido_id)
        if not pedido: return redirect(url_for('saida_locacao'))
        for item in pedido.itens:
            prod = Produto.query.get(item.produto_id)
            prod.quantidade += item.quantidade
        ItemPedido.query.filter_by(pedido_id=pedido.id).delete()
        Movimentacao.query.filter_by(pedido_id=pedido.id).delete()
        pedido.cliente_id = int(request.form['cliente_id'])
        pedido.impressora = request.form['impressora']
        pedido.observacao = request.form['observacao']
        pedido.data = datetime.strptime(request.form['data'], '%Y-%m-%d')
        p_ids = request.form.getlist('produtos[]')
        qtds = request.form.getlist('quantidades[]')
        for p_id, qtd in zip(p_ids, qtds):
            if not p_id: continue
            qtd = int(qtd)
            prod = Produto.query.get(int(p_id))
            if prod.quantidade >= qtd:
                prod.quantidade -= qtd
                db.session.add(ItemPedido(pedido=pedido, produto=prod, quantidade=qtd))
                db.session.add(Movimentacao(produto_id=prod.id, tipo='Saida_Locacao', categoria_movimento='Pedido Editado', numero_documento=str(pedido.numero_pedido), quantidade=qtd, destino_origem=pedido.cliente.nome, observacao=f"Edição Pedido #{pedido.numero_pedido}", pedido_id=pedido.id))
            else:
                db.session.rollback()
                return redirect(url_for('saida_locacao'))
        db.session.commit()
    except Exception as e: db.session.rollback()
    return redirect(url_for('saida_locacao'))

@app.route('/salvar_cliente', methods=['POST'])
def salvar_cliente():
    c_id = request.form.get('cliente_id')
    dados = {k: request.form[k] for k in ['nome', 'tipo_pessoa', 'documento', 'endereco', 'telefone', 'email', 'data_fechamento', 'observacao']}
    if c_id:
        c = Cliente.query.get(int(c_id))
        for k, v in dados.items(): setattr(c, k, v)
    else: db.session.add(Cliente(**dados))
    db.session.commit()
    return redirect(url_for('clientes'))

@app.route('/excluir_cliente/<int:id>')
def excluir_cliente(id):
    c = Cliente.query.get(id)
    if c and not c.pedidos: db.session.delete(c); db.session.commit()
    return redirect(url_for('clientes'))

@app.route('/imprimir_pedido/<int:id>')
def imprimir_pedido(id):
    p = PedidoSaida.query.get_or_404(id)
    return render_template('imprimir_pedido.html', pedido=p)

@app.route('/impressoras')
def impressoras():
    busca = request.args.get('busca')
    status = request.args.get('status')
    cliente_id = request.args.get('cliente_id')
    query = Impressora.query
    if busca:
        term = f"%{busca}%"
        query = query.filter((Impressora.marca.like(term)) | (Impressora.modelo.like(term)) | (Impressora.serial.like(term)) | (Impressora.mlt.like(term)) | (Impressora.localizacao.like(term)))
    if status and status != 'Todas': query = query.filter(Impressora.status == status)
    if cliente_id and cliente_id != 'Todos':
        cliente = Cliente.query.get(int(cliente_id))
        if cliente: query = query.filter(Impressora.localizacao == cliente.nome)
    impressoras = query.order_by(Impressora.modelo).all()
    clientes = Cliente.query.order_by(Cliente.nome).all()
    ultimas_movimentacoes = MovimentacaoImpressora.query.order_by(MovimentacaoImpressora.data.desc()).limit(20).all()
    total_geral = Impressora.query.count()
    disponiveis = Impressora.query.filter_by(status='Disponível').count()
    locadas = Impressora.query.filter_by(status='Locada').count()
    manutencao = Impressora.query.filter_by(status='Manutenção').count()
    return render_template('impressoras.html', impressoras=impressoras, clientes=clientes, ultimas_movimentacoes=ultimas_movimentacoes, total=total_geral, disponiveis=disponiveis, locadas=locadas, manutencao=manutencao, request=request)

@app.route('/api/manutencoes_impressora/<int:id>')
def api_manutencoes_impressora(id):
    manutencoes = Manutencao.query.filter_by(impressora_id=id).order_by(Manutencao.numero_ordem.desc()).all()
    lista = []
    for m in manutencoes:
        lista.append({'id': m.id, 'numero': m.numero_ordem, 'status': m.status_atual, 'inicio': m.data_inicio.strftime('%d/%m/%Y'), 'motivo': m.motivo_inicial})
    return jsonify(lista)

@app.route('/movimentar_impressora', methods=['POST'])
def movimentar_impressora():
    try:
        impressora_id = request.form.get('impressora_id')
        tipo_movimentacao = request.form.get('tipo_movimentacao')
        cliente_id = request.form.get('cliente_id')
        contador_atual = limpar_int(request.form.get('contador_atual'))
        observacao = request.form.get('observacao')
        imp = Impressora.query.get_or_404(impressora_id)
        
        # --- LÓGICA DE MANUTENÇÃO (AUTOMATIZAÇÃO DE O.S.) ---
        if imp.status == 'Manutenção' and tipo_movimentacao != 'Manutenção':
            os_aberta = Manutencao.query.filter_by(impressora_id=imp.id, status_atual='Aberta').order_by(Manutencao.data_inicio.desc()).first()
            if os_aberta:
                os_aberta.status_atual = 'Fechada'
                os_aberta.data_fim = datetime.now()
                log_fechamento = LogManutencao(manutencao_id=os_aberta.id, impressora_id=imp.id, titulo="Encerramento Automático", observacao=f"Impressora movida para {tipo_movimentacao}. Obs: {observacao}")
                db.session.add(log_fechamento)

        if tipo_movimentacao == 'Manutenção':
            ultima_os = Manutencao.query.order_by(Manutencao.numero_ordem.desc()).first()
            proximo_numero = (ultima_os.numero_ordem + 1) if (ultima_os and ultima_os.numero_ordem) else 1
            nova_os = Manutencao(impressora_id=imp.id, numero_ordem=proximo_numero, data_inicio=datetime.now(), status_atual='Aberta', motivo_inicial=observacao or "Manutenção Solicitada")
            db.session.add(nova_os)
            db.session.flush() 
            db.session.add(LogManutencao(manutencao_id=nova_os.id, impressora_id=imp.id, titulo="Abertura O.S.", observacao=f"O.S. #{proximo_numero} aberta automaticamente."))

        status_novo = 'Disponível'
        local_novo = 'Estoque'
        if tipo_movimentacao == 'Locação':
            status_novo = 'Locada'
            if cliente_id:
                cliente = Cliente.query.get(cliente_id)
                local_novo = cliente.nome if cliente else 'Cliente Indefinido'
        elif tipo_movimentacao == 'Manutenção':
            status_novo = 'Manutenção'
            local_novo = 'Assistência Técnica'
            
        nova_mov = MovimentacaoImpressora(impressora_id=imp.id, tipo=tipo_movimentacao, data=datetime.now(), origem=imp.localizacao, destino=local_novo, contador_momento=contador_atual, observacao=observacao)
        imp.status = status_novo
        imp.localizacao = local_novo
        imp.contador = contador_atual
        db.session.add(nova_mov)
        db.session.commit()
        flash(f'Movimentação realizada: {imp.modelo} foi para {local_novo}.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO MOVIMENTACAO: {e}")
        flash(f'Erro ao movimentar: {e}', 'danger')
    return redirect(url_for('impressoras'))

@app.route('/adicionar_log_manutencao', methods=['POST'])
def adicionar_log_manutencao():
    try:
        manutencao_id = request.form.get('manutencao_id')
        impressora_id = request.form.get('impressora_id') 
        titulo = request.form.get('status_detalhe')
        obs = request.form.get('observacao')
        
        if (not manutencao_id or manutencao_id == "") and impressora_id:
            os_aberta = Manutencao.query.filter_by(impressora_id=int(impressora_id), status_atual='Aberta').order_by(Manutencao.data_inicio.desc()).first()
            if os_aberta: manutencao_id = os_aberta.id
        
        if manutencao_id:
            log = LogManutencao(manutencao_id=int(manutencao_id), impressora_id=int(impressora_id) if impressora_id else None, titulo=titulo, observacao=obs)
            db.session.add(log)
            db.session.commit()
            flash('Histórico atualizado na O.S. com sucesso.', 'success')
        else: flash('Erro: Nenhuma O.S. Aberta encontrada.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}', 'danger')
    return redirect(url_for('impressoras'))

@app.route('/api/impressoras_cliente/<int:cliente_id>')
def api_impressoras_cliente(cliente_id):
    cliente = Cliente.query.get(cliente_id)
    if not cliente: return jsonify([])
    impressoras = Impressora.query.filter_by(status='Locada', localizacao=cliente.nome).all()
    lista = []
    for imp in impressoras:
        mlt_texto = imp.mlt if imp.mlt else "S/M"
        display = f"{imp.modelo} | S/N: {imp.serial} | MLT: {mlt_texto}"
        lista.append({'id': imp.id, 'modelo': imp.modelo, 'serial': imp.serial, 'mlt': imp.mlt, 'texto_display': display})
    return jsonify(lista)

@app.route('/fornecedores')
def fornecedores():
    active_tab = request.args.get('tab', 'contatos')
    fornecedores_lista = Fornecedor.query.order_by(Fornecedor.nome).all()
    produtos_lista = Produto.query.order_by(Produto.nome).all()
    pedidos_lista = PedidoCompra.query.order_by(PedidoCompra.data_emissao.desc()).all()
    return render_template('fornecedores.html', fornecedores=fornecedores_lista, produtos=produtos_lista, pedidos=pedidos_lista, hoje=datetime.now(), active_tab=active_tab)

# ... [Bloco de rotas CRUD fornecedores e compras mantido igual] ...
@app.route('/criar_fornecedor', methods=['POST'])
def criar_fornecedor():
    try:
        novo = Fornecedor(nome=request.form['nome'], email=request.form['email'], telefone=request.form['telefone'], observacao=request.form['observacao'])
        db.session.add(novo)
        db.session.commit()
        flash('Fornecedor cadastrado.')
    except Exception as e: db.session.rollback(); flash(f'Erro: {e}')
    return redirect(url_for('fornecedores'))

@app.route('/editar_fornecedor', methods=['POST'])
def editar_fornecedor():
    try:
        f = Fornecedor.query.get(request.form['fornecedor_id'])
        if f:
            f.nome = request.form['nome']; f.email = request.form['email']; f.telefone = request.form['telefone']; f.observacao = request.form['observacao']
            db.session.commit(); flash('Fornecedor atualizado.')
    except Exception as e: db.session.rollback(); flash(f'Erro: {e}')
    return redirect(url_for('fornecedores'))

@app.route('/excluir_fornecedor/<int:id>')
def excluir_fornecedor(id):
    f = Fornecedor.query.get(id)
    if f: db.session.delete(f); db.session.commit()
    return redirect(url_for('fornecedores'))

@app.route('/criar_pedido_compra', methods=['POST'])
def criar_pedido_compra():
    try:
        data_emissao = datetime.strptime(request.form['data_emissao'], '%Y-%m-%d')
        data_entrega = datetime.strptime(request.form['data_entrega'], '%Y-%m-%d') if request.form['data_entrega'] else None
        valor = limpar_float(request.form['valor_total'])
        novo = PedidoCompra(fornecedor_id=int(request.form['fornecedor_id']), valor_total=valor, prazo_pagamento=request.form['prazo_pagamento'], data_emissao=data_emissao, data_entrega_prevista=data_entrega)
        db.session.add(novo)
        db.session.commit()
        flash('Pedido de compra registrado.')
    except Exception as e: db.session.rollback(); flash(f'Erro: {e}')
    return redirect(url_for('fornecedores'))

@app.route('/toggle_pedido_entregue/<int:id>')
def toggle_pedido_entregue(id):
    pedido = PedidoCompra.query.get(id)
    if pedido: pedido.status = 'Entregue' if pedido.status != 'Entregue' else 'Pendente'; db.session.commit()
    return redirect(url_for('fornecedores'))

@app.route('/salvar_pedido_compra', methods=['POST'])
def salvar_pedido_compra():
    try:
        pedido_id = request.form.get('pedido_id')
        fornecedor_id = int(request.form['fornecedor_id'])
        prazo = request.form['prazo_pagamento']
        data_emissao = datetime.strptime(request.form['data_emissao'], '%Y-%m-%d')
        data_entrega = datetime.strptime(request.form['data_entrega'], '%Y-%m-%d') if request.form['data_entrega'] else None
        frete = float(request.form['frete'] or 0)
        obs = request.form['observacao']
        prod_ids = request.form.getlist('item_produto_id')
        descs = request.form.getlist('item_desc')
        qtds = request.form.getlist('item_qtd')
        vals = request.form.getlist('item_valor')
        
        if pedido_id:
            pedido = PedidoCompra.query.get(pedido_id)
            for item in pedido.itens: db.session.delete(item)
        else:
            pedido = PedidoCompra()
            db.session.add(pedido)
        
        pedido.fornecedor_id = fornecedor_id
        pedido.prazo_pagamento = prazo
        pedido.data_emissao = data_emissao
        pedido.data_entrega_prevista = data_entrega
        pedido.frete = frete
        pedido.observacao = obs
        if not pedido.status: pedido.status = 'Pendente'
        db.session.flush()
        
        total_itens = 0
        for i in range(len(descs)):
            qtd = int(qtds[i] or 0)
            unit = float(vals[i] or 0)
            total_linha = qtd * unit
            total_itens += total_linha
            p_id = prod_ids[i] if prod_ids[i] else None
            novo_item = ItemPedidoCompra(pedido_id=pedido.id, produto_id=p_id, descricao=descs[i], quantidade=qtd, valor_unitario=unit, valor_total=total_linha)
            db.session.add(novo_item)
        pedido.valor_itens = total_itens
        pedido.valor_total = total_itens + frete
        db.session.commit()
        flash('Pedido salvo com sucesso.')
    except Exception as e: db.session.rollback(); flash(f'Erro ao salvar pedido: {e}')
    return redirect(url_for('fornecedores', tab='pedidos'))

@app.route('/cancelar_pedido_compra/<int:id>')
def cancelar_pedido_compra(id):
    pedido = PedidoCompra.query.get(id)
    if pedido: pedido.status = 'Cancelado'; db.session.commit(); flash('Pedido cancelado.')
    return redirect(url_for('fornecedores', tab='pedidos'))

@app.route('/entregar_pedido_compra/<int:id>')
def entregar_pedido_compra(id):
    pedido = PedidoCompra.query.get(id)
    if pedido: pedido.status = 'Entregue'; db.session.commit(); flash('Pedido marcado como Entregue.')
    return redirect(url_for('fornecedores', tab='pedidos'))

@app.route('/api/pedido_compra/<int:id>')
def api_pedido_compra(id):
    p = PedidoCompra.query.get(id)
    itens = []
    for i in p.itens:
        itens.append({'produto_id': i.produto_id or '', 'descricao': i.descricao, 'quantidade': i.quantidade, 'valor_unitario': i.valor_unitario, 'valor_total': i.valor_total})
    data = {'id': p.id, 'fornecedor_id': p.fornecedor_id, 'fornecedor_nome': p.fornecedor.nome, 'data_emissao': p.data_emissao.strftime('%Y-%m-%d'), 'data_entrega': p.data_entrega_prevista.strftime('%Y-%m-%d') if p.data_entrega_prevista else '', 'prazo': p.prazo_pagamento, 'frete': p.frete, 'valor_itens': p.valor_itens, 'valor_total': p.valor_total, 'observacao': p.observacao, 'status': p.status, 'itens': itens}
    return jsonify(data)

@app.route('/editar_movimentacao_historico', methods=['POST'])
def editar_movimentacao_historico():
    try:
        mov_id = request.form['mov_id']
        mov = MovimentacaoImpressora.query.get(mov_id)
        if mov:
            mov.data = datetime.strptime(request.form['data'], '%Y-%m-%d %H:%M')
            mov.tipo = request.form['tipo']
            mov.origem = request.form['origem']
            mov.destino = request.form['destino']
            mov.contador_momento = int(request.form['contador'])
            mov.observacao = request.form['observacao']
            db.session.commit()
            flash('Histórico atualizado.')
    except Exception as e: db.session.rollback(); flash(f'Erro ao editar: {e}')
    return redirect(url_for('impressoras'))

@app.route('/api/historico_impressora/<int:id>')
def api_historico_impressora(id):
    movs = MovimentacaoImpressora.query.filter_by(impressora_id=id).all()
    logs = LogManutencao.query.filter_by(impressora_id=id).all()
    lista_unificada = []
    for m in movs:
        lista_unificada.append({'categoria': 'movimentacao', 'data_obj': m.data, 'data': m.data.strftime('%d/%m/%Y %H:%M'), 'tipo': m.tipo, 'origem': m.origem, 'destino': m.destino, 'contador': m.contador_momento, 'observacao': m.observacao})
    for l in logs:
        lista_unificada.append({'categoria': 'manutencao', 'data_obj': l.data, 'data': l.data.strftime('%d/%m/%Y %H:%M'), 'titulo': l.titulo, 'observacao': l.observacao})
    lista_unificada.sort(key=lambda x: x['data_obj'], reverse=True)
    return jsonify(lista_unificada)

# --- SUBSTITUIR NO app.py ---

@app.route('/criar_impressora', methods=['POST'])
def criar_impressora():
    try:
        marca = request.form['marca']
        modelo_input = request.form['modelo'].strip() # Ex: "M420dn"
        
        # Lógica: Se o usuário digitou "Brother M420dn", mantemos. 
        # Se digitou só "M420dn", viramos "Brother M420dn".
        if modelo_input.lower().startswith(marca.lower()):
            modelo_final = modelo_input # Já estava completo
        else:
            modelo_final = f"{marca} {modelo_input}"

        nova = Impressora(
            marca=marca, 
            modelo=modelo_final, # Salva o nome completo
            serial=request.form['serial'],
            mlt=request.form['mlt'],
            contador=int(request.form['contador'] or 0),
            status='Disponível', 
            localizacao='Estoque',
            observacao=request.form['observacao']
        )
        db.session.add(nova)
        db.session.flush() 
        db.session.add(MovimentacaoImpressora(impressora_id=nova.id, tipo='Cadastro', origem='-', destino='Estoque', contador_momento=nova.contador, observacao='Cadastro inicial'))
        db.session.commit()
        flash('Impressora cadastrada com sucesso.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('ERRO: Já existe uma impressora com este Serial!', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao cadastrar: {str(e)}', 'danger')
    return redirect(url_for('impressoras'))


@app.route('/editar_impressora', methods=['POST'])
def editar_impressora():
    try:
        # Pega o ID
        imp_id = request.form.get('impressora_id')
        impressora = Impressora.query.get(imp_id)
        
        if not impressora:
            flash('Impressora não encontrada.', 'danger')
            return redirect(url_for('impressoras'))

        # Atualiza os dados básicos
        impressora.marca = request.form.get('marca')
        impressora.modelo = request.form.get('modelo')
        impressora.serial = request.form.get('serial')
        impressora.mlt = request.form.get('mlt')
        impressora.observacao = request.form.get('observacao')
        
        # --- AQUI ESTÁ A CORREÇÃO ---
        # Verifica se veio um valor de contador e salva
        novo_contador = request.form.get('contador')
        if novo_contador is not None and novo_contador != '':
            impressora.contador = int(novo_contador)
        # ----------------------------

        db.session.commit()
        flash('Dados da impressora atualizados com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao editar impressora: {e}")
        flash('Erro ao atualizar impressora.', 'danger')

    return redirect(url_for('impressoras'))



@app.route('/excluir_impressora/<int:id>')
def excluir_impressora(id):
    imp = Impressora.query.get(id)
    if imp: db.session.delete(imp); db.session.commit()
    return redirect(url_for('impressoras'))

@app.route('/api/historico_completo/<int:id>')
def api_historico_completo(id):
    try:
        impressora = Impressora.query.get_or_404(id)
        movs = MovimentacaoImpressora.query.filter_by(impressora_id=id).order_by(MovimentacaoImpressora.data.desc()).all()
        manutencoes = Manutencao.query.filter_by(impressora_id=id).order_by(Manutencao.numero_ordem.desc()).all()
        insumos_lista = []
        if impressora.serial:
            pedidos_vinculados = PedidoSaida.query.filter(PedidoSaida.impressora.ilike(f'%{impressora.serial}%'), PedidoSaida.status != 'Cancelado').all()
            ids_pedidos = [p.id for p in pedidos_vinculados]
            if ids_pedidos:
                movs_insumos = Movimentacao.query.filter(Movimentacao.pedido_id.in_(ids_pedidos), Movimentacao.tipo == 'Saida_Locacao', Movimentacao.status != 'Cancelado').order_by(Movimentacao.data.desc()).all()
                for m in movs_insumos:
                    insumos_lista.append({'data': m.data.strftime('%d/%m/%Y %H:%M'), 'produto': m.produto.nome, 'marca': m.produto.marca, 'qtd': m.quantidade, 'pedido': m.numero_documento})
        lista_movs = []
        for m in movs:
            lista_movs.append({'data': m.data.strftime('%d/%m/%Y %H:%M'), 'tipo': m.tipo, 'origem': m.origem, 'destino': m.destino, 'contador': m.contador_momento, 'obs': m.observacao})
        lista_manut = []
        for m in manutencoes:
            logs = []
            for l in m.logs: logs.append({'data': l.data.strftime('%d/%m %H:%M'), 'titulo': l.titulo, 'obs': l.observacao})
            lista_manut.append({'numero': m.numero_ordem, 'inicio': m.data_inicio.strftime('%d/%m/%Y'), 'fim': m.data_fim.strftime('%d/%m/%Y') if m.data_fim else 'Em andamento', 'status': m.status_atual, 'motivo': m.motivo_inicial, 'logs': logs})
        return jsonify({'movimentacoes': lista_movs, 'manutencoes': lista_manut, 'insumos': insumos_lista})
    except Exception as e: return jsonify({'movimentacoes': [], 'manutencoes': [], 'insumos': []}), 500

@app.route('/logs')
def logs():
    logs_sistema = SystemLog.query.order_by(SystemLog.data.desc()).limit(100).all()
    return render_template('logs.html', logs=logs_sistema)

@app.route('/salvar_configuracoes', methods=['POST'])
def salvar_configuracoes():
    c = Configuracao.query.first()
    c.margem_atencao_pct = int(request.form['margem_atencao_pct'])
    c.dias_alerta_vencimento = int(request.form['dias_alerta_vencimento'])
    db.session.commit()
    return redirect(url_for('configuracoes'))

@app.route('/configuracoes')
def configuracoes(): return render_template('configuracoes.html')

# --- ROTAS DE CONTRATOS ---

@app.route('/contratos')
def contratos():
    impressoras_todas = Impressora.query.filter(or_(Impressora.status == 'Disponível', Impressora.status == 'Locada')).order_by(Impressora.localizacao, Impressora.modelo).all()
    contratos_ativos = Contrato.query.filter_by(status='Ativo').order_by(Contrato.valor_mensal_total.desc()).all()
    contratos_cancelados = Contrato.query.filter_by(status='Cancelado').order_by(Contrato.data_fim.desc()).all()
    clientes = Cliente.query.order_by(Cliente.nome).all()
    total_ativos = len(contratos_ativos)
    valor_total_mensal = sum(c.valor_mensal_total for c in contratos_ativos)
    impressoras_locadas = Impressora.query.filter_by(status='Locada').count()
    return render_template('contratos.html', contratos_ativos=contratos_ativos, contratos_cancelados=contratos_cancelados, clientes=clientes, impressoras_todas=impressoras_todas, total_ativos=total_ativos, valor_total_mensal=valor_total_mensal, impressoras_locadas=impressoras_locadas, hoje=datetime.now().date())

@app.route('/criar_contrato', methods=['POST'])
def criar_contrato():
    try:
        cliente_id = request.form.get('cliente_id')
        if not cliente_id:
            flash('Erro: Selecione um cliente.', 'danger')
            return redirect(url_for('contratos'))
        cliente_obj = Cliente.query.get(int(cliente_id))
        nome_arquivo = None
        file = request.files.get('arquivo_contrato')
        if file and file.filename != '':
            timestamp = datetime.now().strftime('%Y%m%d%H%M')
            filename = secure_filename(f"contrato_cli{cliente_id}_{timestamp}.pdf")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            nome_arquivo = filename
        novo_contrato = Contrato(cliente_id=int(cliente_id), numero_contrato=request.form.get('numero_contrato'), dia_vencimento=limpar_int(request.form.get('dia_vencimento')), data_inicio=datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date(), data_fim=datetime.strptime(request.form.get('data_fim'), '%Y-%m-%d').date(), status='Ativo', arquivo_pdf=nome_arquivo, valor_mensal_total=0.0)
        db.session.add(novo_contrato)
        db.session.flush()
        
        nomes = request.form.getlist('custo_nome[]')
        tipos = request.form.getlist('custo_tipo[]')
        pgs = request.form.getlist('custo_paginas[]')
        vals = request.form.getlist('custo_valor[]')
        excs = request.form.getlist('custo_excedente[]')
        mapa_custos = {} 
        if nomes:
            for i in range(len(nomes)):
                val_franquia = limpar_float(vals[i])
                nova_franquia = ContratoFranquia(contrato_id=novo_contrato.id, nome=nomes[i], tipo=tipos[i], franquia_paginas=limpar_int(pgs[i]), valor_franquia=val_franquia, valor_excedente=limpar_float(excs[i]))
                db.session.add(nova_franquia)
                db.session.flush()
                mapa_custos[nomes[i]] = {'id': nova_franquia.id, 'tipo': tipos[i], 'valor_base': val_franquia}
        
        imps = request.form.getlist('impressora_id[]')
        custos_vinc = request.form.getlist('custo_vinculado[]')
        vals_loc_manuais = request.form.getlist('valor_locacao[]')
        contagem_por_custo = {}
        for nome_vinculo in custos_vinc:
            if nome_vinculo and nome_vinculo in mapa_custos: contagem_por_custo[nome_vinculo] = contagem_por_custo.get(nome_vinculo, 0) + 1
        
        total_acumulado = 0.0
        if imps:
            for i in range(len(imps)):
                if not imps[i]: continue
                imp_id = int(imps[i])
                nome_vinc = custos_vinc[i]
                valor_final_item = 0.0
                franquia_db_id = None
                if nome_vinc and nome_vinc in mapa_custos:
                    dados_custo = mapa_custos[nome_vinc]
                    franquia_db_id = dados_custo['id']
                    if dados_custo['tipo'] == 'Compartilhada': qtd = contagem_por_custo.get(nome_vinc, 1); valor_final_item = dados_custo['valor_base'] / qtd
                    else: valor_final_item = dados_custo['valor_base']
                else: valor_final_item = limpar_float(vals_loc_manuais[i])
                total_acumulado += valor_final_item
                novo_item = ContratoItem(contrato_id=novo_contrato.id, impressora_id=imp_id, franquia_id=franquia_db_id, valor_locacao_unitario=valor_final_item)
                imp = Impressora.query.get(imp_id)
                if imp:
                    imp.status = 'Locada'
                    imp.localizacao = cliente_obj.nome 
                    db.session.add(MovimentacaoImpressora(impressora_id=imp.id, tipo='Locação', origem='Estoque', destino=cliente_obj.nome, contador_momento=imp.contador, observacao=f"Novo Contrato {novo_contrato.numero_contrato}"))
                    mlt_texto = f"MLT: {imp.mlt}" if imp.mlt else "S/M"
                    registrar_hist_contrato(novo_contrato.id, "Inclusão Item", f"Inclusão de {imp.modelo} ({mlt_texto} | S/N: {imp.serial})")
                db.session.add(novo_item)
        
        novo_contrato.valor_mensal_total = total_acumulado
        registrar_hist_contrato(novo_contrato.id, "Criação", f"Contrato iniciado. Valor total: {currency_filter(total_acumulado)}")
        db.session.commit()
        flash(f'Contrato criado! Total: {currency_filter(total_acumulado)}', 'success')
    except Exception as e: db.session.rollback(); print(f"ERRO CRIAR: {e}"); flash(f'Erro: {str(e)}', 'danger')
    return redirect(url_for('contratos'))

# --- SUBSTITUIR A ROTA editar_contrato NO app.py ---

@app.route('/editar_contrato', methods=['POST'])
def editar_contrato():
    try:
        c_id = request.form.get('contrato_id')
        contrato = Contrato.query.get(c_id)
        if not contrato: return redirect(url_for('contratos'))

        # --- 1. PREPARAÇÃO E COMPARAÇÃO (ANTES DE APAGAR) ---
        valor_antigo = contrato.valor_mensal_total
        cliente_antigo_nome = contrato.cliente.nome
        
        # Mapeia quem estava no contrato antes: {id_impressora: ObjetoImpressora}
        imps_antes = {item.impressora.id: item.impressora for item in contrato.itens if item.impressora}
        ids_antes = set(imps_antes.keys())

        # Pega quem vai ficar no contrato agora
        imp_ids_form = request.form.getlist('impressora_id[]')
        ids_agora = set([int(x) for x in imp_ids_form if x])

        # Calcula as diferenças
        ids_remover = ids_antes - ids_agora  # Estavam e não estão mais (Devolver p/ Estoque)
        ids_adicionar = ids_agora - ids_antes # Não estavam e agora estão (Sair do Estoque p/ Cliente)
        ids_manter = ids_antes & ids_agora    # Continuam (Verificar se mudou cliente)

        # --- 2. ATUALIZAÇÃO DADOS BÁSICOS ---
        contrato.numero_contrato = request.form.get('numero_contrato')
        contrato.dia_vencimento = limpar_int(request.form.get('dia_vencimento'))
        contrato.data_inicio = datetime.strptime(request.form['data_inicio'], '%Y-%m-%d').date()
        contrato.data_fim = datetime.strptime(request.form['data_fim'], '%Y-%m-%d').date()
        
        novo_cliente_id = int(request.form.get('cliente_id'))
        cliente_mudou = (contrato.cliente_id != novo_cliente_id)
        
        if cliente_mudou:
            contrato.cliente_id = novo_cliente_id
            
        cliente_atual = Cliente.query.get(contrato.cliente_id) # Pega objeto atualizado

        # --- 3. PROCESSAR REMOÇÕES (Volta para Estoque) ---
        for imp_id in ids_remover:
            imp = imps_antes[imp_id]
            
            # Atualiza Status da Impressora
            imp.status = 'Disponível'
            imp.localizacao = 'Estoque'
            
            # LOG NA IMPRESSORA (MOVIMENTAÇÃO)
            db.session.add(MovimentacaoImpressora(
                impressora_id=imp.id,
                tipo='Estoque', # Tipo "Estoque" significa retorno
                origem=cliente_antigo_nome,
                destino='Estoque',
                contador_momento=imp.contador,
                observacao=f"Removida do Contrato {contrato.numero_contrato}"
            ))
            
            # Log no Contrato
            registrar_hist_contrato(contrato.id, "Remoção Item", f"Impressora {imp.modelo} (S/N: {imp.serial}) devolvida ao estoque.")

        # --- 4. LIMPEZA DOS ITENS DO CONTRATO (DB) ---
        # Removemos todos os vínculos da tabela 'contrato_item' para recriar limpo
        # (Mas os objetos Impressora já foram tratados acima ou serão abaixo)
        ContratoItem.query.filter_by(contrato_id=contrato.id).delete()
        ContratoFranquia.query.filter_by(contrato_id=contrato.id).delete()
        db.session.flush()

        # --- 5. RECRIAÇÃO: CUSTOS ---
        nomes = request.form.getlist('custo_nome[]')
        tipos = request.form.getlist('custo_tipo[]')
        pgs = request.form.getlist('custo_paginas[]')
        vals = request.form.getlist('custo_valor[]')
        excs = request.form.getlist('custo_excedente[]')
        
        mapa_custos = {} 
        if nomes:
            for i in range(len(nomes)):
                val_franquia = limpar_float(vals[i])
                nova_franquia = ContratoFranquia(
                    contrato_id=contrato.id,
                    nome=nomes[i],
                    tipo=tipos[i],
                    franquia_paginas=limpar_int(pgs[i]),
                    valor_franquia=val_franquia,
                    valor_excedente=limpar_float(excs[i])
                )
                db.session.add(nova_franquia)
                db.session.flush()
                mapa_custos[nomes[i]] = {
                    'id': nova_franquia.id,
                    'tipo': tipos[i],
                    'valor_base': val_franquia
                }

        # --- 6. RECRIAÇÃO: IMPRESSORAS (E MOVIMENTAÇÃO DE ENTRADA) ---
        custos_vinc = request.form.getlist('custo_vinculado[]')
        vals_loc = request.form.getlist('valor_locacao[]')
        
        # Contagem para Rateio
        contagem_por_custo = {}
        for nome_vinculo in custos_vinc:
            if nome_vinculo and nome_vinculo in mapa_custos:
                contagem_por_custo[nome_vinculo] = contagem_por_custo.get(nome_vinculo, 0) + 1

        total_acumulado = 0.0

        if imp_ids_form:
            for i, imp_id_str in enumerate(imp_ids_form):
                if not imp_id_str: continue
                imp_id = int(imp_id_str)
                nome_vinc = custos_vinc[i]
                
                # Calculo Valor
                valor_final_item = 0.0
                franquia_db_id = None
                
                if nome_vinc and nome_vinc in mapa_custos:
                    dados_custo = mapa_custos[nome_vinc]
                    franquia_db_id = dados_custo['id']
                    if dados_custo['tipo'] == 'Compartilhada':
                        qtd = contagem_por_custo.get(nome_vinc, 1)
                        valor_final_item = dados_custo['valor_base'] / qtd
                    else:
                        valor_final_item = dados_custo['valor_base']
                else:
                    valor_final_item = limpar_float(vals_loc[i])
                
                total_acumulado += valor_final_item

                # Cria Vínculo Contrato
                item = ContratoItem(
                    contrato_id=contrato.id,
                    impressora_id=imp_id,
                    franquia_id=franquia_db_id,
                    valor_locacao_unitario=valor_final_item
                )
                db.session.add(item)
                
                # --- TRATAMENTO DA IMPRESSORA (MOVIMENTAÇÃO) ---
                imp = Impressora.query.get(imp_id)
                if imp:
                    # Se for NOVA neste contrato (estava no estoque ou outro lugar)
                    if imp_id in ids_adicionar:
                        imp.status = 'Locada'
                        imp.localizacao = cliente_atual.nome
                        
                        # LOG NA IMPRESSORA
                        db.session.add(MovimentacaoImpressora(
                            impressora_id=imp.id, 
                            tipo='Locação', 
                            origem='Estoque', # Assumimos estoque, ou poderíamos pegar imp.localizacao anterior
                            destino=cliente_atual.nome, 
                            contador_momento=imp.contador, 
                            observacao=f"Inclusão no Contrato {contrato.numero_contrato}"
                        ))
                        
                        # Log no Contrato
                        mlt_texto = f"MLT: {imp.mlt}" if imp.mlt else "S/M"
                        registrar_hist_contrato(contrato.id, "Adição Item", f"Adicionado: {imp.modelo} ({mlt_texto} | S/N: {imp.serial})")

                    # Se já estava (MANTIDA), mas o cliente mudou (Transferência)
                    elif imp_id in ids_manter and cliente_mudou:
                        imp.localizacao = cliente_atual.nome
                        
                        # LOG NA IMPRESSORA
                        db.session.add(MovimentacaoImpressora(
                            impressora_id=imp.id, 
                            tipo='Locação', 
                            origem=cliente_antigo_nome, 
                            destino=cliente_atual.nome, 
                            contador_momento=imp.contador, 
                            observacao=f"Transferência de Titularidade (Contrato {contrato.numero_contrato})"
                        ))

        contrato.valor_mensal_total = total_acumulado
        
        # Log Financeiro se mudou valor
        if abs(valor_antigo - total_acumulado) > 0.01:
            registrar_hist_contrato(contrato.id, "Reajuste Financeiro", f"Valor alterado de {currency_filter(valor_antigo)} para {currency_filter(total_acumulado)}")
        
        # PDF
        file = request.files.get('arquivo_contrato')
        if file and allowed_file(file.filename):
            filename = secure_filename(f"Contrato_{contrato.id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            contrato.arquivo_pdf = filename

        db.session.commit()
        flash(f'Contrato atualizado! Novo Total: {currency_filter(total_acumulado)}', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"ERRO EDITAR: {e}")
        flash(f'Erro ao editar: {e}', 'danger')
        
    return redirect(url_for('contratos'))




# --- SUBSTITUIR A ROTA cancelar_contrato_route NO app.py ---

@app.route('/cancelar_contrato', methods=['POST'])
def cancelar_contrato_route():
    c_id = request.form.get('contrato_id')
    justificativa = request.form.get('justificativa')
    c = Contrato.query.get(c_id)
    if c:
        c.status = 'Cancelado'
        c.justificativa_cancelamento = justificativa
        c.data_fim = datetime.now().date()
        
        # Devolver todas as impressoras ao estoque e registrar no histórico delas
        for item in c.itens:
            imp = item.impressora
            if imp:
                imp.status = 'Disponível'
                imp.localizacao = 'Estoque'
                
                # LOG NA IMPRESSORA
                db.session.add(MovimentacaoImpressora(
                    impressora_id=imp.id, 
                    tipo='Estoque', 
                    origem=c.cliente.nome, 
                    destino='Estoque', 
                    contador_momento=imp.contador, 
                    observacao=f"Fim de Contrato: {justificativa}"
                ))
        
        # Log no Contrato
        registrar_hist_contrato(c.id, "Cancelamento", f"Contrato cancelado. Motivo: {justificativa}")
        
        db.session.commit()
        flash('Contrato cancelado e equipamentos devolvidos ao estoque.')
        
    return redirect(url_for('contratos'))


@app.route('/reativar_contrato/<int:id>')
def reativar_contrato(id):
    c = Contrato.query.get(id)
    if c:
        conflito = False
        for item in c.itens:
            if item.impressora.status == 'Locada': conflito = True; break
        if conflito: flash('Erro: Algumas impressoras já foram locadas. Crie um novo contrato.')
        else:
            c.status = 'Ativo'; c.justificativa_cancelamento = None
            for item in c.itens: item.impressora.status = 'Locada'; item.impressora.localizacao = c.cliente.nome
            db.session.commit(); flash('Contrato reativado.')
    return redirect(url_for('contratos'))

@app.route('/excluir_contrato/<int:id>')
def excluir_contrato(id):
    c = Contrato.query.get(id)
    if c:
        try:
            ContratoItem.query.filter_by(contrato_id=id).delete()
            ContratoFranquia.query.filter_by(contrato_id=id).delete()
            ContratoHistorico.query.filter_by(contrato_id=id).delete()
            db.session.delete(c)
            db.session.commit()
            flash('Contrato excluído definitivamente.', 'success')
        except Exception as e: db.session.rollback(); flash(f'Erro ao excluir: {e}', 'danger')
    return redirect(url_for('contratos'))

@app.route('/api/contrato_detalhes/<int:id>')
def api_contrato_detalhes(id):
    try:
        c = Contrato.query.get_or_404(id)
        d_inicio = c.data_inicio.isoformat() if c.data_inicio else ""
        d_inicio_br = c.data_inicio.strftime('%d/%m/%Y') if c.data_inicio else ""
        d_fim = c.data_fim.isoformat() if c.data_fim else ""
        d_fim_br = c.data_fim.strftime('%d/%m/%Y') if c.data_fim else ""
        lista_imp = []
        for item in c.itens:
            if item.impressora:
                nome_display = f"{item.impressora.modelo} ({item.impressora.serial})"
                mlt_display = item.impressora.mlt or "N/A"
                serial_display = item.impressora.serial or "N/A"
                imp_id = item.impressora.id
                status_real = item.impressora.status
            else:
                nome_display = "Impressora não vinculada"; mlt_display = "-"; serial_display = "-"; imp_id = ""; status_real = "Desconhecido"
            
            if item.franquia_pai:
                nome_custo = item.franquia_pai.nome
                tipo_franq = item.franquia_pai.tipo
                detalhes = f"{item.franquia_pai.franquia_paginas} pág"
            else: nome_custo = "Sem Custo Vinculado"; tipo_franq = "Individual"; detalhes = "-"
            
            alerta_tipo = None; alerta_msg = None; data_evento = None
            if status_real == 'Manutenção': alerta_tipo = 'warning'; alerta_msg = 'EM MANUTENÇÃO'
            elif status_real == 'Disponível':
                alerta_tipo = 'danger'; alerta_msg = 'DEVOLVIDA AO ESTOQUE'
                ult_mov = MovimentacaoImpressora.query.filter_by(impressora_id=item.impressora.id, destino='Estoque').order_by(MovimentacaoImpressora.data.desc()).first()
                if ult_mov: data_evento = ult_mov.data.strftime('%d/%m/%Y')

            lista_imp.append({'id': item.id, 'impressora_id': imp_id, 'modelo': item.impressora.modelo if item.impressora else "Desc.", 'serial': serial_display, 'mlt': mlt_display, 'valor': item.valor_locacao_unitario, 'custo_nome': nome_custo, 'tipo_franquia': tipo_franq, 'detalhes_franquia': detalhes, 'alerta_tipo': alerta_tipo, 'alerta_msg': alerta_msg, 'data_evento': data_evento})
        
        custos_list = []
        for f in c.franquias: custos_list.append({'id': f.id, 'nome': f.nome, 'tipo': f.tipo, 'paginas': f.franquia_paginas, 'valor': f.valor_franquia, 'excedente': f.valor_excedente})
        
        dados = {'id': c.id, 'cliente_id': c.cliente_id, 'numero': c.numero_contrato, 'dia_vencimento': c.dia_vencimento, 'cliente_nome': c.cliente.nome if c.cliente else "Cliente não encontrado", 'valor_mensal': c.valor_mensal_total, 'data_inicio': d_inicio, 'data_inicio_br': d_inicio_br, 'data_fim': d_fim, 'data_fim_br': d_fim_br, 'status': c.status, 'pdf_url': url_for('static', filename=f'uploads/contratos/{c.arquivo_pdf}') if c.arquivo_pdf else None, 'custos': custos_list, 'impressoras': lista_imp}
        return jsonify(dados)
    except Exception as e: print(f"ERRO API DETALHES: {e}"); traceback.print_exc(); return jsonify({'erro': str(e)}), 500

@app.route('/api/contrato_historico_log/<int:id>')
def api_contrato_historico_log(id):
    logs = ContratoHistorico.query.filter_by(contrato_id=id).order_by(ContratoHistorico.data.desc()).all()
    data = []
    for log in logs: data.append({'data': log.data.strftime('%d/%m/%Y %H:%M'), 'acao': log.acao, 'detalhes': log.detalhes, 'usuario': log.usuario})
    return jsonify(data)

@app.route('/imprimir_contrato/<int:id>')
def imprimir_contrato_view(id):
    contrato = Contrato.query.get_or_404(id)
    dados_itens = []
    for item in contrato.itens:
        ultima_mov = MovimentacaoImpressora.query.filter_by(impressora_id=item.impressora_id, tipo='Locação', destino=contrato.cliente.nome).order_by(MovimentacaoImpressora.data.desc()).first()
        data_add = ultima_mov.data.strftime('%d/%m/%Y') if ultima_mov else contrato.data_inicio.strftime('%d/%m/%Y')
        custo_nome = item.franquia_pai.nome if item.franquia_pai else None
        dados_itens.append({'modelo': item.impressora.modelo, 'serial': item.impressora.serial, 'data_inclusao': data_add, 'custo_nome': custo_nome, 'valor': item.valor_locacao_unitario})
    return render_template('imprimir_contrato.html', contrato=contrato, dados_itens=dados_itens, hoje=datetime.now().strftime('%d/%m/%Y %H:%M'))

def verificar_migracoes():
    with app.app_context():
        db.create_all()
        try: db.session.execute(text('SELECT * FROM contrato_historico LIMIT 1'))
        except: print("Criando tabela contrato_historico..."); db.create_all()
        try: db.session.execute(text('SELECT tipo_franquia_item FROM contrato_item LIMIT 1'))
        except:
            print("Migrando Contrato Item...")
            try: db.session.execute(text('ALTER TABLE contrato_item ADD COLUMN tipo_franquia_item VARCHAR(20) DEFAULT "Individual"')); db.session.execute(text('ALTER TABLE contrato ADD COLUMN justificativa_cancelamento TEXT')); db.session.commit()
            except: pass

if __name__ == '__main__':
    verificar_migracoes()
    app.run(debug=True)