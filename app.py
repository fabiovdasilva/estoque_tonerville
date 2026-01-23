from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract, desc, cast, String
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'printcontrol_secret'

db = SQLAlchemy(app)

# --- UTILS ---
def limpar_float(valor_str):
    if not valor_str or str(valor_str).strip() == '':
        return 0.0
    try:
        limpo = str(valor_str).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        return float(limpo)
    except ValueError:
        return 0.0

def registrar_log(acao, detalhes):
    try:
        novo_log = SystemLog(acao=acao, detalhes=detalhes)
        db.session.add(novo_log)
    except Exception as e:
        print(f"Erro log: {e}")

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

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo_pessoa = db.Column(db.String(20))
    documento = db.Column(db.String(20))
    endereco = db.Column(db.String(200))
    telefone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    data_fechamento = db.Column(db.String(50))
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

    @property
    def ultima_movimentacao(self):
        return Movimentacao.query.filter(
            Movimentacao.produto_id == self.id,
            Movimentacao.status != 'Cancelado'
        ).order_by(Movimentacao.data.desc()).first()

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
    status = db.Column(db.String(20), default='Ativo') # Ativo, Cancelado
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
    status = db.Column(db.String(20), default='Ativo') # Ativo, Cancelado
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
    
    # DEFINIÇÃO CENTRALIZADA DOS RELACIONAMENTOS
    # O 'backref' cria automaticamente o campo 'impressora' nas classes filhas
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
    
    # Relacionamento com Logs (Filho desta O.S.)
    logs = db.relationship('LogManutencao', backref='manutencao_pai', cascade="all, delete-orphan")
    # REMOVIDO: impressora =

class LogManutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Pode pertencer a uma Manutenção (O.S.) OU diretamente à Impressora (log solto)
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
    
    # Relacionamento
    pedidos = db.relationship('PedidoCompra', backref='fornecedor', cascade="all, delete-orphan")

class PedidoCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedor.id'), nullable=False)
    # Removemos descricao_itens simples, agora usamos relacionamento
    valor_itens = db.Column(db.Float, default=0.0)
    frete = db.Column(db.Float, default=0.0)
    valor_total = db.Column(db.Float, default=0.0)
    prazo_pagamento = db.Column(db.String(50)) 
    data_emissao = db.Column(db.Date, default=datetime.now)
    data_entrega_prevista = db.Column(db.Date)
    status = db.Column(db.String(20), default='Pendente') # Pendente, Entregue, Cancelado
    observacao = db.Column(db.Text)
    
    itens = db.relationship('ItemPedidoCompra', backref='pedido', cascade="all, delete-orphan")

class ItemPedidoCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_compra.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=True) # Opcional: pode ser item avulso
    descricao = db.Column(db.String(200)) # Nome do produto (copiado ou digitado)
    quantidade = db.Column(db.Integer, nullable=False)
    valor_unitario = db.Column(db.Float, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    
    produto = db.relationship('Produto')

# --- CONTEXTO ---
@app.template_filter('currency')
def currency_filter(value):
    if value is None: value = 0
    return "R$ {:,.2f}".format(value).replace(",", "X").replace(".", ",").replace("X", ".")

@app.template_filter('formata_codigo')
def formata_codigo(id):
    return f"P{id:03d}"

@app.context_processor
def utility_processor():
    try:
        config = Configuracao.query.first()
        if not config:
            config = Configuracao()
            db.session.add(config)
            db.session.commit()
        return dict(hoje=datetime.now(), config=config)
    except:
        return dict(hoje=datetime.now(), config=None)

# --- ROTAS ---

@app.route('/')
def index():
    # 1. Totais Gerais
    total_itens = db.session.query(func.sum(Produto.quantidade)).scalar() or 0
    
    config = Configuracao.query.first()
    margem = config.margem_atencao_pct if config else 20
    dias_vencimento = config.dias_alerta_vencimento if config else 7
    
    todos_produtos = Produto.query.all()
    itens_atencao = []
    for p in todos_produtos:
        limite = p.minimo * (1 + margem / 100)
        if p.quantidade <= p.minimo:
            itens_atencao.append({'produto': p, 'status': 'Crítico', 'classe': 'bg-danger', 'row_class': 'row-alert-red'})
        elif p.quantidade <= limite:
            itens_atencao.append({'produto': p, 'status': 'Baixo', 'classe': 'bg-warning text-dark', 'row_class': 'row-alert-orange'})
    itens_atencao.sort(key=lambda x: x['produto'].quantidade)

    data_limite = datetime.now().date() + timedelta(days=dias_vencimento)
    vendas_vencendo = Venda.query.filter(
        Venda.status_pagamento != 'Pago',
        Venda.status_geral != 'Cancelada',
        Venda.data_vencimento <= data_limite
    ).order_by(Venda.data_vencimento).all()

    total_alertas = len(itens_atencao) + len(vendas_vencendo)
    
    # 5. Métricas (CORRIGIDO: FILTRANDO CANCELADOS)
    mes_atual = datetime.now().month
    saidas_mes = db.session.query(func.sum(Movimentacao.quantidade)).filter(
        Movimentacao.tipo.in_(['Saida_Locacao', 'Ajuste_Saida', 'Venda']),
        Movimentacao.status != 'Cancelado',  # Ignora cancelados
        extract('month', Movimentacao.data) == mes_atual
    ).scalar() or 0

    # Tabelas Separadas (CORRIGIDO: FILTRANDO CANCELADOS)
    ultimas_entradas = Movimentacao.query.filter(
        Movimentacao.tipo == 'Entrada',
        Movimentacao.status != 'Cancelado'
    ).order_by(Movimentacao.data.desc()).limit(30).all()

    ultimas_saidas = Movimentacao.query.filter(
        Movimentacao.tipo.in_(['Saida_Locacao', 'Venda', 'Ajuste_Saida']),
        Movimentacao.status != 'Cancelado'
    ).order_by(Movimentacao.data.desc()).limit(30).all()
    
    total_contratos = "R$ 18.500,00" 

    return render_template('dashboard.html', 
                           total_itens=total_itens, 
                           saidas_mes=saidas_mes,
                           total_alertas=total_alertas,
                           itens_atencao=itens_atencao,
                           vendas_vencendo=vendas_vencendo,
                           ultimas_entradas=ultimas_entradas,
                           ultimas_saidas=ultimas_saidas,
                           total_contratos=total_contratos)

@app.route('/notificacoes')
def notificacoes():
    config = Configuracao.query.first()
    margem = config.margem_atencao_pct if config else 20
    dias_vencimento = config.dias_alerta_vencimento if config else 7
    
    todos_produtos = Produto.query.all()
    itens_atencao = []
    for p in todos_produtos:
        limite = p.minimo * (1 + margem / 100)
        if p.quantidade <= p.minimo:
            itens_atencao.append({'produto': p, 'status': 'Crítico', 'classe': 'bg-danger', 'row_class': 'row-alert-red'})
        elif p.quantidade <= limite:
            itens_atencao.append({'produto': p, 'status': 'Baixo', 'classe': 'bg-warning text-dark', 'row_class': 'row-alert-orange'})
            
    data_limite = datetime.now().date() + timedelta(days=dias_vencimento)
    vendas_vencendo = Venda.query.filter(
        Venda.status_pagamento != 'Pago',
        Venda.status_geral != 'Cancelada',
        Venda.data_vencimento <= data_limite
    ).order_by(Venda.data_vencimento).all()
    
    return render_template('notificacoes.html', itens_atencao=itens_atencao, vendas_vencendo=vendas_vencendo)

@app.route('/estoque')
def estoque():
    marca_filtro = request.args.get('marca')
    apenas_disponiveis = request.args.get('disponiveis')
    query = Produto.query
    if marca_filtro and marca_filtro != 'Todas': query = query.filter(Produto.marca.ilike(f'%{marca_filtro}%'))
    if apenas_disponiveis: query = query.filter(Produto.quantidade > 0)
    
    produtos = query.all()
    
    # Histórico mostra tudo, inclusive cancelados (com destaque visual)
    historico = Movimentacao.query.order_by(Movimentacao.data.desc()).limit(30).all()
    
    valor_total_estoque = sum([p.quantidade * p.valor_pago for p in produtos])
    total_itens_estoque = sum([p.quantidade for p in produtos])
    
    # Top Saídas (CORRIGIDO: Filtrar Cancelados)
    top_saidas = db.session.query(Produto.nome, Produto.marca, func.sum(Movimentacao.quantidade).label('total')).join(Movimentacao).filter(
        Movimentacao.tipo.in_(['Saida_Locacao', 'Venda', 'Ajuste_Saida']),
        Movimentacao.status != 'Cancelado'
    ).group_by(Produto.id).order_by(desc('total')).limit(30).all()

    marcas = db.session.query(Produto.marca).distinct().all()
    lista_marcas = [m[0] for m in marcas if m[0]]
    
    return render_template('estoque.html', produtos=produtos, historico=historico, marcas=lista_marcas, 
                           valor_total_estoque=valor_total_estoque, total_itens_estoque=total_itens_estoque, top_saidas=top_saidas)

@app.route('/saida_locacao')
def saida_locacao():
    busca = request.args.get('busca')
    periodo = request.args.get('periodo')
    cliente_id = request.args.get('cliente_id')
    
    query = PedidoSaida.query
    
    if busca:
        term = f"%{busca}%"
        query = query.join(Cliente).filter(
            (cast(PedidoSaida.numero_pedido, String).like(term)) | 
            (Cliente.nome.like(term)) |
            (PedidoSaida.impressora.like(term))
        )
    
    if cliente_id and cliente_id != 'Todos':
        query = query.filter(PedidoSaida.cliente_id == int(cliente_id))
        
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
    top_clientes = db.session.query(
        Cliente.nome, 
        func.sum(ItemPedido.quantidade).label('total_itens')
    ).join(PedidoSaida, Cliente.pedidos).join(ItemPedido).filter(
        extract('month', PedidoSaida.data) == mes_atual,
        PedidoSaida.status == 'Ativo' # Filtra pedidos cancelados
    ).group_by(Cliente.id).order_by(desc('total_itens')).limit(30).all()

    return render_template('saida_locacao.html', 
                           produtos=produtos, 
                           clientes=clientes, 
                           pedidos=pedidos,
                           top_clientes=top_clientes,
                           hoje=datetime.now())

# ... (Rotas clientes, vendas, etc permanecem iguais) ...
@app.route('/clientes')
def clientes():
    todos_clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes.html', clientes=todos_clientes)

@app.route('/vendas')
def vendas():
    # ... código vendas igual ...
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

# --- AÇÕES CANCELAMENTO CORRIGIDAS ---

@app.route('/cancelar_venda', methods=['POST'])
def cancelar_venda():
    venda_id = request.form.get('venda_id')
    justificativa = request.form.get('justificativa')
    venda = Venda.query.get(venda_id)
    if not venda: return redirect(url_for('vendas'))
        
    for item in venda.itens:
        # 1. Devolve estoque
        produto = Produto.query.get(item.produto_id)
        produto.quantidade += item.quantidade
    
    # 2. Marca movimentações originais como Canceladas
    # Supondo que o numero_documento foi salvo como f"V-{venda.id}"
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
    if not pedido or pedido.status == 'Cancelado':
        return redirect(url_for('saida_locacao'))
    
    # 1. Devolve Estoque
    for item in pedido.itens:
        produto = Produto.query.get(item.produto_id)
        produto.quantidade += item.quantidade
        
    pedido.status = 'Cancelado'
    pedido.justificativa_cancelamento = justificativa
    
    # 2. Marca Movimentações como Canceladas
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
    if not mov or mov.status == 'Cancelado':
        return redirect(url_for('estoque'))

    produto = Produto.query.get(mov.produto_id)
    
    if mov.tipo == 'Entrada':
        if produto.quantidade < mov.quantidade:
            flash(f'Erro: Estoque insuficiente para cancelar entrada.')
            return redirect(url_for('estoque'))
        produto.quantidade -= mov.quantidade
    else: # Saidas
        produto.quantidade += mov.quantidade

    mov.status = 'Cancelado'
    mov.justificativa_cancelamento = justificativa
    mov.observacao = (mov.observacao or '') + " [CANCELADO]"
    
    db.session.commit()
    return redirect(url_for('estoque'))

# ... (Demais rotas criar_produto, editar_produto, etc - manter iguais) ...
@app.route('/nova_venda', methods=['POST'])
def nova_venda():
    # ... código nova venda ...
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
    novo = Produto(nome=nome_produto, categoria=request.form['categoria'], marca=request.form['marca'], compatibilidade=request.form['compatibilidade'], quantidade=0, minimo=int(request.form['minimo'] or 5), valor_pago=0.0, valor_venda=valor_venda, observacao=request.form['observacao'])
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
        
        # VALIDAÇÃO NOVA: Impede entrada com valor zero ou negativo
        if custo <= 0:
            flash('ERRO: Para entrada de estoque, o Valor Unitário é obrigatório e deve ser maior que zero.')
            return redirect(url_for('estoque'))
            
        total = produto.quantidade * produto.valor_pago + qtd * custo
        produto.quantidade += qtd
        if produto.quantidade > 0: produto.valor_pago = total / produto.quantidade
        
        db.session.add(Movimentacao(
            produto_id=produto.id, tipo='Entrada', categoria_movimento=request.form.get('origem_tipo'), 
            numero_documento=request.form.get('numero_documento'), quantidade=qtd, 
            valor_unitario_entrada=custo, 
            destino_origem=request.form.get('fornecedor'), observacao=obs
        ))
        
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
    cliente_id = request.args.get('cliente_id') # Novo Filtro
    
    query = Impressora.query
    
    if busca:
        term = f"%{busca}%"
        query = query.filter(
            (Impressora.marca.like(term)) | # Busca também pela marca
            (Impressora.modelo.like(term)) | 
            (Impressora.serial.like(term)) | 
            (Impressora.mlt.like(term)) |
            (Impressora.localizacao.like(term))
        )
    
    if status and status != 'Todas':
        query = query.filter(Impressora.status == status)
        
    # Lógica do Filtro de Cliente
    if cliente_id and cliente_id != 'Todos':
        cliente = Cliente.query.get(int(cliente_id))
        if cliente:
            # Filtra onde a localização é igual ao nome do cliente
            query = query.filter(Impressora.localizacao == cliente.nome)
        
    impressoras = query.order_by(Impressora.modelo).all()
    clientes = Cliente.query.order_by(Cliente.nome).all()
    
    # ... (Resto do código: ultimas_movimentacoes, contadores, return render_template) ...
    # Copie o restante igual ao anterior:
    ultimas_movimentacoes = MovimentacaoImpressora.query.order_by(MovimentacaoImpressora.data.desc()).limit(20).all()
    
    total = len(impressoras) # Nota: isso conta só as filtradas. Se quiser totais fixos, teria que fazer query separada.
    # Para manter os cards do topo fixos (gerais), faça queries separadas:
    total_geral = Impressora.query.count()
    disponiveis = Impressora.query.filter_by(status='Disponível').count()
    locadas = Impressora.query.filter_by(status='Locada').count()
    manutencao = Impressora.query.filter_by(status='Manutenção').count()
    
    return render_template('impressoras.html', 
                           impressoras=impressoras,
                           clientes=clientes,
                           ultimas_movimentacoes=ultimas_movimentacoes,
                           total=total_geral,
                           disponiveis=disponiveis,
                           locadas=locadas,
                           manutencao=manutencao,
                           request=request) # Passar request para manter filtro selecionado

@app.route('/api/manutencoes_impressora/<int:id>')
def api_manutencoes_impressora(id):
    # Busca todas as manutenções da impressora, da mais recente para a mais antiga
    manutencoes = Manutencao.query.filter_by(impressora_id=id).order_by(Manutencao.numero_ordem.desc()).all()
    
    lista = []
    for m in manutencoes:
        lista.append({
            'id': m.id,
            'numero': m.numero_ordem,
            'status': m.status_atual,
            'inicio': m.data_inicio.strftime('%d/%m/%Y'),
            'motivo': m.motivo_inicial
        })
    
    return jsonify(lista)

# --- ROTA DE MOVIMENTAÇÃO ATUALIZADA ---
@app.route('/movimentar_impressora', methods=['POST'])
def movimentar_impressora():
    try:
        imp_id = request.form['impressora_id']
        tipo = request.form['tipo_movimentacao'] # Locação, Manutenção, Estoque
        obs = request.form['observacao']
        novo_contador = int(request.form['contador_atual'])
        
        impressora = Impressora.query.get(imp_id)
        
        # Validação do Contador
        if novo_contador < impressora.contador:
            flash(f'ERRO: O contador informado ({novo_contador}) é menor que o contador atual ({impressora.contador}).')
            return redirect(url_for('impressoras'))
            
        origem_atual = impressora.localizacao
        destino_novo = "Estoque" # Default
        
        # 1. AÇÃO: LOCAÇÃO
        if tipo == 'Locação':
            cliente_id = request.form.get('cliente_id')
            cliente = Cliente.query.get(cliente_id)
            destino_novo = cliente.nome
            impressora.status = 'Locada'
            
        # 2. AÇÃO: MANUTENÇÃO
        elif tipo == 'Manutenção':
            destino_novo = "Assistência Técnica"
            impressora.status = 'Manutenção'
            
            # Abre O.S.
            qtd_manutencoes = Manutencao.query.filter_by(impressora_id=impressora.id).count()
            nova_manutencao = Manutencao(
                impressora_id=impressora.id,
                numero_ordem=qtd_manutencoes + 1,
                motivo_inicial=obs,
                status_atual='Aberta'
            )
            db.session.add(nova_manutencao)
            db.session.flush()
            
            db.session.add(LogManutencao(
                manutencao_id=nova_manutencao.id,
                titulo="Abertura de Chamado",
                observacao=f"Motivo: {obs}"
            ))

        # 3. AÇÃO: ESTOQUE (Serve para Devolução ou Retorno de Manutenção)
        elif tipo == 'Estoque':
            destino_novo = "Estoque"
            impressora.status = 'Disponível'
            
            # Se estava em manutenção, fecha a O.S. automaticamente
            manutencao_aberta = Manutencao.query.filter_by(impressora_id=impressora.id, status_atual='Aberta').first()
            if manutencao_aberta:
                manutencao_aberta.status_atual = 'Finalizada'
                manutencao_aberta.data_fim = datetime.now()
                db.session.add(LogManutencao(
                    manutencao_id=manutencao_aberta.id,
                    titulo="Finalizado",
                    observacao="Equipamento retornou ao estoque."
                ))

        # Atualiza a Impressora
        impressora.localizacao = destino_novo
        impressora.contador = novo_contador
        
        # Registra no Histórico
        mov = MovimentacaoImpressora(
            impressora_id=impressora.id,
            tipo=tipo,
            origem=origem_atual,
            destino=destino_novo,
            contador_momento=novo_contador,
            observacao=obs
        )
        db.session.add(mov)
        db.session.commit()
        flash('Movimentação registrada com sucesso.')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}')
        
    return redirect(url_for('impressoras'))

