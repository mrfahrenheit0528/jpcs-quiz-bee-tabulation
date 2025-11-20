from website import create_app

app = create_app()

if __name__ == '__main__':
    app.run(
        # host = '10.109.24.116', 
        # port = '5000', 
        debug=True)