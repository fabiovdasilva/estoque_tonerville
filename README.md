# 🖨️ PrintControl - Sistema de Gestão de Outsourcing

O **PrintControl** é um sistema unificado desenvolvido para gerenciar operações de outsourcing de impressão, controle de estoque, vendas e contratos de locação. O projeto visa centralizar informações de clientes, fornecedores e equipamentos, oferecendo um histórico detalhado de movimentações e manutenções.

## 🚀 Funcionalidades

### 📦 Gestão de Estoque
- Cadastro de produtos com categorias (Toner, Peças, Impressoras).
- Controle de quantidade mínima e alertas visuais (Cores) para estoque baixo/crítico.
- Histórico de entradas e saídas.

### 💰 Vendas
- Registro de vendas para clientes.
- Controle de status de pagamento (Pendente, Pago, Atrasado).
- Controle de emissão de Nota Fiscal e Boleto.

### 🚚 Saída para Locação
- Módulo específico para envio de suprimentos/peças para clientes de contrato.
- **Vinculação Inteligente:** Seleção de impressora filtrada pelo cliente selecionado (Exibe Modelo, Serial e Patrimônio).
- Histórico de itens enviados por cliente.

### 🖨️ Controle de Impressoras (Patrimônio)
- Cadastro completo de equipamentos (Marca, Modelo, Serial, MLT).
- **Linha do Tempo (Timeline):** Histórico visual de todas as movimentações (Locação, Devolução, Manutenção).
- **Gestão de Manutenção:** Abertura de O.S., registro de logs (Aguardando peça, Em bancada) e histórico separado por O.S.

### 🤝 Gestão de Contratos
- Cadastro de contratos de locação.
- Classificação ABC de clientes.
- Monitoramento de datas de vencimento e renovação.

### 🏭 Fornecedores e Compras
- Agenda de contatos de fornecedores.
- **Pedidos de Compra:**
  - Adição dinâmica de múltiplos itens.
  - Cálculo automático de totais e frete.
  - Gestão de ciclo de vida (Pendente, Entregue, Cancelado).
  - Edição de pedidos a qualquer momento.

## 🛠️ Tecnologias Utilizadas

- **Backend:** Python (Flask).
- **Banco de Dados:** SQLite (SQLAlchemy ORM).
- **Frontend:** HTML5, CSS3, Bootstrap 5, JavaScript (Vanilla).
- **Design:** Interface limpa, responsiva e focada em usabilidade (UI Clean).

## ⚙️ Como Executar o Projeto

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/SEU_USUARIO/printcontrol-sistema.git](https://github.com/SEU_USUARIO/printcontrol-sistema.git)
   cd printcontrol-sistema

2. **Crie um ambiente virtual (recomendado):**

Bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate

3. **Instale as dependências:**

Bash
pip install -r requirements.txt

4. **Inicie o Banco de Dados: Ao rodar a aplicação pela primeira vez, o arquivo database.db será criado automaticamente.**

5. **Execute a aplicação:**

Bash
python app.py

6. **Acesse: Abra o navegador em http://127.0.0.1:5000**

