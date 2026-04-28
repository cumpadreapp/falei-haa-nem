from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
import random
import string
import base64

# ==================== CONFIGURAÇÕES ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'snapdeploy-chave-secreta-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///falei_haa_nemm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Criar pastas de upload
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'fotos_perfil'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'postagens'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audios_comentarios'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para continuar'

# ==================== MODELOS ====================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, default='Usuário')
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
    tipo = db.Column(db.String(20), default='texto')
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

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ==================== ROTAS PRINCIPAIS ====================
@app.route('/')
def index():
    banner = Banner.query.filter_by(ativo=True).first()
    postagens = Postagem.query.order_by(Postagem.relevancia.desc(), Postagem.data_criacao.desc()).all()
    visualizacoes_usuario = {}
    if current_user.is_authenticated:
        visualizacoes = Visualizacao.query.filter_by(user_id=current_user.id).all()
        visualizacoes_usuario = {v.postagem_id: True for v in visualizacoes}
    elif session.get('session_id'):
        visualizacoes = Visualizacao.query.filter_by(session_id=session['session_id']).all()
        visualizacoes_usuario = {v.postagem_id: True for v in visualizacoes}
    return render_template('index.html', banner=banner, postagens=postagens, visualizacoes_usuarios=visualizacoes_usuario)

@app.route('/post/<int:post_id>/visualizar', methods=['POST'])
def marcar_visualizacao(post_id):
    postagem = db.session.get(Postagem, post_id)
    if not postagem:
        return jsonify({'success': False, 'message': 'Postagem não encontrada'})
    
    if not session.get('session_id'):
        session['session_id'] = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    session_id = session['session_id']
    user_id = current_user.id if current_user.is_authenticated else None
    
    visualizacao_existente = Visualizacao.query.filter_by(
        postagem_id=post_id, session_id=session_id
    ).first()
    
    if not visualizacao_existente and (not user_id or not Visualizacao.query.filter_by(postagem_id=post_id, user_id=user_id).first()):
        nova_visualizacao = Visualizacao(
            user_id=user_id,
            postagem_id=post_id,
            session_id=session_id
        )
        db.session.add(nova_visualizacao)
        postagem.visualizacoes += 1
        postagem.relevancia = postagem.visualizacoes + (len(postagem.comentarios) * 2)
        db.session.commit()
        return jsonify({'success': True, 'visualizacoes': postagem.visualizacoes})
    return jsonify({'success': False, 'message': 'Já visualizado'})

@app.route('/post/<int:post_id>/comentario', methods=['POST'])
@login_required
def adicionar_comentario(post_id):
    if not current_user.is_active:
        flash('Sua conta está bloqueada. Contate o administrador.', 'danger')
        return redirect(url_for('index'))
    
    postagem = db.session.get(Postagem, post_id)
    if not postagem:
        flash('Postagem não encontrada', 'danger')
        return redirect(url_for('index'))
    
    texto = request.form.get('texto', '')
    novo_comentario = Comentario(
        texto=texto,
        user_id=current_user.id,
        postagem_id=post_id
    )
    db.session.add(novo_comentario)
    db.session.commit()
    
    postagem.relevancia = postagem.visualizacoes + (len(postagem.comentarios) * 2)
    db.session.commit()
    flash('Comentário adicionado!', 'success')
    return redirect(url_for('index'))

@app.route('/compartilhar/<int:post_id>', methods=['POST'])
def compartilhar_whatsapp(post_id):
    postagem = db.session.get(Postagem, post_id)
    if not postagem:
        return jsonify({'success': False, 'message': 'Postagem não encontrada'})
    
    mensagem = request.form.get('mensagem_personalizada', '')
    numero = request.form.get('numero_whatsapp', '')
    texto = f"{mensagem}\n\n{postagem.titulo}\n{postagem.conteudo}\n\nCompartilhado do Falei, haa Nemm!"
    texto = texto.replace(' ', '%20')
    link = f"https://wa.me/{numero}?text={texto}" if numero else f"https://wa.me/?text={texto}"
    return jsonify({'success': True, 'link': link})