# --- NOVA ROTA: ADICIONAR LOG DE MANUTENÇÃO ---
@app.route('/adicionar_log_manutencao', methods=['POST'])
def adicionar_log_manutencao():
    try:
        manutencao_id = request.form.get('manutencao_id') # Agora pega o ID selecionado
        titulo = request.form['status_detalhe']
        obs = request.form['observacao']
        
        if manutencao_id:
            log = LogManutencao(
                manutencao_id=int(manutencao_id),
                titulo=titulo,
                observacao=obs
            )
            db.session.add(log)
            db.session.commit()
            flash('Histórico da O.S. atualizado com sucesso.')
        else:
            flash('Erro: Nenhuma Ordem de Serviço foi selecionada.')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}')
        
    return redirect(url_for('impressoras'))

# --- ADICIONE ESTA ROTA PARA BUSCAR IMPRESSORAS DO CLIENTE ---
@app.route('/api/impressoras_cliente/<int:cliente_id>')
def api_impressoras_cliente(cliente_id):
    cliente = Cliente.query.get(cliente_id)
    if not cliente:
        return jsonify([])
    
    # Busca impressoras onde a localização é igual ao nome do cliente
    # e o status é 'Locada' (para garantir)
    impressoras = Impressora.query.filter_by(status='Locada', localizacao=cliente.nome).all()
    
    lista = []
    for imp in impressoras:
        mlt_texto = imp.mlt if imp.mlt else "S/M"
        display = f"{imp.modelo} | S/N: {imp.serial} | MLT: {mlt_texto}"
        
        lista.append({
            'id': imp.id,
            'modelo': imp.modelo,
            'serial': imp.serial,
            'mlt': imp.mlt,
            'texto_display': display # Esse texto aparecerá no dropdown
        })
        
    return jsonify(lista)

