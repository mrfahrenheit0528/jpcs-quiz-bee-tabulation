"""Production entry point. Use ./quiz start for data import, LAN and discovery."""
from waitress import serve
from website import create_app
from website.manage import DATA, exclusive, secret
from website.migrate import migrate

def main():
    with exclusive():
        migrate(DATA/'database.db')
        app=create_app({'SECRET_KEY':secret(), 'SQLALCHEMY_DATABASE_URI':f'sqlite:///{DATA / "database.db"}'})
        port=app.config['QUIZ_PORT']
        print(f'Quiz server listening on port {port}; 8 Waitress threads',flush=True)
        serve(app,host='0.0.0.0',port=port,threads=8)

if __name__=='__main__': main()