@app.route('/usuario/<int:user_id>/dados')
def usuario_dados(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado'}), 404
    return jsonify({
        'nome': user.nome,
        'foto': url_for('static', filename=user.foto),
        'biografia': user.biografia,
        'telefone': user.telefone,
        'redes': user.get_redes(),
        'data_cadastro': user.data_cadastro.strftime('%d/%m/%Y')
    })

# ==================== AUTENTICAÇÃO ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        telefone = request.form.get('telefone')
        if telefone == 'admin':
            admin = User.query.filter_by(is_admin=True).first()
            if admin:
                login_user(admin)
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Admin não encontrado', 'danger')
        else:
            usuario = User.query.filter_by(telefone=telefone).first()
            if usuario:
                if not usuario.is_active:
                    flash('Conta bloqueada', 'danger')
                else:
                    login_user(usuario)
                    flash(f'Bem-vindo, {usuario.nome}!', 'success')
                    return redirect(url_for('index'))
            else:
                flash('Número não cadastrado', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema', 'info')
    return redirect(url_for('index'))

@app.route('/cadastro/foto', methods=['GET', 'POST'])
def cadastro_foto():
    if request.method == 'POST':
        foto_data = request.form.get('foto_base64')
        if foto_data:
            session['temp_foto'] = foto_data
            return redirect(url_for('cadastro_whatsapp'))
    return render_template('cadastro_foto.html')

@app.route('/cadastro/whatsapp', methods=['GET', 'POST'])
def cadastro_whatsapp():
    if request.method == 'POST':
        telefone = request.form.get('telefone')
        if not telefone.startswith('+'):
            telefone = '+' + telefone
        if User.query.filter_by(telefone=telefone).first():
            flash('Número já cadastrado!', 'danger')
            return redirect(url_for('cadastro_whatsapp'))
        codigo = ''.join(random.choices(string.digits, k=6))
        session['temp_telefone'] = telefone
        session['temp_codigo'] = codigo
        flash(f'[SIMULAÇÃO] Código de verificação: {codigo}', 'info')
        return redirect(url_for('confirmar_whatsapp'))
    return render_template('cadastro_whatsapp.html')

@app.route('/cadastro/confirmar', methods=['GET', 'POST'])
def confirmar_whatsapp():
    if request.method == 'POST':
        codigo_digitado = request.form.get('codigo')
        telefone = session.get('temp_telefone')
        if not telefone:
            flash('Sessão expirada, reinicie o cadastro.', 'danger')
            return redirect(url_for('cadastro_whatsapp'))
        if codigo_digitado != session.get('temp_codigo'):
            flash('Código inválido.', 'danger')
            return redirect(url_for('confirmar_whatsapp'))
        
        foto_base64 = session.get('temp_foto')
        foto_path = 'default.png'
        if foto_base64:
            img_data = foto_base64.split(',')[1]
            img_bytes = base64.b64decode(img_data)
            filename = secure_filename(f"user_{telefone}_{datetime.now().timestamp()}.jpg")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'fotos_perfil', filename)
            with open(filepath, 'wb') as f:
                f.write(img_bytes)
            foto_path = f"uploads/fotos_perfil/{filename}"
        
        novo_usuario = User(
            nome=f"Usuário_{telefone[-4:]}",
            telefone=telefone,
            foto=foto_path,
            biografia="Novo usuário da rede!"
        )
        db.session.add(novo_usuario)
        db.session.commit()
        login_user(novo_usuario)
        session.pop('temp_telefone', None)
        session.pop('temp_codigo', None)
        session.pop('temp_foto', None)
        flash('Cadastro realizado com sucesso!', 'success')
        return redirect(url_for('perfil'))
    return render_template('confirmar_whatsapp.html')

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    if request.method == 'POST':
        current_user.nome = request.form.get('nome')
        current_user.biografia = request.form.get('biografia')
        redes = {
            'instagram': request.form.get('instagram', ''),
            'facebook': request.form.get('facebook', ''),
            'twitter': request.form.get('twitter', '')
        }
        current_user.set_redes(redes)
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename:
                filename = secure_filename(f"user_{current_user.id}_{datetime.now().timestamp()}.jpg")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'fotos_perfil', filename)
                foto.save(filepath)
                current_user.foto = f"uploads/fotos_perfil/{filename}"
        db.session.commit()
        flash('Perfil atualizado!', 'success')
        return redirect(url_for('perfil'))
    
    redes = current_user.get_redes()
    return render_template('perfil.html', usuario=current_user, redes=redes)

# ==================== ADMIN ====================
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso negado. Área administrativa.', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)
    return decorated_view

@app.route('/admin')
@admin_required
def admin_dashboard():
    postagens = Postagem.query.all()
    usuarios = User.query.all()
    banner = Banner.query.first()
    stats = {
        'total_postagens': len(postagens),
        'total_visualizacoes': sum(p.visualizacoes for p in postagens),
        'total_comentarios': sum(len(p.comentarios) for p in postagens),
        'total_usuarios': len(usuarios)
    }
    return render_template('admin_dashboard.html', postagens=postagens, banner=banner, stats=stats)

@app.route('/admin/banner', methods=['POST'])
@admin_required
def atualizar_banner():
    if 'imagem' not in request.files:
        flash('Selecione uma imagem', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    imagem = request.files['imagem']
    if imagem.filename:
        filename = secure_filename(f"banner_{datetime.now().timestamp()}.jpg")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'postagens', filename)
        imagem.save(filepath)
        banner = Banner.query.first()
        if not banner:
            banner = Banner()
            db.session.add(banner)
        banner.imagem = f"uploads/postagens/{filename}"
        banner.link = request.form.get('link', '')
        banner.ativo = True
        db.session.commit()
        flash('Banner atualizado!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/postagem/nova', methods=['POST'])
