import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ---------- Модели ----------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Reader(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    patronymic = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    library_card = db.Column(db.String(20), unique=True)

    user = db.relationship('User', backref=db.backref('reader', uselist=False))

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    isbn = db.Column(db.String(20))
    year = db.Column(db.Integer)
    publisher = db.Column(db.String(100))
    cover_url = db.Column(db.String(300))

    copies = db.relationship('Copy', backref='book', lazy=True)

class Copy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    inv_number = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), default='available')

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    copy_id = db.Column(db.Integer, db.ForeignKey('copy.id'), nullable=False)
    reader_id = db.Column(db.Integer, db.ForeignKey('reader.id'), nullable=False)
    loan_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    return_date = db.Column(db.Date, nullable=True)
    issued_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    copy = db.relationship('Copy')
    reader = db.relationship('Reader')
    issuer = db.relationship('User', foreign_keys=[issued_by])

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- Маршруты ----------
@app.route('/')
def index():
    books = Book.query.all()
    for book in books:
        book.available = Copy.query.filter_by(book_id=book.id, status='available').count()
    last_login = request.cookies.get('last_login')
    return render_template('index.html', books=books, last_login=last_login)

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    book.available = Copy.query.filter_by(book_id=book.id, status='available').count()
    return render_template('book_detail.html', book=book)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        role = request.form.get('role', 'reader')
        if User.query.filter_by(login=login).first():
            flash('Логин уже занят')
            return redirect(url_for('register'))
        user = User(login=login, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        if role == 'reader':
            reader = Reader(
                user_id=user.id,
                first_name=request.form['first_name'],
                last_name=request.form['last_name'],
                library_card=request.form['library_card'],
                phone=request.form.get('phone'),
                email=request.form.get('email')
            )
            db.session.add(reader)
            db.session.commit()
        flash('Регистрация успешна, войдите')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        user = User.query.filter_by(login=login).first()
        if user and user.check_password(password):
            login_user(user)
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('last_login', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), max_age=60*60*24*30)
            return resp
        else:
            flash('Неверный логин или пароль')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    if current_user.role != 'reader':
        flash('Только для читателей')
        return redirect(url_for('index'))
    reader = Reader.query.filter_by(user_id=current_user.id).first()
    loans = Loan.query.filter_by(reader_id=reader.id, return_date=None).all()
    for loan in loans:
        loan.book_title = loan.copy.book.title
        loan.book_author = loan.copy.book.author
    return render_template('profile.html', reader=reader, loans=loans)

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Доступ запрещён')
        return redirect(url_for('index'))
    users = User.query.all()
    books = Book.query.all()
    return render_template('admin.html', users=users, books=books)

@app.route('/admin/add_book', methods=['POST'])
@login_required
def add_book():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    title = request.form['title']
    author = request.form['author']
    description = request.form.get('description')
    content = request.form.get('content')
    category = request.form.get('category')
    isbn = request.form.get('isbn')
    year = request.form.get('year')
    publisher = request.form.get('publisher')
    copies_count = int(request.form.get('copies_count', 1))
    book = Book(
        title=title, author=author, description=description, content=content,
        category=category, isbn=isbn, year=year, publisher=publisher
    )
    db.session.add(book)
    db.session.commit()
    for i in range(copies_count):
        inv_number = f"{book.id}-{i+1}"
        copy = Copy(book_id=book.id, inv_number=inv_number)
        db.session.add(copy)
    db.session.commit()
    flash('Книга добавлена')
    return redirect(url_for('admin_panel'))

@app.route('/librarian')
@login_required
def librarian_panel():
    if current_user.role not in ['admin', 'librarian']:
        return redirect(url_for('index'))
    active_loans = Loan.query.filter_by(return_date=None).all()
    for loan in active_loans:
        loan.book_title = loan.copy.book.title
        loan.reader_name = f"{loan.reader.last_name} {loan.reader.first_name}"
    return render_template('librarian.html', active_loans=active_loans)

@app.route('/librarian/issue', methods=['POST'])
@login_required
def issue_book():
    if current_user.role not in ['admin', 'librarian']:
        return redirect(url_for('index'))
    copy_id = request.form['copy_id']
    reader_card = request.form['library_card']
    reader = Reader.query.filter_by(library_card=reader_card).first()
    if not reader:
        flash('Читатель не найден')
        return redirect(url_for('librarian_panel'))
    copy = Copy.query.get(copy_id)
    if not copy or copy.status != 'available':
        flash('Экземпляр недоступен')
        return redirect(url_for('librarian_panel'))
    loan_date = datetime.now().date()
    due_date = loan_date + timedelta(days=14)
    loan = Loan(
        copy_id=copy_id,
        reader_id=reader.id,
        loan_date=loan_date,
        due_date=due_date,
        issued_by=current_user.id
    )
    copy.status = 'loaned'
    db.session.add(loan)
    db.session.commit()
    flash(f'Книга выдана читателю {reader.last_name} {reader.first_name}')
    return redirect(url_for('librarian_panel'))

