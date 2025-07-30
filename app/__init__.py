import os
import json
from flask import Flask, session, request, g
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_babel import Babel, gettext
from dotenv import load_dotenv

load_dotenv()

# Initialize extensions
login_manager = LoginManager()
bcrypt = Bcrypt()
babel = Babel()

def get_locale():
    """Selects the best language for the user."""
    if 'lang' in session:
        return session['lang']
    return request.accept_languages.best_match(['en', 'es', 'fr', 'de', 'ar', 'ru'])

def load_translations(locale):
    """Loads translations from a JSON file for a given locale."""
    translations_path = os.path.join(os.path.dirname(__file__), '..', 'translations')
    json_filename = os.path.join(translations_path, str(locale) + '.json')
    try:
        with open(json_filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def custom_gettext(string, **variables):
    """
    A custom gettext function that uses our JSON translations.
    This function will be used in templates as `_()`.
    """
    # 'g' is a special Flask object that is available during a single request.
    # We store the loaded translations in it to avoid reloading the file multiple times.
    translations = getattr(g, 'translations', None)
    if translations is None:
        locale = get_locale()
        translations = g.translations = load_translations(locale)
    
    # Get the translation and format it with variables if any
    translated_string = translations.get(string, string)
    return translated_string.format(**variables)

def create_app():
    """Creates and configures the Flask application instance."""
    app = Flask(__name__,
                static_folder='../static',
                template_folder='../templates')
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    
    # Initialize Babel with the app and our custom locale selector.
    # We will NOT use a custom domain.
    babel.init_app(app, locale_selector=get_locale)
    
    # Initialize other extensions
    login_manager.init_app(app)
    bcrypt.init_app(app)
    
    from .models import init_db, get_user_by_id

    with app.app_context():
        init_db()

    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'danger'
    
    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(user_id)
        
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    @app.before_request
    def before_request_func():
        # Ensure translations are loaded for each request context.
        g.translations = load_translations(get_locale())

    @app.context_processor
    def inject_global_vars():
        # This injects our custom gettext function as `_` and get_locale()
        # into all templates.
        return dict(_=custom_gettext, get_locale=get_locale)

    return app