@admin_required
def nova_postagem():
    tipo = request.form.get('tipo')
    titulo = request.form.get('titulo', '')
    conteudo_texto = request.form.get('conteudo_texto', '')
    link_youtube = request.form.get('link_youtube', '')
    localizacao = request.form.get('localizacao', '')
    
    nova_post = Postagem(
        tipo=tipo,
        titulo=titulo,
        conteudo=conteudo_texto,
        link_youtube=link_youtube,
        localizacao=localizacao
    )
    
    if tipo in ['foto', 'video', 'audio'] and 'arquivo' in request.files:
        arquivo = request.files['arquivo']
        if arquivo.filename:
            filename = secure_filename(f"post_{datetime.now().timestamp()}_{arquivo.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'postagens', filename)
            arquivo.save(filepath)
            nova_post.arquivo = f"uploads/postagens/{filename}"
    
    db.session.add(nova_post)
    db.session.commit()
    flash('Postagem criada!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/postagem/<int:post_id>/excluir', methods=['POST'])
@admin_required
def excluir_postagem(post_id):
    postagem = db.session.get(Postagem, post_id)
    if not postagem:
        flash('Postagem não encontrada', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    if postagem.arquivo:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], postagem.arquivo))
        except:
            pass
    db.session.delete(postagem)
    db.session.commit()
    flash('Postagem excluída!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/usuarios')
@admin_required
def admin_usuarios():
    usuarios = User.query.all()
    return render_template('admin_usuarios.html', usuarios=usuarios)

@app.route('/admin/usuario/<int:user_id>/editar', methods=['POST'])
@admin_required
def admin_editar_usuario(user_id):
    usuario = db.session.get(User, user_id)
    if not usuario:
        flash('Usuário não encontrado', 'danger')
        return redirect(url_for('admin_usuarios'))
    
    usuario.nome = request.form.get('nome')
    usuario.biografia = request.form.get('biografia')
    db.session.commit()
    flash('Usuário atualizado!', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuario/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required
def admin_toggle_admin(user_id):
    usuario = db.session.get(User, user_id)
    if not usuario:
        flash('Usuário não encontrado', 'danger')
        return redirect(url_for('admin_usuarios'))
    
    if usuario.id == current_user.id:
        flash('Não pode remover seu próprio admin', 'danger')
    else:
        usuario.is_admin = not usuario.is_admin
        db.session.commit()
        flash(f'Admin de {usuario.nome} alterado', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuario/<int:user_id>/toggle_block', methods=['POST'])
@admin_required
def admin_toggle_block(user_id):
    usuario = db.session.get(User, user_id)
    if not usuario:
        flash('Usuário não encontrado', 'danger')
        return redirect(url_for('admin_usuarios'))
    
    if usuario.id == current_user.id:
        flash('Não pode bloquear a si mesmo', 'danger')
    else:
        usuario.is_active = not usuario.is_active
        db.session.commit()
        flash('Usuário bloqueado/desbloqueado', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuario/<int:user_id>/excluir', methods=['POST'])
@admin_required
def admin_excluir_usuario(user_id):
    usuario = db.session.get(User, user_id)
    if not usuario:
        flash('Usuário não encontrado', 'danger')
        return redirect(url_for('admin_usuarios'))
    
    if usuario.id == current_user.id:
        flash('Não pode excluir a si mesmo', 'danger')
    else:
        Comentario.query.filter_by(user_id=user_id).delete()
        Visualizacao.query.filter_by(user_id=user_id).delete()
        db.session.delete(usuario)
        db.session.commit()
        flash('Usuário excluído!', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/comentarios')
@admin_required
def admin_comentarios():
    comentarios = Comentario.query.order_by(Comentario.data.desc()).all()
    return render_template('admin_comentarios.html', comentarios=comentarios)

@app.route('/admin/comentario/<int:comentario_id>/excluir', methods=['POST'])
@admin_required
def admin_excluir_comentario(comentario_id):
    comentario = db.session.get(Comentario, comentario_id)
    if not comentario:
        flash('Comentário não encontrado', 'danger')
        return redirect(url_for('admin_comentarios'))
    
    if comentario.audio:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], comentario.audio))
        except:
            pass
    
    postagem = comentario.postagem
    db.session.delete(comentario)
    db.session.commit()
    
    if postagem:
        postagem.relevancia = postagem.visualizacoes + (len(postagem.comentarios) * 2)
        db.session.commit()
    
    flash('Comentário excluído', 'success')
    return redirect(url_for('admin_comentarios'))

# ==================== CRIAÇÃO DO ADMIN PADRÃO ====================
def criar_admin_padrao():
    with app.app_context():
        admin = User.query.filter_by(is_admin=True).first()
        if not admin:
            admin = User(
                nome='Administrador',
                telefone='admin',
                foto='default.png',
                biografia='Administrador do sistema',
                is_admin=True,
                is_active=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin padrão criado com sucesso!")

# ==================== INICIALIZAÇÃO ====================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        criar_admin_padrao()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