# --- FORNECEDORES ---

@app.route('/fornecedores')
def fornecedores():
    # Captura a aba da URL (padrão é 'contatos')
    active_tab = request.args.get('tab', 'contatos')
    
    fornecedores_lista = Fornecedor.query.order_by(Fornecedor.nome).all()
    produtos_lista = Produto.query.order_by(Produto.nome).all()
    pedidos_lista = PedidoCompra.query.order_by(PedidoCompra.data_emissao.desc()).all()
    
    return render_template('fornecedores.html', 
                           fornecedores=fornecedores_lista,
                           produtos=produtos_lista,
                           pedidos=pedidos_lista,
                           hoje=datetime.now(),
                           active_tab=active_tab)


@app.route('/criar_fornecedor', methods=['POST'])
def criar_fornecedor():
    try:
        novo = Fornecedor(
            nome=request.form['nome'],
            email=request.form['email'],
            telefone=request.form['telefone'],
            observacao=request.form['observacao']
        )
        db.session.add(novo)
        db.session.commit()
        flash('Fornecedor cadastrado.')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}')
    return redirect(url_for('fornecedores'))

@app.route('/editar_fornecedor', methods=['POST'])
def editar_fornecedor():
    try:
        f_id = request.form['fornecedor_id']
        f = Fornecedor.query.get(f_id)
        if f:
            f.nome = request.form['nome']
            f.email = request.form['email']
            f.telefone = request.form['telefone']
            f.observacao = request.form['observacao']
            db.session.commit()
            flash('Fornecedor atualizado.')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}')
    return redirect(url_for('fornecedores'))

