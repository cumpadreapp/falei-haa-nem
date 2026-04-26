from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), unique=True, nullable=False)
    foto = db.Column(db.String(200), default='default.png')
    biografia = db.Column(db.Text, default='')
    redes_sociais = db.Column(db.Text, default='{}')
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    comentarios = db.relationship('Comentario', backref='autor', lazy=True)
    visualizacoes = db.relationship('Visualizacao', backref='usuario', lazy=True)

    def get_redes(self):
        return json.loads(self.redes_sociais) if self.redes_sociais else {}

    def set_redes(self, dados):
        self.redes_sociais = json.dumps(dados)

class Postagem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200))
    tipo = db.Column(db.String(20))
    conteudo = db.Column(db.Text)
    arquivo = db.Column(db.String(200))
    link_youtube = db.Column(db.String(200))
    localizacao = db.Column(db.String(200))
    visualizacoes = db.Column(db.Integer, default=0)
    relevancia = db.Column(db.Integer, default=0)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    comentarios = db.relationship('Comentario', backref='postagem', lazy=True)
    visualizacoes_usuarios = db.relationship('Visualizacao', backref='postagem', lazy=True)

class Comentario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text)
    audio = db.Column(db.String(200))
    data = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    postagem_id = db.Column(db.Integer, db.ForeignKey('postagem.id'))

class Visualizacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    postagem_id = db.Column(db.Integer, db.ForeignKey('postagem.id'))
    session_id = db.Column(db.String(100))
    data = db.Column(db.DateTime, default=datetime.utcnow)

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    imagem = db.Column(db.String(200))
    link = db.Column(db.String(300))
    ativo = db.Column(db.Boolean, default=True)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

class CodigoConfirmacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telefone = db.Column(db.String(20), unique=True)
    codigo = db.Column(db.String(6))
    data_expiracao = db.Column(db.DateTime)