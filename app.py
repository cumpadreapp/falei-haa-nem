from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Postagem, Comentario, Visualizacao, Banner
from datetime import datetime, timedelta
import os
import json
import random
import string
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua-chave-secreta-mvp-falei-haa-nemm'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///falei_haa_nemm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Pastas de upload
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'fotos_perfil'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'postagens'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audios_comentarios'), exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ========== CONFIGURAÇÃO DO TWILIO (com fallback) ==========
TWILIO_ACTIVE = False
try:
    from twilio.rest import Client
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', 'SEU_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', 'SEU_AUTH_TOKEN')
    TWILIO_VERIFY_SERVICE_SID = os.environ.get('TWILIO_VERIFY_SERVICE_SID', 'SEU_SERVICE_SID')
    
    if TWILIO_ACCOUNT_SID != 'SEU_ACCOUNT_SID' and TWILIO_AUTH_TOKEN != 'SEU_AUTH_TOKEN' and TWILIO_VERIFY_SERVICE_SID != 'SEU_SERVICE_SID':
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        TWILIO_ACTIVE = True
        print("Twilio configurado para envio real de WhatsApp")
    else:
        print("Twilio não configurado – usando modo de simulação")
except ImportError:
    print("Biblioteca Twilio não instalada – usando modo de simulação")
except Exception as e:
    print(f"Erro ao configurar Twilio: {e} – usando modo de simulação")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso negado. Área administrativa.', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)
    return decorated_view

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
    postagem = Postagem.query.get_or_404(post_id)
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
    postagem = Postagem.query.get_or_404(post_id)
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

@app.route('/comentario/<int:comentario_id>/audio', methods=['POST'])
@login_required
def adicionar_audio_comentario(comentario_id):
    comentario = Comentario.query.get_or_404(comentario_id)
    if comentario.user_id != current_user.id:
        flash('Você só pode editar seus próprios comentários', 'danger')
        return redirect(url_for('index'))
    if 'audio' not in request.files:
        flash('Nenhum arquivo', 'danger')
        return redirect(url_for('index'))
    audio = request.files['audio']
    if audio.filename:
        filename = secure_filename(f"audio_{comentario_id}_{datetime.now().timestamp()}.webm")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'audios_comentarios', filename)
        audio.save(filepath)
        comentario.audio = f"uploads/audios_comentarios/{filename}"
        db.session.commit()
        flash('Áudio adicionado!', 'success')
    return redirect(url_for('index'))

@app.route('/compartilhar/<int:post_id>', methods=['POST'])
def compartilhar_whatsapp(post_id):
    postagem = Postagem.query.get_or_404(post_id)
    mensagem = request.form.get('mensagem_personalizada', '')
    numero = request.form.get('numero_whatsapp', '')
    texto = f"{mensagem}\n\n{postagem.titulo}\n{postagem.conteudo}\n\nCompartilhado do Falei, haa Nemm!"
    texto = texto.replace(' ', '%20')
    link = f"https://wa.me/{numero}?text={texto}" if numero else f"https://wa.me/?text={texto}"
    return jsonify({'success': True, 'link': link})

# ==================== AUTENTICAÇÃO E CADASTRO ====================
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
                    return redirect(url_for('index'))
            else:
                flash('Número não cadastrado', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
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

        if TWILIO_ACTIVE:
            try:
                verification = twilio_client.verify.services(TWILIO_VERIFY_SERVICE_SID) \
                    .verifications.create(to=telefone, channel='whatsapp')
                if verification.status == 'pending':
                    session['temp_telefone'] = telefone
                    flash(f'Código enviado para {telefone}.', 'success')
                    return redirect(url_for('confirmar_whatsapp'))
                else:
                    flash('Erro ao enviar código. Tente novamente.', 'danger')
            except Exception as e:
                flash(f'Erro na API do WhatsApp: {str(e)}', 'danger')
        else:
            # Modo simulação: gerar código e mostrar na tela
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

        if TWILIO_ACTIVE:
            try:
                verification_check = twilio_client.verify.services(TWILIO_VERIFY_SERVICE_SID) \
                    .verification_checks.create(to=telefone, code=codigo_digitado)
                if verification_check.status != 'approved':
                    flash('Código inválido. Tente novamente.', 'danger')
                    return redirect(url_for('confirmar_whatsapp'))
            except Exception as e:
                flash(f'Erro na verificação: {str(e)}', 'danger')
                return redirect(url_for('confirmar_whatsapp'))
        else:
            # Modo simulação: compara o código armazenado na sessão
            if codigo_digitado != session.get('temp_codigo'):
                flash('Código inválido.', 'danger')
                return redirect(url_for('confirmar_whatsapp'))

        # Cria o usuário (código aprovado)
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

@app.route('/usuario/<int:user_id>/dados')
def usuario_dados(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'nome': user.nome,
        'foto': url_for('static', filename=user.foto),
        'biografia': user.biografia,
        'telefone': user.telefone,
        'redes': user.get_redes(),
        'data_cadastro': user.data_cadastro.strftime('%d/%m/%Y')
    })

# ==================== ADMIN: GERENCIAR BANNER E POSTAGENS ====================
@app.route('/admin')
@admin_required
def admin_dashboard():
    postagens = Postagem.query.order_by(Postagem.data_criacao.desc()).all()
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
    postagem = Postagem.query.get_or_404(post_id)
    if postagem.arquivo:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], postagem.arquivo))
        except:
            pass
    db.session.delete(postagem)
    db.session.commit()
    flash('Postagem excluída!', 'success')
    return redirect(url_for('admin_dashboard'))

# ==================== ADMIN: GERENCIAR USUÁRIOS ====================
@app.route('/admin/usuarios')
@admin_required
def admin_usuarios():
    usuarios = User.query.all()
    return render_template('admin_usuarios.html', usuarios=usuarios)

@app.route('/admin/usuario/<int:user_id>/editar', methods=['POST'])
@admin_required
def admin_editar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    usuario.nome = request.form.get('nome')
    usuario.biografia = request.form.get('biografia')
    db.session.commit()
    flash('Usuário atualizado!', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuario/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required
def admin_toggle_admin(user_id):
    usuario = User.query.get_or_404(user_id)
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
    usuario = User.query.get_or_404(user_id)
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
    usuario = User.query.get_or_404(user_id)
    if usuario.id == current_user.id:
        flash('Não pode excluir a si mesmo', 'danger')
    else:
        Comentario.query.filter_by(user_id=user_id).delete()
        Visualizacao.query.filter_by(user_id=user_id).delete()
        db.session.delete(usuario)
        db.session.commit()
        flash('Usuário excluído!', 'success')
    return redirect(url_for('admin_usuarios'))

# ==================== ADMIN: GERENCIAR COMENTÁRIOS ====================
@app.route('/admin/comentarios')
@admin_required
def admin_comentarios():
    comentarios = Comentario.query.order_by(Comentario.data.desc()).all()
    return render_template('admin_comentarios.html', comentarios=comentarios)

@app.route('/admin/comentario/<int:comentario_id>/excluir', methods=['POST'])
@admin_required
def admin_excluir_comentario(comentario_id):
    comentario = Comentario.query.get_or_404(comentario_id)
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

# ==================== INICIALIZAÇÃO ====================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        criar_admin_padrao()
    app.run(debug=True)