@app.route('/excluir_fornecedor/<int:id>')
def excluir_fornecedor(id):
    f = Fornecedor.query.get(id)
    if f:
        db.session.delete(f)
        db.session.commit()
    return redirect(url_for('fornecedores'))

# --- ROTAS PARA PEDIDOS DE COMPRA ---

@app.route('/criar_pedido_compra', methods=['POST'])
def criar_pedido_compra():
    try:
        data_emissao = datetime.strptime(request.form['data_emissao'], '%Y-%m-%d')
        data_entrega = datetime.strptime(request.form['data_entrega'], '%Y-%m-%d') if request.form['data_entrega'] else None
        valor = limpar_float(request.form['valor_total'])
        
        novo = PedidoCompra(
            fornecedor_id=int(request.form['fornecedor_id']),
            descricao_itens=request.form['descricao_itens'],
            valor_total=valor,
            prazo_pagamento=request.form['prazo_pagamento'],
            data_emissao=data_emissao,
            data_entrega_prevista=data_entrega,
            entregue=False
        )
        db.session.add(novo)
        db.session.commit()
        flash('Pedido de compra registrado.')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}')
    return redirect(url_for('fornecedores'))

@app.route('/toggle_pedido_entregue/<int:id>')
def toggle_pedido_entregue(id):
    pedido = PedidoCompra.query.get(id)
    if pedido:
        pedido.entregue = not pedido.entregue # Inverte o status
        db.session.commit()
    return redirect(url_for('fornecedores'))