@app.route('/librarian/return', methods=['POST'])
@login_required
def return_book():
    if current_user.role not in ['admin', 'librarian']:
        return redirect(url_for('index'))
    loan_id = request.form['loan_id']
    loan = Loan.query.get(loan_id)
    if loan and loan.return_date is None:
        loan.return_date = datetime.now().date()
        copy = Copy.query.get(loan.copy_id)
        copy.status = 'available'
        db.session.commit()
        flash('Книга возвращена')
    else:
        flash('Ошибка возврата')
    return redirect(url_for('librarian_panel'))

@app.route('/api/available_copies')
def available_copies():
    book_id = request.args.get('book_id')
    if not book_id:
        return jsonify([])
    copies = Copy.query.filter_by(book_id=book_id, status='available').all()
    return jsonify([{'copy_id': c.id, 'inv_number': c.inv_number} for c in copies])

# ---------- Инициализация БД с 15 книгами (увеличенные тексты) ----------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(login='admin').first():
        admin = User(login='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

    if Book.query.count() == 0:
        books_data = [
            # Бизнес (3)
            {"title": "От нуля к единице", "author": "Питер Тиль", "category": "Бизнес", "year": 2014,
             "description": "Как создавать инновационные стартапы, которые меняют рынок.",
             "content": "Каждый момент в бизнесе бывает только один раз. Будущее создают те, кто умеет видеть скрытые возможности. В этой книге Питер Тиль, сооснователь PayPal, делится опытом создания компаний, способных изменить мир. Он утверждает, что настоящий успех приходит не от конкуренции, а от создания монополии на уникальном рынке. Книга научит вас мыслить нестандартно и находить идеи, которые приведут к прорыву. Тиль предлагает семь вопросов, которые необходимо задать себе, чтобы построить бизнес будущего. Технология, монополия, команда, распространение, долговечность и секретность — вот ключевые принципы, которые он раскрывает на примере PayPal, Tesla, SpaceX и других компаний. Это не просто книга о стартапах, это философия создания уникального."},
            {"title": "Думай медленно... решай быстро", "author": "Даниэль Канеман", "category": "Бизнес", "year": 2011,
             "description": "Нобелевский лауреат объясняет, как работает наше мышление.",
             "content": "Даниэль Канеман, лауреат Нобелевской премии, представляет революционную теорию о двух системах мышления: быстрой (интуитивной) и медленной (рациональной). Книга объясняет, почему мы часто совершаем ошибки в суждениях и как можно научиться принимать более взвешенные решения. Это обязательное чтение для всех, кто хочет понимать психологию принятия решений в бизнесе и жизни. Канеман описывает многочисленные эксперименты, показывающие, как наше восприятие искажается эвристиками, как мы переоцениваем свои знания и как избежать когнитивных ловушек. Особое внимание уделяется эффекту фрейминга, якорению и тому, как наш мозг реагирует на потери сильнее, чем на приобретения. Книга изменит ваш взгляд на принятие решений."},
            {"title": "Стартап: настольная книга основателя", "author": "Стив Бланк", "category": "Бизнес", "year": 2012,
             "description": "Практическое руководство по поиску бизнес-модели и масштабированию.",
             "content": "Стив Бланк, признанный гуру стартапов, предлагает методологию Customer Development, которая помогла тысячам компаний найти свою нишу. Книга учит не просто строить продукт, а искать клиентов и проверять гипотезы. Это пошаговое руководство для тех, кто хочет превратить идею в устойчивый бизнес. Автор развенчивает миф о том, что успешный стартап начинается с гениальной идеи. Вместо этого он предлагает системный подход: сначала найти и проверить проблему, затем сформулировать решение, проверить его на реальных клиентах и только потом масштабировать. Книга содержит конкретные шаблоны для интервью с клиентами, метрики для оценки и примеры из практики. Благодаря этой методологии вы избежите главной ошибки стартапов — создания продукта, который никому не нужен."},
            # Программирование (3)
            {"title": "Чистый код", "author": "Роберт Мартин", "category": "Программирование", "year": 2008,
             "description": "Библия для разработчиков о том, как писать код, который легко читать.",
             "content": "Роберт Мартин (Дядя Боб) собрал лучшие практики написания чистого, понятного и поддерживаемого кода. Книга полна примеров на Java, но принципы универсальны для любого языка. Вы научитесь именовать переменные, структурировать функции, писать комментарии там, где нужно, и избавляться от технического долга. Особое внимание уделяется SOLID-принципам, работе с классами, обработке ошибок и тестированию. Код — это не просто инструкция для компьютера, это способ общения с другими разработчиками. Мартин доказывает, что чистый код экономит время и нервы команды, снижает количество багов и делает проект гибким. Эта книга должна быть на столе каждого программиста."},
            {"title": "Совершенный код", "author": "Стив Макконнелл", "category": "Программирование", "year": 2004,
             "description": "Энциклопедия техник программирования, от структуры до отладки.",
             "content": "Это фундаментальный труд, охватывающий все этапы разработки ПО: от проектирования до отладки. Макконнелл рассказывает, как создавать надежный, эффективный и легко поддерживаемый код. Книга будет полезна как начинающим, так и опытным программистам. В ней рассматриваются вопросы именования, форматирования, проектирования классов, обработки ошибок, тестирования, оптимизации и многие другие. Каждый раздел содержит конкретные рекомендации и примеры на C++, Java и других языках. Автор использует метафору «строительства программного обеспечения», подчёркивая, что хороший код — это результат продуманного проектирования и дисциплины. Более 900 страниц бесценной информации."},
            {"title": "Изучаем Python", "author": "Марк Лутц", "category": "Программирование", "year": 2013,
             "description": "Полное руководство по Python для начинающих и профессионалов.",
             "content": "Марк Лутц, один из ведущих экспертов по Python, предлагает исчерпывающее руководство по языку. Книга охватывает синтаксис, типы данных, функции, модули, ООП, исключения и многое другое. Подходит для глубокого изучения Python с нуля. В четвёртом издании добавлены материалы о Python 3.x, асинхронном программировании, декораторах и генераторах. Книга содержит сотни примеров кода и упражнений для закрепления. Лутц объясняет не только как, но и почему Python работает именно так, что помогает понять внутреннюю логику языка. Это идеальный выбор для тех, кто хочет стать профессионалом Python."},
            # Нейросети (3)
            {"title": "Глубокое обучение", "author": "Иэн Гудфеллоу", "category": "Нейросети", "year": 2016,
             "description": "Фундаментальный учебник по нейросетям от ведущих исследователей.",
             "content": "Эта книга — официальный учебник по глубокому обучению, написанный пионерами в этой области. Она охватывает математические основы, архитектуры нейросетей, методы оптимизации и современные приложения. Рекомендуется для студентов и специалистов, желающих углубиться в AI. Книга начинается с линейной алгебры и теории вероятностей, затем переходит к многослойным перцептронам, свёрточным и рекуррентным сетям, а также к генеративно-состязательным сетям (GAN). Рассматриваются современные методы регуляризации, оптимизации и практические советы по обучению. Это наиболее полный ресурс по глубокому обучению, используемый в ведущих университетах мира."},
            {"title": "Python и машинное обучение", "author": "Себастьян Рашка", "category": "Нейросети", "year": 2015,
             "description": "Практическое введение в ML и нейросети на Python.",
             "content": "Книга знакомит с основами машинного обучения на Python с использованием библиотек scikit-learn, NumPy и TensorFlow. Автор шаг за шагом разбирает алгоритмы классификации, регрессии, кластеризации и нейросетей, приводя множество примеров кода. В третьем издании добавлены главы о глубоком обучении с TensorFlow 2 и Keras, а также о работе с текстовыми данными. Каждая тема сопровождается пояснениями математических концепций и их реализацией на Python. Книга идеально подходит для практиков, желающих начать применять ML в своих проектах."},
            {"title": "Искусственный интеллект. Современный подход", "author": "Стюарт Рассел", "category": "Нейросети", "year": 2016,
             "description": "Классический учебник по AI, охватывающий нейросети и многое другое.",
             "content": "Это наиболее авторитетный учебник по искусственному интеллекту. Он охватывает широкий круг тем: от поиска и логики до обучения с подкреплением и нейросетей. Книга подойдет как для введения в AI, так и для углубленного изучения. В четвёртом издании обновлены главы о глубоком обучении, робототехнике и этических аспектах AI. Рассел и Норвиг сочетают теорию с практическими примерами, показывая, как создавать интеллектуальных агентов. Это настольная книга для всех, кто серьёзно занимается искусственным интеллектом."},
            # Экономика (3)
            {"title": "Капитал в XXI веке", "author": "Томас Пикетти", "category": "Экономика", "year": 2013,
             "description": "Масштабное исследование неравенства и динамики капитала.",
             "content": "Томас Пикетти анализирует эволюцию неравенства в развитых странах за последние 300 лет. Он доказывает, что капитал имеет тенденцию концентрироваться, что ведет к социальному расслоению. Книга вызвала мировую дискуссию о путях справедливого экономического роста. Пикетти опирается на огромный массив исторических данных, показывая, что норма доходности капитала устойчиво превышает темпы экономического роста. Это приводит к тому, что богатство наследуется и концентрируется в руках немногих. Автор предлагает прогрессивное налогообложение как возможное решение. Книга стала бестселлером и обязательным чтением для экономистов и политиков."},
            {"title": "Фрикономика", "author": "Стивен Левитт", "category": "Экономика", "year": 2005,
             "description": "Нестандартный взгляд на экономические механизмы, стоящие за явлениями жизни.",
             "content": "Авторы показывают, как экономический подход может объяснить самые неожиданные вещи: почему учителя жульничают, почему наркодилеры живут с родителями и как имя ребенка влияет на его будущее. Книга увлекательно раскрывает скрытые стимулы, управляющие миром. Левитт и Дабнер используют данные, чтобы развенчать мифы и показать, что зачастую причинно-следственные связи далеки от очевидных. Книга стала мировым бестселлером и изменила представление об экономике как о скучной науке."},
            {"title": "Экономика всего", "author": "Александр Аузан", "category": "Экономика", "year": 2014,
             "description": "Как культурные коды и институты влияют на экономическое развитие.",
             "content": "Александр Аузан, декан экономического факультета МГУ, объясняет, почему одни страны богаты, а другие бедны, с точки зрения институциональной экономики. Книга помогает понять, как культура, доверие и исторические традиции формируют экономический успех. Аузан разбирает влияние доверия, менталитета и сетевых связей на экономический рост. Особое внимание уделяется России: почему реформы не всегда дают ожидаемый эффект и как культурные особенности влияют на бизнес. Книга написана доступным языком и будет интересна всем, кто хочет понять, как устроена экономика на самом деле."},
            # Криптовалюта (3)
            {"title": "Mastering Bitcoin", "author": "Андреас Антонопулос", "category": "Криптовалюта", "year": 2014,
             "description": "Техническое руководство по биткоину и блокчейну для разработчиков.",
             "content": "Эта книга — техническая библия по биткоину. Антонопулос подробно объясняет, как работает блокчейн, транзакции, криптография, майнинг и кошельки. Книга содержит множество примеров кода и будет полезна разработчикам, желающим создавать приложения на основе блокчейна. Второе издание охватывает SegWit, Lightning Network и другие нововведения. Автор не только описывает технологию, но и разъясняет экономические и философские аспекты биткоина. Это незаменимое руководство для тех, кто хочет по-настоящему разобраться в криптовалютах."},
            {"title": "Криптовалюты. Биткоин и блокчейн", "author": "Натаниэль Поппер", "category": "Криптовалюта", "year": 2015,
             "description": "История биткоина, его влияние на экономику и будущее финансов.",
             "content": "Журналист New York Times Натаниэль Поппер рассказывает захватывающую историю возникновения биткоина, его главных героев и борьбы за децентрализацию. Книга объясняет, как криптовалюта меняет представление о деньгах и финансах. Поппер проводит читателя через ранние дни, когда биткоин стоил копейки, до момента, когда он стал глобальным феноменом. Он показывает как технические, так и социальные аспекты, включая знаменитые взломы бирж, аресты создателей Silk Road и внутренние конфликты сообщества. Книга будет интересна всем, кто хочет понять, откуда взялись криптовалюты и куда они движутся."},
            {"title": "The Truth Machine", "author": "Пол Винья", "category": "Криптовалюта", "year": 2018,
             "description": "Как блокчейн изменит мир: от финансов до голосования.",
             "content": "Авторы, финансовые эксперты, исследуют потенциал блокчейна за пределами криптовалют. Они показывают, как технология может обеспечить прозрачность голосований, защиту данных, управление цепочками поставок и многое другое. Книга дает оптимистичный взгляд на будущее блокчейна. Винья и Кейси рассказывают о реальных проектах, которые уже меняют отрасли: от идентификации в развивающихся странах до отслеживания алмазов. Они также обсуждают вызовы, стоящие на пути массового внедрения, и почему блокчейн может стать фундаментом новой цифровой экономики. Книга написана доступно и будет интересна широкому кругу читателей."}
        ]

        for data in books_data:
            book = Book(
                title=data["title"], author=data["author"], category=data["category"],
                year=data["year"], description=data["description"], content=data["content"],
                cover_url=None
            )
            db.session.add(book)
            db.session.flush()
            for i in range(3):
                copy = Copy(book_id=book.id, inv_number=f"{book.id}-{i+1}", status="available")
                db.session.add(copy)
        db.session.commit()
        print("Добавлено 15 книг с полными текстами (увеличены на 30%)")

if __name__ == '__main__':
    app.run(debug=True)