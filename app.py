from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Book  # Use `db` from models.py
from flask_migrate import Migrate
import requests

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Use a strong secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'  # Database URI

# Initialize extensions
db.init_app(app)  # Initialize the db instance from models.py
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'auth'  # Redirect to login page if not logged in

# Load user for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Google Books API Key
API_KEY = 'AIzaSyCyVgnY4TAUURkXoi9ba4JqhTSpucLFFcc'  # Replace with your API key

# Admin Login
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check for admin user
        user = User.query.filter_by(username=username, is_admin=True).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')

    return render_template('admin_login.html')

# Admin Dashboard
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('index'))

    # Fetch all users
    users = User.query.all()

    # Create a dictionary of users and their books
    user_books = {}
    for user in users:
        user_books[user.id] = Book.query.filter_by(user_id=user.id).all()

    return render_template('admin_dashboard.html', users=users, user_books=user_books)

# CLI Command: Create Admin User
@app.cli.command("create_admin")
def create_admin():
    with app.app_context():
        username = input("Enter admin username: ")
        password = input("Enter admin password: ")

        # Check if the admin user already exists
        existing_admin = User.query.filter_by(username=username).first()
        if existing_admin:
            print(f"Admin with username {username} already exists.")
        else:
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            admin_user = User(username=username, password=hashed_password, is_admin=True)
            db.session.add(admin_user)
            db.session.commit()
            print(f"Admin user {username} created successfully.")

# Home Page (Popular Books)
@app.route('/')
def index():
    url = f'https://www.googleapis.com/books/v1/volumes?q=subject:fiction&orderBy=relevance&maxResults=10&key={API_KEY}'
    response = requests.get(url)
    data = response.json()

    books = []
    if 'items' in data:
        books = [{
            'title': item['volumeInfo'].get('title', 'No Title'),
            'author': item['volumeInfo'].get('authors', ['Unknown'])[0],
            'description': item['volumeInfo'].get('description', 'No description available'),
            'thumbnail': item['volumeInfo'].get('imageLinks', {}).get('thumbnail', 'https://via.placeholder.com/150'),
            'link': item['volumeInfo'].get('infoLink', '#')
        } for item in data['items']]

    return render_template('index.html', books=books)

# Auth (Login and Sign-up)
@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        # Handle Login
        if 'login' in request.form:
            username = request.form['username']
            password = request.form['password']
            user = User.query.filter_by(username=username).first()

            if user and check_password_hash(user.password, password):  # Assuming password is hashed
                login_user(user)
                flash('Login successful!', 'success')
                
                # Redirect based on user type (admin or regular user)
                if user.is_admin:
                    return redirect(url_for('admin_dashboard'))  # Admin should go to admin dashboard
                else:
                    return redirect(url_for('dashboard'))  # Regular user should go to user dashboard
            else:
                flash('Invalid username or password.', 'danger')

        # Handle Sign Up
        elif 'signup' in request.form:
            username = request.form['username']
            password = request.form['password']
            user_exists = User.query.filter_by(username=username).first()

            if user_exists:
                flash('Username already taken. Please choose a different one.', 'danger')
            else:
                hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
                new_user = User(username=username, password=hashed_password)
                db.session.add(new_user)
                db.session.commit()
                flash('Sign Up successful! You can now log in.', 'success')

    return render_template('auth.html')

# Dashboard Page (User's Books)
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if current_user.is_admin:
        flash('Access denied. Admins cannot access user dashboards.', 'danger')
        return redirect(url_for('admin_dashboard'))  # Redirect admins to the admin dashboard
    
    # Fetch books for the current user
    books = Book.query.filter_by(user_id=current_user.id).all()

    # Handle search functionality if submitted
    if request.method == 'POST':
        query = request.form.get('query')  # Search query
        if query:
            url = f'https://www.googleapis.com/books/v1/volumes?q={query}&key={API_KEY}'
            response = requests.get(url)
            data = response.json()

            search_results = []
            if 'items' in data:
                search_results = [item['volumeInfo'] for item in data['items']]

            return render_template('dashboard.html', user=current_user, books=books, search_results=search_results)

    return render_template('dashboard.html', user=current_user, books=books)

# Add Book to Shelf
@app.route('/add_book', methods=['POST'])
@login_required
def add_book():
    title = request.form.get('title')
    author = request.form.get('author')
    description = request.form.get('description')

    # Add the book to the database
    new_book = Book(title=title, author=author, description=description, user_id=current_user.id)
    db.session.add(new_book)
    db.session.commit()
    flash(f'Book "{title}" added to your shelf!', 'success')
    return redirect(url_for('dashboard'))

# Search Books
@app.route('/search', methods=['GET', 'POST'])
def search():
    books = []
    query = request.args.get('query', '')  # Get the search query from the URL parameters
    
    # Handle search functionality
    if query:
        # Request up to 20 books from Google Books API
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=20&key={API_KEY}"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            for item in data.get('items', []):
                volume_info = item.get('volumeInfo', {})
                image_links = volume_info.get('imageLinks', {})
                books.append({
                    'title': volume_info.get('title', 'No Title'),
                    'author': ', '.join(volume_info.get('authors', ['Unknown Author'])),
                    'description': volume_info.get('description', 'No Description Available'),
                    'thumbnail': image_links.get('thumbnail', 'https://via.placeholder.com/150'),
                    'infoLink': volume_info.get('infoLink', '#')
                })
        else:
            print("Error fetching data from Google Books API:", response.status_code)

    return render_template('search.html', books=books, query=query)

# Add Book to User's Shelf (from Search Results)
@app.route('/add_book_to_shelf', methods=['POST'])
@login_required
def add_book_to_shelf():
    title = request.form.get('title')
    author = request.form.get('author')
    description = request.form.get('description')

    # Check if the book already exists on the user's shelf
    existing_book = Book.query.filter_by(title=title, user_id=current_user.id).first()

    if not existing_book:
        new_book = Book(title=title, author=author, description=description, user_id=current_user.id)
        db.session.add(new_book)
        db.session.commit()
        flash(f'Book "{title}" added to your shelf!', 'success')
    else:
        flash('This book is already on your shelf.', 'info')

    return redirect(url_for('search'))

# Remove Book from User's Shelf
@app.route('/remove_book_from_shelf/<int:book_id>', methods=['POST'])
@login_required
def remove_book_from_shelf(book_id):
    # Fetch the book by its ID and ensure it belongs to the current user
    book = Book.query.filter_by(id=book_id, user_id=current_user.id).first()

    if book:
        db.session.delete(book)
        db.session.commit()
        flash(f'Book "{book.title}" removed from your shelf.', 'success')
    else:
        flash('The book could not be found or does not belong to your shelf.', 'danger')

    return redirect(url_for('dashboard'))

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))  # Redirect to the home page

if __name__ == '__main__':
    app.run(debug=True)