# ROTA UNIFICADA PARA CRIAR OU EDITAR PEDIDO
@app.route('/salvar_pedido_compra', methods=['POST'])
def salvar_pedido_compra():
    try:
        pedido_id = request.form.get('pedido_id')
        
        # Dados do Form
        fornecedor_id = int(request.form['fornecedor_id'])
        prazo = request.form['prazo_pagamento']
        data_emissao = datetime.strptime(request.form['data_emissao'], '%Y-%m-%d')
        data_entrega = datetime.strptime(request.form['data_entrega'], '%Y-%m-%d') if request.form['data_entrega'] else None
        frete = float(request.form['frete'] or 0)
        obs = request.form['observacao']
        
        # Listas dos Itens (arrays do form)
        prod_ids = request.form.getlist('item_produto_id')
        descs = request.form.getlist('item_desc')
        qtds = request.form.getlist('item_qtd')
        vals = request.form.getlist('item_valor')
        
        if pedido_id:
            # EDITAR: Busca e limpa itens antigos para recriar
            pedido = PedidoCompra.query.get(pedido_id)
            for item in pedido.itens:
                db.session.delete(item)
        else:
            # CRIAR NOVO
            pedido = PedidoCompra()
            db.session.add(pedido)
        
        # Atualiza dados principais
        pedido.fornecedor_id = fornecedor_id
        pedido.prazo_pagamento = prazo
        pedido.data_emissao = data_emissao
        pedido.data_entrega_prevista = data_entrega
        pedido.frete = frete
        pedido.observacao = obs
        if not pedido.status: pedido.status = 'Pendente'
        
        db.session.flush() # Garante ID do pedido
        
        # Processa Itens
        total_itens = 0
        for i in range(len(descs)):
            qtd = int(qtds[i] or 0)
            unit = float(vals[i] or 0)
            total_linha = qtd * unit
            total_itens += total_linha
            
            p_id = prod_ids[i] if prod_ids[i] else None
            
            novo_item = ItemPedidoCompra(
                pedido_id=pedido.id,
                produto_id=p_id,
                descricao=descs[i],
                quantidade=qtd,
                valor_unitario=unit,
                valor_total=total_linha
            )
            db.session.add(novo_item)
            
        pedido.valor_itens = total_itens
        pedido.valor_total = total_itens + frete
        
        db.session.commit()
        flash('Pedido salvo com sucesso.')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao salvar pedido: {e}')
        print(e)
        
    return redirect(url_for('fornecedores', tab='pedidos'))

