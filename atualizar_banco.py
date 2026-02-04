from app import app, db

# Isso força o contexto da aplicação para que o banco possa ser acessado
with app.app_context():
    # O comando create_all cria apenas as tabelas que ainda NÃO existem.
    # Ele não apaga seus dados antigos (Clientes, Vendas, etc).
    db.create_all()
    print("Banco de dados atualizado com sucesso! Novas tabelas criadas.")