try:
	from .app_factory import create_app
except ImportError:
	from app_factory import create_app


app = create_app()