@app.route('/cancelar_pedido_compra/<int:id>')
def cancelar_pedido_compra(id):
    pedido = PedidoCompra.query.get(id)
    if pedido:
        pedido.status = 'Cancelado'
        db.session.commit()
        flash('Pedido cancelado.')
    return redirect(url_for('fornecedores', tab='pedidos')) # Redireciona para aba pedidos

@app.route('/entregar_pedido_compra/<int:id>')
def entregar_pedido_compra(id):
    pedido = PedidoCompra.query.get(id)
    if pedido:
        pedido.status = 'Entregue'
        db.session.commit()
        flash('Pedido marcado como Entregue.')
    return redirect(url_for('fornecedores', tab='pedidos'))

# API PARA BUSCAR DETALHES (Resumo e Edição)
@app.route('/api/pedido_compra/<int:id>')
def api_pedido_compra(id):
    p = PedidoCompra.query.get(id)
    itens = []
    for i in p.itens:
        itens.append({
            'produto_id': i.produto_id or '',
            'descricao': i.descricao,
            'quantidade': i.quantidade,
            'valor_unitario': i.valor_unitario,
            'valor_total': i.valor_total
        })
        
    data = {
        'id': p.id,
        'fornecedor_id': p.fornecedor_id,
        'fornecedor_nome': p.fornecedor.nome,
        'data_emissao': p.data_emissao.strftime('%Y-%m-%d'),
        'data_entrega': p.data_entrega_prevista.strftime('%Y-%m-%d') if p.data_entrega_prevista else '',
        'prazo': p.prazo_pagamento,
        'frete': p.frete,
        'valor_itens': p.valor_itens,
        'valor_total': p.valor_total,
        'observacao': p.observacao,
        'status': p.status,
        'itens': itens
    }
    return jsonify(data)



# --- NOVA ROTA: EDITAR MOVIMENTAÇÃO (HISTÓRICO) ---
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
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao editar: {e}')
    return redirect(url_for('impressoras'))

# --- NOVA ROTA: API TIMELINE UNIFICADA ---
@app.route('/api/historico_impressora/<int:id>')
def api_historico_impressora(id):
    # Busca Movimentações
    movs = MovimentacaoImpressora.query.filter_by(impressora_id=id).all()
    # Busca Logs de Manutenção
    logs = LogManutencao.query.filter_by(impressora_id=id).all()
    
    lista_unificada = []
    
    for m in movs:
        lista_unificada.append({
            'categoria': 'movimentacao',
            'data_obj': m.data,
            'data': m.data.strftime('%d/%m/%Y %H:%M'),
            'tipo': m.tipo,
            'origem': m.origem,
            'destino': m.destino,
            'contador': m.contador_momento,
            'observacao': m.observacao
        })
        
    for l in logs:
        lista_unificada.append({
            'categoria': 'manutencao',
            'data_obj': l.data,
            'data': l.data.strftime('%d/%m/%Y %H:%M'),
            'titulo': l.status_detalhe, # Ex: Aguardando Peça
            'observacao': l.observacao
        })
    
    # Ordena por data (mais recente primeiro)
    lista_unificada.sort(key=lambda x: x['data_obj'], reverse=True)
    
    return jsonify(lista_unificada)

# --- ATUALIZAR CRIAR IMPRESSORA (Para gerar o primeiro log) ---
@app.route('/criar_impressora', methods=['POST'])
def criar_impressora():
    try:
        nova = Impressora(
            marca=request.form['marca'], # Captura a marca
            modelo=request.form['modelo'],
            serial=request.form['serial'],
            mlt=request.form['mlt'],
            contador=int(request.form['contador'] or 0),
            status='Disponível', 
            localizacao='Estoque',
            observacao=request.form['observacao']
        )
        db.session.add(nova)
        db.session.flush() 
        
        # Log Inicial
        db.session.add(MovimentacaoImpressora(
            impressora_id=nova.id,
            tipo='Cadastro',
            origem='-',
            destino='Estoque',
            contador_momento=nova.contador,
            observacao='Cadastro inicial no sistema'
        ))
        
        db.session.commit()
        flash('Impressora cadastrada com sucesso.')
        
    except IntegrityError:
        db.session.rollback()
        flash('ERRO: Já existe uma impressora cadastrada com este Número de Série!')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao cadastrar: {str(e)}')
        
    return redirect(url_for('impressoras'))

@app.route('/editar_impressora', methods=['POST'])
def editar_impressora():
    try:
        imp_id = request.form.get('impressora_id')
        imp = Impressora.query.get(imp_id)
        if imp:
            imp.marca = request.form['marca'] # Atualiza a marca
            imp.modelo = request.form['modelo']
            imp.serial = request.form['serial']
            imp.mlt = request.form['mlt']
            # Contador não edita aqui, só via movimentação ou técnico
            imp.observacao = request.form['observacao']
            db.session.commit()
            flash('Informações atualizadas.')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao editar: {e}')
    return redirect(url_for('impressoras'))


@app.route('/excluir_impressora/<int:id>')
def excluir_impressora(id):
    imp = Impressora.query.get(id)
    if imp:
        db.session.delete(imp)
        db.session.commit()
    return redirect(url_for('impressoras'))

@app.route('/api/historico_completo/<int:id>')
def api_historico_completo(id):
    # 1. Busca Histórico Geral (Movimentações)
    movs = MovimentacaoImpressora.query.filter_by(impressora_id=id).order_by(MovimentacaoImpressora.data.desc()).all()
    lista_movs = [{
        'data': m.data.strftime('%d/%m/%Y %H:%M'),
        'tipo': m.tipo,
        'origem': m.origem,
        'destino': m.destino,
        'contador': m.contador_momento,
        'obs': m.observacao
    } for m in movs]
    
    # 2. Busca Manutenções Estruturadas
    manutencoes = Manutencao.query.filter_by(impressora_id=id).order_by(Manutencao.numero_ordem.desc()).all()
    lista_manut = []
    
    for m in manutencoes:
        logs = []
        for l in m.logs:
            logs.append({
                'data': l.data.strftime('%d/%m %H:%M'),
                'titulo': l.titulo,
                'obs': l.observacao
            })
        
        lista_manut.append({
            'numero': m.numero_ordem,
            'inicio': m.data_inicio.strftime('%d/%m/%Y'),
            'fim': m.data_fim.strftime('%d/%m/%Y') if m.data_fim else 'Em andamento',
            'status': m.status_atual,
            'motivo': m.motivo_inicial,
            'logs': logs
        })
        
    return jsonify({'movimentacoes': lista_movs, 'manutencoes': lista_manut})


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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)